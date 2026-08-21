"""
IPTV 质量检测模块
双引擎：HTTP 快筛 + FFprobe 中度探测
"""
import re
import asyncio
import json
import logging
import subprocess
import aiohttp
import config

_ffprobe_executor = None

logger = logging.getLogger(__name__)


def _strip_suffix(url: str) -> str:
    """去掉 $LR... 等播放器自定义后缀"""
    if "$" in url:
        return url.split("$", 1)[0]
    return url


def _get_domain(url: str) -> str:
    """从 URL 中提取基础域名（不含路径和端口）"""
    if not url:
        return ""
    stripped = url.split("$", 1)[0] if "$" in url else url
    m = re.match(r"(https?://(?:\[?[^\[/\]]+\]?)?)", stripped)
    return m.group(1) if m else ""


def _is_m3u8_url(url: str) -> bool:
    """判断是否为 m3u8 地址"""
    return ".m3u8" in _strip_suffix(url) or "index.m3u8" in _strip_suffix(url)


def _get_base_url(url: str) -> str:
    """获取 URL 的基地址（用于拼接相对路径的 TS 片段）"""
    stripped = _strip_suffix(url)
    idx = stripped.rfind("/")
    return stripped[:idx + 1] if idx != -1 else stripped


async def _http_fast_check(session, url, timeout):
    """HTTP 快筛：拉 playlist 验证可达性"""
    result = {"url": url, "status": "unknown", "detail": "", "layer": "fast"}
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            if resp.status != 200:
                result["status"] = "failed"
                result["detail"] = f"http_status={resp.status}"
                return result
            text = await resp.text()
            if not text or len(text) < 10:
                result["status"] = "empty"
                result["detail"] = "playlist is empty"
                return result
            if ".m3u8" in url or "index.m3u8" in url:
                ts_lines = [l.strip() for l in text.splitlines()
                            if l.strip() and not l.strip().startswith("#") and l.strip()]
                result["ts_count"] = len(ts_lines)
                if not ts_lines:
                    result["status"] = "ok_no_ts"
                    result["detail"] = "live m3u8 (no ENDLIST)"
                else:
                    result["status"] = "ok"
                    result["detail"] = f"playlist_ok ts_entries={len(ts_lines)}"
            else:
                result["status"] = "ok"
                result["detail"] = "http_ok"
    except asyncio.TimeoutError:
        result["status"] = "timeout"
        result["detail"] = f"timeout >{timeout}s"
    except Exception as e:
        result["status"] = "error"
        result["detail"] = str(e)
    return result


def _find_ffprobe():
    """查找 ffprobe 可执行文件"""
    import shutil
    if config.ffmpeg_path:
        return config.ffmpeg_path
    path = shutil.which("ffprobe")
    return path or "ffprobe"


def _run_ffprobe(url, timeout, max_streams):
    """运行 ffprobe 探流，返回元数据字典"""
    ffprobe = _find_ffprobe()
    cmd = [
        ffprobe,
        "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-i", url,
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=False,
            timeout=timeout + 2,
        )
        if proc.returncode != 0:
            return {"status": "failed", "detail": f"ffprobe exit={proc.returncode}"}
        data = json.loads(proc.stdout.decode("utf-8", errors="replace"))
        streams = data.get("streams", [])
        video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
        audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
        result = {
            "status": "ok",
            "detail": "",
            "video_codec": video_stream.get("codec_name", "") if video_stream else "",
            "width": video_stream.get("width", 0) if video_stream else 0,
            "height": video_stream.get("height", 0) if video_stream else 0,
            "bitrate": 0,
        }
        if video_stream and video_stream.get("bit_rate"):
            result["bitrate"] = int(video_stream["bit_rate"])
        elif audio_stream and audio_stream.get("bit_rate"):
            result["bitrate"] = int(audio_stream["bit_rate"])
        detail_parts = []
        if video_stream:
            res = f"{result['width']}x{result['height']}"
            detail_parts.append(f"v:{video_stream['codec_name']}@{res}")
        if audio_stream:
            detail_parts.append(f"a:{audio_stream['codec_name']}")
        if result["bitrate"] > 0:
            detail_parts.append(f"br:{result['bitrate']//1000}kbps")
        result["detail"] = " ".join(detail_parts)
        return result
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "detail": f"ffprobe timeout >{timeout}s"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


async def _get_ffprobe_executor():
    global _ffprobe_executor
    if _ffprobe_executor is None:
        import concurrent.futures
        _ffprobe_executor = concurrent.futures.ProcessPoolExecutor(max_workers=8)
    return _ffprobe_executor


def _shutdown_ffprobe_executor():
    """全局清理：关闭 ffprobe 进程池，避免 Event loop 关闭时的 RuntimeError"""
    global _ffprobe_executor
    if _ffprobe_executor is not None:
        try:
            _ffprobe_executor.shutdown(wait=False)
        except Exception:
            pass
        _ffprobe_executor = None


async def _ffprobe_async(url, timeout, max_streams):
    """在独立进程池中异步运行 ffprobe"""
    loop = asyncio.get_event_loop()
    executor = await _get_ffprobe_executor()
    return await loop.run_in_executor(executor, _run_ffprobe, url, timeout, max_streams)


async def _check_single(session, url, http_timeout, ffprobe_timeout, ffprobe_semaphore=None):
    """单 URL 双引擎检测：先 HTTP 快筛，再通过则 FFprobe 中度探测"""
    clean_url = _strip_suffix(url)
    # 第一层：HTTP 快筛
    fast = await _http_fast_check(session, clean_url, http_timeout)
    if fast["status"] not in ("ok", "ok_no_ts"):
        fast["layer"] = "fast_fail"
        return fast
    # 第二层：FFprobe 中度探测
    if config.enable_ffprobe:
        probe = await _ffprobe_async(clean_url, ffprobe_timeout, config.ffprobe_max_streams)
        # ffprobe 失败不阻塞，保留快筛结果
        if probe["status"] != "ok":
            fast["ffprobe"] = probe
            return fast
        # 质量过滤：bitrate 为 0 说明 ffprobe 无法读取码率字段（常见于 IPTV），跳过码率检查只检查分辨率
        min_br = config.min_bitrate if config.min_bitrate > 0 else 0
        if min_br > 0 and probe.get("bitrate", 0) > 0 and probe.get("bitrate", 0) < min_br:
            probe["status"] = "failed"
            probe["detail"] += f" low_bitrate={probe['bitrate']//1000}kbps < {min_br//1000}kbps"
            probe["layer"] = "ffprobe_fail"
            fast["ffprobe"] = probe
            return fast
        min_res = int(config.min_resolution) if config.min_resolution else 0
        if min_res > 0 and probe.get("width", 0) < min_res:
            probe["status"] = "failed"
            probe["detail"] += f" low_resolution={probe['width']}px < {min_res}px"
            probe["layer"] = "ffprobe_fail"
            fast["ffprobe"] = probe
            return fast
        fast["ffprobe"] = probe
        fast["layer"] = "ffprobe"
    return fast


async def check_all(channels):
    """
    双引擎并发检测所有频道的所有 URL。

    参数:
        channels: {category: {channel_name: [url1, url2, ...]}}

    返回:
        (check_results, fail_domains)
    """
    semaphore = asyncio.Semaphore(config.check_max_conn)
    results = {}

    # FFprobe 并发限制（避免同时启动过多进程导致系统资源耗尽）
    async def _worker(cat, ch_name, url):
        async with semaphore:
            r = await _check_single(session, url, config.check_timeout, config.ffprobe_timeout)
            return (cat, ch_name, url, r)

    connector = aiohttp.TCPConnector(limit=config.check_max_conn, ssl=False)
    timeout = aiohttp.ClientTimeout(total=config.check_timeout)
    all_tasks = []
    for cat, ch_dict in channels.items():
        for ch_name, url_list in ch_dict.items():
            for url in url_list:
                all_tasks.append(_worker(cat, ch_name, url))

    fail_domains = {}

    logger.info(
        f"开始质量检测，共 {len(all_tasks)} 个 URL，并发数 {config.check_max_conn}，"
        f"HTTP 超时 {config.check_timeout}s"
        + (f"，FFprobe 启用，超时 {config.ffprobe_timeout}s" if config.enable_ffprobe else "")
    )

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        tasks = [asyncio.create_task(t) for t in all_tasks]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

    for item in raw_results:
        if isinstance(item, Exception):
            continue
        cat, ch_name, url, r = item
        results.setdefault(cat, {}).setdefault(ch_name, {})[url] = r
        if r["status"] in ("ok", "ok_no_ts"):
            logger.debug(f"  [{ch_name}] OK  {url}  ({r.get('detail', '')})")
        else:
            logger.debug(f"  [{ch_name}] FAIL {url}  ({r.get('detail', '')})")
            domain = _get_domain(url)
            if domain:
                fail_domains.setdefault(domain, []).append(
                    {"url": url, "status": r["status"], "detail": r.get("detail", "")}
                )

    total = failed = timeout_cnt = error_cnt = 0
    for cat_ch in results.values():
        for ch_urls in cat_ch.values():
            for r in ch_urls.values():
                total += 1
                if r["status"] == "failed":
                    failed += 1
                elif r["status"] == "timeout":
                    timeout_cnt += 1
                elif r["status"] in ("error", "empty"):
                    error_cnt += 1
    ok_count = total - failed - timeout_cnt - error_cnt
    logger.info(
        f"质量检测完成: 总计={total} 通过={ok_count} 失败={failed} 超时={timeout_cnt} 错误={error_cnt}"
    )
    return results, fail_domains


def filter_dead_urls(channels, check_results):
    """
    根据检测结果过滤失效源，返回去重后的 channels。
    保留条件: status 为 "ok" 或 "ok_no_ts"，且 layer 为 "ffprobe"（排除仅快筛无元数据的源）
    """
    filtered = {}
    for cat, ch_dict in channels.items():
        filtered[cat] = {}
        for ch_name, url_list in ch_dict.items():
            valid = []
            for url in url_list:
                cl = _strip_suffix(url)
                r = check_results.get(cat, {}).get(ch_name, {}).get(cl, {})
                if r.get("status") in ("ok", "ok_no_ts") and r.get("layer") == "ffprobe":
                    valid.append(url)
            if valid:
                filtered[cat][ch_name] = valid

    removed = sum(
        len(channels[c][n]) - len(filtered[c][n])
        for c in filtered for n in filtered.get(c, {})
    )
    kept = sum(len(urls) for c in filtered for urls in filtered[c].values())
    logger.info(f"过滤后: 保留 {kept} 个有效源，移除 {removed} 个失效源")
    return filtered
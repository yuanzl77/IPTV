"""
IPTV 质量检测模块
使用 aiohttp + asyncio 并发检测 m3u8 流和直链的有效性
"""
import re
import asyncio
import logging
import aiohttp
import config

logger = logging.getLogger(__name__)


def _strip_suffix(url: str) -> str:
    """去掉 $LR... 等播放器自定义后缀"""
    if "$" in url:
        return url.split("$", 1)[0]
    return url


def _get_domain(url: str) -> str:
    """从 URL 中提取基础域名（不含路径和端口）"""
    if not url:
        return ''
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


async def _check_m3u8(session: aiohttp.ClientSession, url: str, timeout: float, min_ts: int) -> dict:
    """检测 m3u8 流：拉取 playlist，验证状态码，可选下载 TS 片段"""
    base = _get_base_url(url)
    result = {"url": url, "status": "unknown", "detail": "", "ts_count": 0}
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

            # 统计 playlist 中的 TS 片段数
            ts_pattern = re.compile(r"(?!(#|$))(.+\.ts.+|#EXT-X-TARGETDURATION|#EXTINF)", re.IGNORECASE)
            ts_lines = [l.strip() for l in text.splitlines()
                        if l.strip() and not l.strip().startswith("#") and l.strip()]
            if not ts_lines:
                # 也可能是 live 流，没有明确 TS 条目，只有 #EXT-X-ENDLIST 标记才判定为 VOD
                result["ts_count"] = 0
                result["status"] = "ok_no_ts"
                result["detail"] = "live m3u8 (no ENDLIST)"
                return result

            result["ts_count"] = len(ts_lines)

            if min_ts <= 0 or config.check_skip_m3u8:
                # 不要求下载 TS，playlist 能拿到就算通过
                result["status"] = "ok"
                result["detail"] = f"playlist_ok ts_entries={len(ts_lines)}"
                return result

            # 尝试下载前 min_ts 个 TS 片段，验证可访问性
            downloaded = 0
            for line in ts_lines[:min_ts]:
                ts_url = line if line.startswith(("http://", "https://")) else base + line
                try:
                    async with session.get(ts_url, timeout=aiohttp.ClientTimeout(total=timeout)) as ts_resp:
                        if ts_resp.status == 200:
                            downloaded += 1
                except Exception:
                    pass

            if downloaded >= min_ts:
                result["status"] = "ok"
                result["detail"] = f"playlist_ok ts_downloaded={downloaded}/{len(ts_lines)}"
            else:
                result["status"] = "failed"
                result["detail"] = f"ts_failed downloaded={downloaded}/{min_ts}"
    except asyncio.TimeoutError:
        result["status"] = "timeout"
        result["detail"] = f"timeout >{timeout}s"
    except Exception as e:
        result["status"] = "error"
        result["detail"] = str(e)
    return result


async def _check_direct(session: aiohttp.ClientSession, url: str, timeout: float) -> dict:
    """检测直链（非 m3u8）：HEAD 请求确认可达，若不支持 HEAD 则 GET 一小段"""
    result = {"url": url, "status": "unknown", "detail": "", "ts_count": 0}
    stripped = _strip_suffix(url)
    try:
        async with session.head(stripped, timeout=aiohttp.ClientTimeout(total=timeout), allow_redirects=True) as resp:
            if resp.status in (200, 206):
                result["status"] = "ok"
                result["detail"] = f"http_status={resp.status}"
            else:
                result["status"] = "failed"
                result["detail"] = f"http_status={resp.status}"
    except asyncio.TimeoutError:
        result["status"] = "timeout"
        result["detail"] = f"timeout >{timeout}s"
    except Exception:
        # HEAD 失败时降级为 GET 少量字节
        try:
            async with session.get(stripped, timeout=aiohttp.ClientTimeout(total=timeout), allow_redirects=True) as resp:
                if resp.status in (200, 206):
                    _ = await resp.read(4096)  # 只读 4KB
                    result["status"] = "ok"
                    result["detail"] = f"http_status={resp.status} (fallback get)"
                else:
                    result["status"] = "failed"
                    result["detail"] = f"http_status={resp.status}"
        except asyncio.TimeoutError:
            result["status"] = "timeout"
            result["detail"] = f"timeout >{timeout}s"
        except Exception as e:
            result["status"] = "error"
            result["detail"] = str(e)
    return result


async def _check_single(session: aiohttp.ClientSession, url: str, timeout: float, min_ts: int) -> dict:
    """单个 URL 检测入口"""
    if _is_m3u8_url(url):
        return await _check_m3u8(session, url, timeout, min_ts)
    else:
        return await _check_direct(session, url, timeout)


async def check_all(channels: dict) -> dict:
    """
    并发检测所有频道的所有 URL。

    参数:
        channels: {category: {channel_name: [url1, url2, ...]}}

    返回:
        {category: {channel_name: {url: {"status": str, "detail": str}}}}
        status 枚举: "ok" | "failed" | "timeout" | "error" | "empty" | "ok_no_ts"
    """
    semaphore = asyncio.Semaphore(config.check_max_conn)
    results = {}

    async def _worker(cat: str, ch_name: str, url: str) -> tuple:
        async with semaphore:
            r = await _check_single(session, url, config.check_timeout, config.check_min_ts)
            return (cat, ch_name, url, r)

    connector = aiohttp.TCPConnector(limit=config.check_max_conn, ssl=False)
    timeout = aiohttp.ClientTimeout(total=config.check_timeout)

    all_tasks = []
    for cat, ch_dict in channels.items():
        for ch_name, url_list in ch_dict.items():
            for url in url_list:
                clean_url = _strip_suffix(url)
                all_tasks.append(_worker(cat, ch_name, clean_url))

    fail_domains = {}   # {domain: [{url, status, detail}, ...]}

    logger.info(f"开始质量检测，共 {len(all_tasks)} 个 URL，并发数 {config.check_max_conn}，超时 {config.check_timeout}s")

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        tasks = [asyncio.create_task(t) for t in all_tasks]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

    # 聚合结果
    for item in raw_results:
        if isinstance(item, Exception):
            continue
        cat, ch_name, url, r = item
        results.setdefault(cat, {}).setdefault(ch_name, {})[url] = r
        if r["status"] in ("ok", "ok_no_ts"):
            logger.debug(f"  [{ch_name}] OK  {url}  ({r['detail']})")
        else:
            logger.debug(f"  [{ch_name}] FAIL {url}  ({r['detail']})")
            domain = _get_domain(url)
            if domain:
                fail_domains.setdefault(domain, []).append({"url": url, "status": r["status"], "detail": r["detail"]})

    # 统计
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


def filter_dead_urls(channels: dict, check_results: dict) -> dict:
    """
    根据检测结果过滤失效源，返回去重后的 channels。

    保留条件:
      - status 为 "ok" 或 "ok_no_ts"
      - detail 不为空
    """
    filtered = {}
    for cat, ch_dict in channels.items():
        filtered[cat] = {}
        for ch_name, url_list in ch_dict.items():
            valid = []
            for url in url_list:
                cl = _strip_suffix(url)
                r = check_results.get(cat, {}).get(ch_name, {}).get(cl, {})
                if r.get("status") in ("ok", "ok_no_ts"):
                    valid.append(url)
            if valid:
                filtered[cat][ch_name] = valid

    # 统计
    removed = sum(
        len(channels[c][n]) - len(filtered[c][n])
        for c in filtered for n in filtered.get(c, {})
    )
    kept = sum(len(urls) for c in filtered for urls in filtered[c].values())
    logger.info(f"过滤后: 保留 {kept} 个有效源，移除 {removed} 个失效源")
    return filtered
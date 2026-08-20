import re
import asyncio
import requests
import logging
from collections import OrderedDict
from datetime import datetime
import config
import check as quality_checker

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s", handlers=[logging.FileHandler("function.log", "w", encoding="utf-8"), logging.StreamHandler()])


def parse_template(template_file):
    template_channels = OrderedDict()
    current_category = None

    with open(template_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                if "#genre#" in line:
                    current_category = line.split(",")[0].strip()
                    template_channels[current_category] = []
                elif current_category:
                    channel_name = line.split(",")[0].strip()
                    template_channels[current_category].append(channel_name)

    return template_channels


def fetch_epg_id_map():
    """从 config.epg_urls[0] 下载 EPG，解析出 {频道名: id} 映射字典。"""
    import gzip
    import xml.etree.ElementTree as ET
    epg_url = config.epg_urls[0]
    try:
        resp = requests.get(epg_url, timeout=15)
        resp.raise_for_status()
        # .gz 链接需要解压，.xml 链接直接用
        if epg_url.endswith(".gz"):
            xml_data = gzip.decompress(resp.content)
        else:
            xml_data = resp.content
        tree = ET.fromstring(xml_data)
        epg_id_map = {}
        for ch in tree.findall("channel"):
            dn = ch.find("display-name")
            if dn is not None and dn.text:
                eid = ch.get("id", "").strip()
                name = dn.text.strip()
                if eid and name:
                    epg_id_map[name] = eid
        logging.info(f"[EPG映射] 成功加载 {len(epg_id_map)} 个频道 ID")
        return epg_id_map
    except Exception as e:
        logging.warning(f"[EPG映射] 加载失败，将使用默认数字 ID: {e}")
        return {}


def fetch_channels(url):
    channels = OrderedDict()

    try:
        response = requests.get(url)
        response.raise_for_status()
        response.encoding = "utf-8"
        lines = response.text.split("\n")
        current_category = None
        is_m3u = any("#EXTINF" in line for line in lines[:15])
        source_type = "m3u" if is_m3u else "txt"
        logging.info(f"url: {url} 获取成功，判断为{source_type}格式")

        if is_m3u:
            for line in lines:
                line = line.strip()
                if line.startswith("#EXTINF"):
                    match = re.search(r'group-title="(.*?)",(.*)', line)
                    if match:
                        current_category = match.group(1).strip()
                        channel_name = match.group(2).strip()
                        if current_category not in channels:
                            channels[current_category] = []
                elif line and not line.startswith("#"):
                    channel_url = line.strip()
                    if current_category and channel_name:
                        channels[current_category].append((channel_name, channel_url))
        else:
            for line in lines:
                line = line.strip()
                if "#genre#" in line:
                    current_category = line.split(",")[0].strip()
                    channels[current_category] = []
                elif current_category:
                    match = re.match(r"^(.*?),(.*?)$", line)
                    if match:
                        channel_name = match.group(1).strip()
                        channel_url = match.group(2).strip()
                        channels[current_category].append((channel_name, channel_url))
                    elif line:
                        channels[current_category].append((line, ""))
        if channels:
            categories = ", ".join(channels.keys())
            logging.info(f"url: {url} 抓取成功，包含频道分类: {categories}")
    except requests.RequestException as e:
        logging.error(f"url: {url} 抓取失败。 Error: {e}")

    return channels


def _normalize(name: str) -> str:
    s = name.strip()
    s = re.sub(r'[（\[(（\[).+?[）\]\)]', '', s)
    s = re.sub(r'(高清版|超清版|频道|卫视|高清|超清|HD|台)$', '', s)
    while re.search(r'(高清版|超清版|频道|卫视|高清|超清|HD|台)$', s):
        s = re.sub(r'(高清版|超清版|频道|卫视|高清|超清|HD|台)$', '', s)
    s = s.replace('-', '').replace(' ', '')
    return s


def match_channels(template_channels, all_channels):
    matched_channels = OrderedDict()

    for category, channel_list in template_channels.items():
        matched_channels[category] = OrderedDict()
        for channel_name in channel_list:
            norm_target = _normalize(channel_name)
            for online_category, online_channel_list in all_channels.items():
                for online_channel_name, online_channel_url in online_channel_list:
                    if _normalize(online_channel_name) == norm_target:
                        matched_channels[category].setdefault(channel_name, []).append(online_channel_url)

    return matched_channels


def filter_source_urls(template_file):
    template_channels = parse_template(template_file)
    source_urls = config.source_urls

    all_channels = OrderedDict()
    for url in source_urls:
        fetched_channels = fetch_channels(url)
        for category, channel_list in fetched_channels.items():
            if category in all_channels:
                all_channels[category].extend(channel_list)
            else:
                all_channels[category] = channel_list

    matched_channels = match_channels(template_channels, all_channels)

    return matched_channels, template_channels


def is_ipv6(url):
    # ipv6 
    clean_url = url.rstrip("$")
    return re.match(r"^https?://\[[0-9a-fA-F:]+\]", clean_url) is not None


def _print_domain_suggestions(fail_domains: dict):
    """打印检测失败的域名建议列表，供用户考虑加入黑名单"""
    if not fail_domains:
        return
    summary = {}
    for domain, entries in sorted(fail_domains.items(), key=lambda x: -len(x[1])):
        statuses = {}
        for e in entries:
            s = e["status"]
            statuses[s] = statuses.get(s, 0) + 1
        status_str = ", ".join(f"{k}={v}" for k, v in sorted(statuses.items()))
        summary[domain] = f"失败次数={len(entries)}  ({status_str})"

    logging.info("[黑名单建议] 以下域名检测频繁失败，可考虑加入 url_blacklist：")
    for domain, info in summary.items():
        logging.info(f"  {domain}  {info}")


async def async_main():
    """异步主入口：fetch -> check -> write"""
    epg_id_map = fetch_epg_id_map()
    template_file = "demo.txt"
    channels, template_channels = filter_source_urls(template_file)

    if config.enable_quality_check:
        logging.info("[质量检测] 开始...")
        check_results, fail_domains = await quality_checker.check_all(channels)
        channels = quality_checker.filter_dead_urls(channels, check_results)
        _print_domain_suggestions(fail_domains)
        logging.info("[质量检测] 完成")

    updateChannelUrlsM3U(channels, template_channels, epg_id_map)


def updateChannelUrlsM3U(channels, template_channels, epg_id_map=None):
    written_urls = set()
    epg_id_map = epg_id_map or {}

    current_date = datetime.now().strftime("%Y-%m-%d")
    for group in config.announcements:
        for announcement in group["entries"]:
            name = announcement.get("name")
            if name is None or name == "__TIME__":
                name = current_date
            elif isinstance(name, str) and "__TIME__" in name:
                name = name.replace("__TIME__", current_date)
            announcement["name"] = name

    with open("live.m3u", "w", encoding="utf-8") as f_m3u:
        epg_attr = ",".join(chr(34)+epg_url+chr(34) for epg_url in config.epg_urls)
        f_m3u.write(f"#EXTM3U x-tvg-url={epg_attr}\n")

        with open("live.txt", "w", encoding="utf-8") as f_txt:
            for group in config.announcements:
                f_txt.write(f"{group['channel']},#genre#\n")
                for announcement in group["entries"]:
                    f_m3u.write(f"""#EXTINF:-1 tvg-id="{announcement['name']}" tvg-name="{announcement['name']}" tvg-logo="{announcement['logo']}" group-title="{group['channel']}",{announcement['name']}\n""")
                    f_m3u.write(f"{announcement['url']}\n")
                    f_txt.write(f"{announcement['name']},{announcement['url']}\n")

            for category, channel_list in template_channels.items():
                f_txt.write(f"{category},#genre#\n")
                if category in channels:
                    for channel_name in channel_list:
                        if channel_name in channels[category]:
                            sorted_urls = sorted(channels[category][channel_name], key=lambda url: not is_ipv6(url) if config.ip_version_priority == "ipv6" else is_ipv6(url))
                            filtered_urls = []
                            for url in sorted_urls:
                                if url and url not in written_urls and not any(blacklist in url for blacklist in config.url_blacklist):
                                    filtered_urls.append(url)
                                    written_urls.add(url)

                            total_urls = len(filtered_urls)
                            for index, url in enumerate(filtered_urls, start=1):
                                if is_ipv6(url):
                                    url_suffix = f"$LR—IPV6" if total_urls == 1 else f"$LR—IPV6【线路{index}】"
                                else:
                                    url_suffix = f"$LR—IPV4" if total_urls == 1 else f"$LR—IPV4【线路{index}】"
                                if "$" in url:
                                    base_url = url.split("$", 1)[0]
                                else:
                                    base_url = url

                                new_url = f"{base_url}{url_suffix}"

                                tvg_id = epg_id_map.get(channel_name, str(index))
                                f_m3u.write(f"#EXTINF:-1 tvg-id=\"{tvg_id}\" tvg-name=\"{channel_name}\" tvg-logo=\"https://gcore.jsdelivr.net/gh/yuanzl77/TVlogo@master/png/{channel_name}.png\" group-title=\"{category}\",{channel_name}\n")
                                f_m3u.write(new_url + "\n")
                                f_txt.write(f"{channel_name},{new_url}\n")

            f_txt.write("\n")


if __name__ == "__main__":
    asyncio.run(async_main())

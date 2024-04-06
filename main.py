import re
import requests
from config import Config
import time
import concurrent.futures

def parse_template(template_file):
    """
    Parse the template file to extract channel names.
    """
    channels = set()
    with open(template_file, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                channel, _ = line.split(",", 1)
                channels.add(channel)
    return channels

def get_speed(url):
    start = time.time()
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            return int(round((time.time() - start) * 1000))
    except:
        pass
    return float("inf")

def filter_urls(urls):
    with concurrent.futures.ThreadPoolExecutor() as executor:
        speeds = list(executor.map(get_speed, urls))
    return [url for url, speed in zip(urls, speeds) if speed != float("inf")]

def filter_source_urls(template_file):
    """
    Filter source URLs based on the template file.
    """
    template_channels = parse_template(template_file)
    filtered_urls = [url for url in Config.source_urls if url.split(",", 1)[0] in template_channels]
    filtered_channels = {}

    for url in filtered_urls:
        response = requests.get(url)
        if response.status_code == 200:
            lines = response.text.split("\n")
            current_channel = ""
            pattern = r"^(.*?),(?!#genre#)(.*?)$"

            for line in lines:
                line = line.strip()
                if "#genre#" in line:
                    current_channel = line.split(",")[0]
                    if current_channel in template_channels:
                        filtered_channels[current_channel] = {}
                else:
                    match = re.search(pattern, line)
                    if match:
                        channel_name, url = match.groups()
                        if current_channel in template_channels:
                            filtered_channels[current_channel].setdefault(channel_name, []).append(url)
        else:
            print(f"Failed to fetch channel items from the source URL: {url}")

    return {channel: {key: filter_urls(urls) for key, urls in info.items()} for channel, info in filtered_channels.items()}

def updateChannelUrlsM3U(channels):
    with open("live.m3u", "w") as f:
        f.write("#EXTM3U\n")
        for channel, info in channels.items():
            for key, urls in info.items():
                for url in urls:
                    f.write(f"#EXTINF:-1 tvg-id=\"\" tvg-name=\"{key}\" tvg-logo=\"https://gitee.com/yuanzl77/TVBox-logo/raw/main/png/{key}.png\" group-title=\"{channel}\",{key}\n")
                    f.write(url + "\n")
        f.write("\n")

if __name__ == "__main__":
    template_file = "demo.txt"  # Replace "demo.txt" with your actual template file
    channels = filter_source_urls(template_file)
    updateChannelUrlsM3U(channels)

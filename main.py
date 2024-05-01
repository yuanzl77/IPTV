import re
import requests
import config

def parse_template(template_file):
    """
    Parse the template file to extract channel names.
    """
    with open(template_file, "r") as f:
        return [line.split(",")[0].replace("-", "") for line in f if line.strip() and not line.startswith("#")]

def getChannelItems(template_channels, source_urls):
    """
    Get the channel items from the source URLs
    """
    channels = {}
    pattern = r"^(.*?),(?!#genre#)(.*?)$"

    for url in source_urls:
        if url.endswith(".m3u"):
            converted_url = f"https://fanmingming.com/txt?url={url}"
            response = requests.get(converted_url)
        else:
            response = requests.get(url)

        if response.status_code == 200:
            response.encoding = 'utf-8'
            lines = response.text.split("\n")

            for line in lines:
                line = line.strip()
                if "#genre#" in line:
                    current_channel = line.split(",")[0]
                    if current_channel not in channels:
                        channels[current_channel] = {}
                else:
                    match = re.search(pattern, line)
                    if match:
                        for template_channel in template_channels:
                            if re.fullmatch(template_channel, match.group(1)):
                                channels.setdefault(current_channel, {}).setdefault(template_channel, []).append(match.group(2))
                                break
        else:
            print(f"Failed to fetch channel items from the source URL: {url}")

    return channels

def filter_source_urls(template_file):
    """
    Filter source URL.
    """
    template_channels = parse_template(template_file)
    source_urls = [url for url in config.source_urls]
    return getChannelItems(template_channels, source_urls), template_channels

def updateChannelUrlsM3U(channels, template_channels):
    """
    Update the category and channel urls to the final file in M3U format
    """
    with open("live.m3u", "w") as f:
        f.write("#EXTM3U\n")
        f.write("""#EXTINF:-1 tvg-id="1" tvg-name="请阅读" tvg-logo="https://gitee.com/yuanzl77/TVBox-logo/raw/main/mmexport1713580051470.png" group-title="公告",请阅读\n""")
        f.write("https://liuliuliu.tv/api/channels/1997/stream\n")
        f.write("""#EXTINF:-1 tvg-id="1" tvg-name="yuanzl77.github.io" tvg-logo="https://gitee.com/yuanzl77/TVBox-logo/raw/main/mmexport1713580051470.png" group-title="公告",yuanzl77.github.io\n""")
        f.write("https://liuliuliu.tv/api/channels/233/stream\n")
        for channel in template_channels:
            if channel in channels:
                for key, urls in channels[channel].items():
                    for url in urls:
                        if url:
                            f.write(f"#EXTINF:-1 tvg-id=\"\" tvg-name=\"{key}\" tvg-logo=\"https://gitee.com/yuanzl77/TVBox-logo/raw/main/png/{key}.png\" group-title=\"{channel}\",{key}\n")
                            f.write(url + "\n")
        f.write("\n")

if __name__ == "__main__":
    template_file = "demo.txt"
    channels, template_channels = filter_source_urls(template_file)
    updateChannelUrlsM3U(channels, template_channels)

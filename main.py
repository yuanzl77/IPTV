import re
import requests
import urllib.parse
import ipaddress
import config

def is_ipv6(url):
    """
    Check if the url is ipv6
    """
    try:
        host = urllib.parse.urlparse(url).hostname
        ipaddress.IPv6Address(host)
        return True
    except ValueError:
        return False

def checkUrlIPVType(url):
    """
    Check if the url is compatible with the ipv type in the config
    """
    ipv_type = getattr(config, "ipv_type", "ipv4")
    if ipv_type == "ipv4":
        return not is_ipv6(url)
    elif ipv_type == "ipv6":
        return is_ipv6(url)
    else:
        return True

def parse_template(template_file):
    """
    Parse the template file to extract channel names.
    """
    channels = []
    with open(template_file, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                channel, _ = line.split(",", 1)
                # Remove special characters like "-"
                channel = channel.replace("-", "")  
                channels.append(channel)
    return channels

def getChannelItems(template_channels, source_urls):
    """
    Get the channel items from the source URLs
    """
    channels = {}
    current_channel = None

    for url in source_urls:
        # Check if the URL ends with ".m3u"
        if url.endswith(".m3u"):
            # Convert .m3u to .txt using the provided service
            converted_url = f"https://fanmingming.com/txt?url={url}"
            # Get the content from the converted URL
            response = requests.get(converted_url)
        else:
            # Get the content from the original source URL
            response = requests.get(url)

        # Check if the request was successful
        if response.status_code == 200:
            # Extract channel items from the response text
            lines = response.text.split("\n")
            pattern = r"^(.*?),(?!#genre#)(.*?)$"

            for line in lines:
                line = line.strip()
                if "#genre#" in line:
                    # This is a new channel, create a new key in the dictionary.
                    current_channel = line.split(",")[0]
                    if current_channel not in channels:
                        channels[current_channel] = {}
                else:
                    # This is a url, add it to the list of urls for the current channel.
                    match = re.search(pattern, line)
                    if match:
                        # Check if the channel name matches any of the template channels
                        matched_channel = None
                        for template_channel in template_channels:
                            if re.fullmatch(template_channel, match.group(1)):
                                matched_channel = template_channel
                                break
                        if matched_channel:
                            if matched_channel not in channels[current_channel]:
                                channels[current_channel][matched_channel] = [match.group(2)]
                            else:
                                channels[current_channel][matched_channel].append(match.group(2))
        else:
            print(f"Failed to fetch channel items from the source URL: {url}")

    return channels

def filter_source_urls(template_file):
    """
    Filter source URLs based on the template file and the specified IP version.
    """
    template_channels = parse_template(template_file)
    source_urls = [url for url in config.source_urls if checkUrlIPVType(url)]

    channels = getChannelItems(template_channels, source_urls)  # Pass source_urls to getChannelItems

    return channels, template_channels

def updateChannelUrlsM3U(channels, template_channels):
    """
    Update the category and channel urls to the final file in M3U format
    """
    with open("live.m3u", "w") as f:
        f.write("#EXTM3U\n")
        f.write("""#EXTINF:-1 tvg-id="1" tvg-name="请阅读" tvg-logo="https://gitee.com/yuanzl77/TVBox-logo/raw/main/mmexport1713580051470.png" group-title="公告",请阅读\n""")
        f.write("http://175.10.88.166:3000/udp/239.76.253.135:9000\n")
        f.write("""#EXTINF:-1 tvg-id="1" tvg-name="yuanzl77.github.io" tvg-logo="https://gitee.com/yuanzl77/TVBox-logo/raw/main/mmexport1713580051470.png" group-title="公告",yuanzl77.github.io\n""")
        f.write("https://liuliuliu.tv/api/channels/233/stream\n")
        for channel in template_channels:
            if channel in channels:
                for key, urls in channels[channel].items():
                    for url in urls:
                        if url is not None:
                            f.write(f"#EXTINF:-1 tvg-id=\"\" tvg-name=\"{key}\" tvg-logo=\"https://gitee.com/yuanzl77/TVBox-logo/raw/main/png/{key}.png\" group-title=\"{channel}\",{key}\n")
                            f.write(url + "\n")
        f.write("\n")

if __name__ == "__main__":
    template_file = "demo.txt"
    channels, template_channels = filter_source_urls(template_file)
    updateChannelUrlsM3U(channels, template_channels)

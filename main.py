import re
import requests
from config import Config

def getChannelItems():
    """
    Get the channel items from the source URLs
    """
    channels = {}
    current_channel = None

    for url in Config.source_urls:
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
                        if match.group(1) not in channels[current_channel]:
                            channels[current_channel][match.group(1)] = [match.group(2)]
                        else:
                            channels[current_channel][match.group(1)].append(match.group(2))
        else:
            print(f"Failed to fetch channel items from the source URL: {url}")

    return channels

def updateChannelUrlsM3U(channels, template_channels):
    """
    Update the category and channel urls to the final file in M3U format
    """
    with open("live.m3u", "w") as f:
        f.write("#EXTM3U\n")
        for channel in template_channels:
            if channel in channels:
                for key, urls in channels[channel].items():
                    for url in urls:
                        if url is not None:
                            f.write(f"#EXTINF:-1 tvg-id=\"\" tvg-name=\"{key}\" tvg-logo=\"https://gitee.com/yuanzl77/TVBox-logo/raw/main/png/{key}.png\" group-title=\"{channel}\",{key}\n")
                            f.write(url + "\n")
        f.write("\n")

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
                channels.append(channel)
    return channels

def filter_source_urls(template_file):
    """
    Filter source URLs based on the template file.
    """
    channels = getChannelItems()
    template_channels = parse_template(template_file)

    return channels, template_channels

if __name__ == "__main__":
    template_file = "demo.txt"
    channels, template_channels = filter_source_urls(template_file)
    updateChannelUrlsM3U(channels, template_channels)

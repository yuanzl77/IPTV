import re
import requests
from config import Config

def getChannelItems():
    """
    Get the channel items from the source URLs
    """
    channels = {}

    for url in Config.source_urls:
        # Get the content from each source URL
        response = requests.get(url)

        # Check if the request was successful
        if response.status_code == 200:
            # Extract channel items from the response text
            lines = response.text.split("\n")
            current_channel = ""
            pattern = r"^(.*?),(?!#genre#)(.*?)$"

            for line in lines:
                line = line.strip()
                if "#genre#" in line:
                    # This is a new channel, create a new key in the dictionary.
                    current_channel = line.split(",")[0]
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

def updateChannelUrlsM3U(channels):
    """
    Update the category and channel urls to the final file in M3U format
    """
    with open("live.m3u", "w") as f:
        f.write("#EXTM3U\n")
        for channel, info in channels.items():
            for key, urls in info.items():
                for url in urls:
                    if url is not None:
                        f.write(f"#EXTINF:-1 tvg-id=\"\" tvg-name=\"{key}\" tvg-logo=\"https://gitee.com/yuanzl77/TVBox-logo/raw/main/png/{key}.png\" group-title=\"{channel}\",{key}\n")
                        f.write(url + "\n")
        f.write("\n")

if __name__ == "__main__":
    # Call the function to get channel items
    channels = getChannelItems()
    # Call the function to update channel URLs in M3U format
    updateChannelUrlsM3U(channels)

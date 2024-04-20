import requests

# 获取文件内容并指定编码为 UTF-8
url = "http://router.bopop.buzz:9999/new/mdlive.txt"
response = requests.get(url)
response.encoding = 'utf-8'

# 检查是否成功获取内容
if response.status_code == 200:
    # 逐行查找匹配的内容
    lines = response.text.split('\n')
    is_in_cctv_section = False
    channels = {}
    for line in lines:
        if "央卫,#genre#" in line:
            is_in_cctv_section = True
            continue 
        elif "CCTV" in line and is_in_cctv_section:
            parts = line.split(",")
            if len(parts) >= 2:
                channel_name = parts[0].strip()
                channel_url = parts[1].strip()
                channels[channel_name] = channel_url
        elif "CCTV" not in line and is_in_cctv_section:
            break  # 央视频道部分结束

    # 检查是否找到了所需的信息
    if channels:
        # 写入到本地文件
        with open("./直播/cctv.txt", "w", encoding="utf-8") as f:
            f.write("请阅读 yuanzl77.github.io - LR\n\n央视频道,#genre#\n")
            for channel, url in channels.items():
                f.write("{},{}\n".format(channel, url))
        print("央视频道的频道信息已写入到 cctv.txt")
    else:
        print("未找到匹配的频道信息")
else:
    print("获取文件内容失败")

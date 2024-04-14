import requests
import re

# 获取文件内容
url = "http://router.bopop.buzz:9999/new/mdlive.txt"
response = requests.get(url)

# 检查是否成功获取内容
if response.status_code == 200:
    # 使用正则表达式匹配央视频道中的CCTV1和CCTV2
    pattern = re.compile(r'央卫,#genre#\nCCTV1,(.*?)\nCCTV2,(.*?)\n', re.S)
    match = pattern.search(response.text)
    if match:
        cctv1_url = match.group(1)
        cctv2_url = match.group(2)
        
        # 写入到本地文件
        with open("cs.txt", "w", encoding="utf-8") as f:
            f.write("央视频道,#genre#\n")
            f.write("CCTV1,{}\n".format(cctv1_url))
            f.write("CCTV2,{}\n".format(cctv2_url))
        print("CCTV1 和 CCTV2 频道信息已写入到 cctv_channels.txt")
    else:
        print("未找到匹配的频道信息")
else:
    print("获取文件内容失败")

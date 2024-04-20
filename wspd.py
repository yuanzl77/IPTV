from datetime import datetime, timedelta

def generate_url(channel_name, date):
    base_url = "http://120.79.4.185/md"
    full_url = f"{base_url}{date}.php?id={channel_name.lower()}"
    return full_url

if __name__ == "__main__":
    today = datetime.now() 
    date = today.strftime("%m%d")
    
    channels = [
        "北京卫视:bjws","天津卫视:tjws","东方卫视:dfws","重庆卫视:cqws","黑龙江卫视:hljws","辽宁卫视:lnws","河北卫视:hbws","山东卫视:sdws","安徽卫视:ahws","湖北卫视:hubws","湖南卫视:hunws","江西卫视:jxws","江苏卫视:jsws","浙江卫视:zjws","东南卫视:dnws","广东卫视:gdws","深圳卫视:szws","广西卫视:gxws","贵州卫视:gzws","四川卫视:scws","新疆卫视:xjws","海南卫视:hinws","兵团卫视:btws","河南卫视:hnws"
 ]
 
with open("./直播/wspd.txt", "w") as f:
        f.write("请阅读 yuanzl77.github.io - LR\n\n卫视频道,#genre#\n")
        for channel in channels:
            channel_name, identifier = channel.split(":")
            generated_url = generate_url(identifier, date)
            f.write(f"{channel_name},{generated_url}\n")

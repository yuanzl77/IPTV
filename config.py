# ── IP 优先级 ───────────────────────────────────────────────────────
# "ipv6" = IPv6 地址优先排在前面；"ipv4" = IPv4 优先
ip_version_priority = "ipv6"

# ── 数据源列表 ───────────────────────────────────────────────────────
# 每个 URL 都是一个 IPTV 直播源文件（支持 m3u 或 txt 格式）
# main.py 会依次请求这些地址，提取频道名和播放地址
source_urls = [
    "http://45.192.97.170:6001/txt",
    "https://tvlive.yuan77.workers.dev/xymm",
    "http://47.100.209.208:20002",
    "https://raw.githubusercontent.com/YueChan/Live/refs/heads/main/GNTV.m3u",
    "https://raw.githubusercontent.com/Kimentanm/aptv/refs/heads/master/m3u/iptv.m3u",
    "https://raw.githubusercontent.com/Guovin/iptv-api/refs/heads/gd/output/result.txt",
    "https://raw.githubusercontent.com/Guovin/iptv-api/refs/heads/gd/output/ipv6/result.txt",
    "https://live.zbds.top/tv/iptv6.txt",
    "https://live.zbds.top/tv/iptv4.txt"
]

# ── URL 黑名单 ───────────────────────────────────────────────────────
# 包含以下任意子串的播放地址会被自动过滤掉
# 用途：屏蔽已知失效、广告插播、低质量或不稳定的源
url_blacklist = [
    "epg.pw/stream/",
    "45.192.97.170:8880"
]

# ── 公告条目 ────────────────────────────────────────────────────────
# 这些条目会写在直播源文件的最前面，位于所有频道之前
# 用途：展示公告信息，如主播链接、更新时间等
#
# name 的三种写法：
#   None                  → 自动替换为当天日期（如 "2026-08-12"）
#   "__TIME__"             → 同上，也替换为当天日期
#   "更新时间：__TIME__"   → 替换为 "更新时间：2026-08-12"
#
# channel   → 该公告在 live.txt 中的分类名（#genre# 分组）
# url       → 播放地址
# logo      → 频道图标 URL（m3u 中 tvg-logo 属性）
announcements = [
    {
        "channel": "公告-yuanzl77",
        "entries": [
            {"name": "www.776512.xyz", "url": "https://liuliuliu.tv/api/channels/233/stream", "logo": "https://ts2.tc.mm.bing.net/th/id/OIP-C.2CL9t6gI2-c5n5DI9Sl_0QAAAA?rs=1&pid=ImgDetMain&o=7&rm=3"},
            {"name": "更新时间：__TIME__", "url": "https://gitlab.com/lr77/IPTV/-/raw/main/%E4%B8%BB%E8%A7%92.mp4", "logo": "https://ts2.tc.mm.bing.net/th/id/OIP-C.2CL9t6gI2-c5n5DI9Sl_0QAAAA?rs=1&pid=ImgDetMain&o=7&rm=3"},
        ]
    }
]

# ── EPG 电子节目单 ───────────────────────────────────────────────────────
# 同时用于：x-tvg-url 属性 + EPG 频道 ID 映射（{频道名: tvg-id}）
# 用途：让支持 EPG 的播放器（如 TiviMate、Kodi）显示节目指南
# 建议将最全面的源放在最后，作为保底
epg_urls = [
    "http://e.erw.cc/e.xml.gz",
    "https://github.776512.xyz/https://raw.githubusercontent.com/kuke31/xmlgz/main/e.xml.gz",
    "https://github.776512.xyz/https://raw.githubusercontent.com/atsushi444/iptv-epg/refs/heads/main/EPG.xml",
]

# ── 质量检测配置 ───────────────────────────────────────────────────────
# enable_quality_check  : True=启用（测活后过滤失效源），False=跳过直接输出
# check_timeout         : 单个 URL 检测超时时间（秒），超时视为失效
# check_max_conn        : 最大并发检测数，调高可加速但更占带宽
# check_min_ts          : m3u8 检测要求至少成功下载几个 TS 片段才判定有效（>=1 即认为有效）
# check_skip_m3u8       : True=只检查 HTTP 状态码，不下载 TS 片段（更快但精度略低）
enable_quality_check = True
check_timeout    = 3.5
check_max_conn   = 50
check_min_ts     = 3
check_skip_m3u8  = False

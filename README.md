# 本分播客库（podcast-lib）

「本分播客机」（app.benfen.net/podcast/）的节目库：策展播客名单 + 每日两次自动消化。

- 策展名单在 `shows.txt`（分类 | 节目名 | RSS 地址），改名单只改它。
- `collect.py` 逐个拉取 RSS：验活、提取节目信息与最新 30 集元数据，压成 `shows.json`。
- 某个 feed 失败时保留上一轮数据（标 stale），绝不用空覆盖好数据。
- 发布（纯静态）：https://benfennet.github.io/podcast-lib/shows.json

节目版权归各节目方所有；本库只整理其公开订阅地址与元数据。

#!/usr/bin/env python3
"""本分播客库：把策展名单（shows.txt）里的 RSS 逐个消化成一份小名单 out/shows.json。

设计（与 radio-verified 同一套纪律）：
- 每台只留最新 EP_KEEP 集的元数据（标题/日期/时长/音频地址/简介摘要），
  原始 feed 动辄几 MB，消化后整库只有几百 KB，播客机打开秒读。
- 某个 feed 本轮拉不到/解析失败：保留上一轮的旧数据（标记 stale），绝不用空覆盖好数据。
- 纯静态发布到 GitHub Pages：https://benfennet.github.io/podcast-lib/shows.json
"""
import hashlib
import html
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import timezone
from email.utils import parsedate_to_datetime

import requests

EP_KEEP = 30
UA = {"User-Agent": "benfen-podcast-lib/1.0 (+https://benfen.net)"}
NS = {"itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd"}


def strip_tags(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def parse_duration(v: str) -> int:
    if not v:
        return 0
    v = v.strip()
    if v.isdigit():
        return int(v)
    parts = v.split(":")
    try:
        nums = [int(float(p)) for p in parts]
    except ValueError:
        return 0
    sec = 0
    for n in nums:
        sec = sec * 60 + n
    return sec


def digest(feed_url: str) -> dict:
    r = requests.get(feed_url, headers=UA, timeout=40)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    ch = root.find("channel")
    if ch is None:
        raise ValueError("no channel")

    def txt(el, path):
        # 必须带 NS 找：itunes:duration/itunes:author 这类带前缀的标签，不带命名空间永远找不到
        #（2026-10-24 实锤：八个节目时长全 0 就是它）。无前缀路径带 NS 找也不受影响。
        n = el.find(path, NS) if el is not None else None
        return (n.text or "").strip() if n is not None and n.text else ""

    img = ""
    im = ch.find("itunes:image", NS)
    if im is not None:
        img = im.get("href") or ""
    if not img:
        img = txt(ch, "image/url")

    eps = []
    for it in ch.findall("item"):
        enc = it.find("enclosure")
        audio = (enc.get("url") or "").strip() if enc is not None else ""
        if not audio:
            continue
        guid = txt(it, "guid") or audio
        date_iso = ""
        raw_date = txt(it, "pubDate")
        if raw_date:
            try:
                dt = parsedate_to_datetime(raw_date)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                date_iso = dt.astimezone(timezone.utc).strftime("%Y-%m-%d")
            except Exception:
                date_iso = ""
        desc = strip_tags(txt(it, "description") or txt(it, "itunes:summary"))[:160]
        eps.append({
            "guid": guid,
            "title": strip_tags(txt(it, "title")),
            "date": date_iso,
            "dur": parse_duration(txt(it, "itunes:duration")),
            "audio": audio,
            "desc": desc,
        })
        if len(eps) >= EP_KEEP:
            break

    if not eps:
        raise ValueError("no episodes with audio")
    return {
        "title": strip_tags(txt(ch, "title")),
        "author": strip_tags(txt(ch, "itunes:author") or txt(ch, "managingEditor")),
        "desc": strip_tags(txt(ch, "description"))[:220],
        "img": img,
        "eps": eps,
    }


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    out_dir = os.path.join(here, "out")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "shows.json")

    prev = {}
    if os.path.exists(out_path):
        try:
            for s in json.load(open(out_path)).get("shows", []):
                prev[s["feed"]] = s
        except Exception:
            prev = {}

    shows = []
    for line in open(os.path.join(here, "shows.txt"), encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) != 3:
            print("跳过坏行:", line, file=sys.stderr)
            continue
        cat, _name, feed = parts
        sid = hashlib.md5(feed.encode()).hexdigest()[:10]
        try:
            d = digest(feed)
            shows.append({"id": sid, "feed": feed, "cat": cat, **d,
                          "n_eps": len(d["eps"]), "stale": False})
            print(f"OK   {d['title']}（{cat}，{len(d['eps'])} 集）")
        except Exception as e:
            old = prev.get(feed)
            if old:
                old = dict(old)
                old["stale"] = True
                shows.append(old)
                print(f"STALE {old.get('title')}（本轮失败，保留旧数据：{e}）")
            else:
                print(f"FAIL {feed}（无旧数据可用：{e}）", file=sys.stderr)

    if not shows:
        print("全部失败，保留旧 out 不覆盖", file=sys.stderr)
        return 1
    payload = {"v": 1, "shows": shows}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    size = os.path.getsize(out_path)
    print(f"shows.json：{len(shows)} 个节目，{size // 1024} KB")
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        rows = "\n".join(
            f"<li>{html.escape(s['cat'])} · {html.escape(s['title'])}"
            f"（最新 {s['n_eps']} 集{'，本轮验活失败、暂用旧数据' if s.get('stale') else ''}）</li>"
            for s in shows)
        f.write(f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>本分播客库</title></head>
<body style="font-family:serif;max-width:640px;margin:40px auto;padding:0 16px;line-height:1.7">
<h1>本分播客库</h1>
<p>策展播客名单，每日两次消化各家订阅：验活、只留最新 {EP_KEEP} 集，压成一份小名单给播客机读。</p>
<p>数据地址（纯静态 JSON，欢迎取用）：<a href="./shows.json">shows.json</a>（{len(shows)} 个节目，{size // 1024} KB）</p>
<ul>{rows}</ul>
<p style="color:#888">节目版权归各节目方所有；本库只整理其公开订阅地址与元数据。</p>
</body></html>""")
    return 0


if __name__ == "__main__":
    sys.exit(main())

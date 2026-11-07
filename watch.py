"""每天自己看一小时 B 站：选题 → 下载 → 转写 → 抽帧 → 落成一份可读的笔记。

用法：
  python watch.py --plan        # 只看今天挑了什么，不下载
  python watch.py               # 全流程（约 1 小时视频量）
  python watch.py --minutes 45
"""
import datetime
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

import bili
import dig

OUT_ROOT = os.environ.get("BILI_OUT", os.path.join(os.path.dirname(os.path.abspath(__file__)), "out"))
SEEN = os.path.join(OUT_ROOT, "_已看.txt")

KW = [
    "AI 最新 解读",
    "AI Agent 实测",
    "大模型 评测 对比",
    "AI 编程 工具",
    "具身智能 机器人",
    "大模型 论文 解读",
    "AI 创业 落地",
    "AI 手机 端侧模型",
]
BAD = ["合集", "全集", "教程", "全套", "零基础", "小白", "就业", "薪资", "训练营",
       "七天", "保姆级", "毕设", "速成", "免费", "干货", "码农", "包会", "万字",
       "涨停", "股票", "龙头", "游资", "打板", "复盘", "概念股", "利好",
       "竞赛", "青少年", "大赛", "考研", "招生", "vlog", "Vlog", "日常生活"]
MIN_PLAY = 2500
MAX_AGE_DAYS = 180


def dur_sec(s):
    if not s:
        return 0
    parts = [int(x) for x in str(s).split(":")]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return int(parts[0])


def seen():
    if not os.path.exists(SEEN):
        return set()
    with open(SEEN, "r", encoding="utf-8") as f:
        return set(x.strip() for x in f if x.strip())


def mark(bvid):
    os.makedirs(OUT_ROOT, exist_ok=True)
    with open(SEEN, "a", encoding="utf-8") as f:
        f.write(bvid + "\n")


def pick(minutes=60, want=4):
    day = datetime.date.today().toordinal()
    kws = [KW[(day + i) % len(KW)] for i in range(3)]
    have = seen()
    cand = []
    for kw in kws:
        try:
            for r in bili.search(kw, 12):
                if not r["bvid"] or r["bvid"] in have:
                    continue
                t = r["title"]
                if any(b in t for b in BAD):
                    continue
                d = dur_sec(r["duration"])
                if d < 180 or d > 2700:          # 3–45 分钟
                    continue
                if any(c["bvid"] == r["bvid"] for c in cand):
                    continue
                if (r.get("play") or 0) < MIN_PLAY:
                    continue
                # 只留 45 天内的：搜索索引里混着两年前的旧视频
                import time as _t
                if (r.get("pubdate") or 0) < _t.time() - MAX_AGE_DAYS * 86400:
                    continue
                r["sec"] = d
                cand.append(r)
        except SystemExit as e:
            print("  搜索失败，跳过:", kw, e)
    cand.sort(key=lambda x: ((x.get("pubdate") or 0), (x.get("play") or 0)), reverse=True)
    chosen, total = [], 0
    for r in cand:
        if len(chosen) >= want:
            break
        if total + r["sec"] > minutes * 60 + 300:
            continue
        chosen.append(r)
        total += r["sec"]
    return chosen, total


def one(r):
    path = bili.download(r["bvid"])
    base = os.path.splitext(os.path.basename(path))[0]
    outdir = os.path.join(os.path.dirname(path), base + "_dig")
    os.makedirs(outdir, exist_ok=True)
    wav = dig.audio(path, outdir)
    text = dig.transcribe(wav, "small", "zh")
    tpath = os.path.join(outdir, "transcript.txt")
    with open(tpath, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    frames = dig.frames(path, outdir, 4)
    return {"path": path, "transcript": tpath, "text": text,
            "frames": [p for p, _ in frames]}


def main():
    minutes = 60
    args = sys.argv[1:]
    if "--minutes" in args:
        minutes = int(args[args.index("--minutes") + 1])
    plan_only = "--plan" in args

    print("=== 今天挑的 ===")
    chosen, total = pick(minutes)
    for r in chosen:
        print("%s | %dmin | %s | %s" % (r["bvid"], r["sec"] // 60, r["author"], r["title"]))
    print("合计 %d 分钟 / %d 个" % (total // 60, len(chosen)))
    if plan_only or not chosen:
        return

    done = []
    for i, r in enumerate(chosen, 1):
        print("\n--- %d/%d %s ---" % (i, len(chosen), r["bvid"]), flush=True)
        try:
            info = one(r)
            info.update({"meta": r})
            done.append(info)
            mark(r["bvid"])
        except SystemExit as e:
            print("  跳过（%s）" % e)

    today = datetime.date.today()
    outdir = os.path.join(OUT_ROOT, today.strftime("%Y-%m"), )
    os.makedirs(outdir, exist_ok=True)
    md = os.path.join(outdir, today.strftime("%Y-%m-%d") + ".md")
    n = 2
    while os.path.exists(md):
        md = os.path.join(outdir, today.strftime("%Y-%m-%d") + "-%d.md" % n)
        n += 1
    with open(md, "w", encoding="utf-8") as f:
        f.write("# %s 看的一小时 B 站\n\n" % today.strftime("%Y-%m-%d"))
        f.write("合计 %d 个视频 / %d 分钟。\n\n" % (len(done), total // 60))
        for d in done:
            m = d["meta"]
            f.write("## %s\n\n" % m["title"])
            f.write("- UP：%s\n- 时长：%d 分钟\n- 播放：%s\n- 链接：https://www.bilibili.com/video/%s\n"
                    % (m["author"], m["sec"] // 60, m.get("play"), m["bvid"]))
            f.write("- 原片：`%s`\n- 稿子：`%s`\n" % (d["path"], d["transcript"]))
            for p in d["frames"]:
                f.write("- 帧：`%s`\n" % p)
            f.write("\n<details><summary>转写全文</summary>\n\n```\n")
            f.write(d["text"][:12000])
            f.write("\n```\n\n</details>\n\n")
    print("\n笔记:", md)


if __name__ == "__main__":
    main()

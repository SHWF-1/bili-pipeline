"""B 站免登录取流的最小工具：搜索 / 拉元数据 / 下 mp4。

用法：
  python bili.py search "AI 手机" 8
  python bili.py dl BV1GJ411x7h7
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")
HDR = {
    "User-Agent": UA,
    "Referer": "https://www.bilibili.com/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
}
OUT = r"D:\AI\DS计划\.build\bili"


def get_json(url, tries=4):
    """B 站对密集请求会回 412，退避重试。"""
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=HDR)
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2.5 * (i + 1))
    raise SystemExit("request failed after %d tries: %s" % (tries, last))


def search(kw, n=8):
    q = urllib.parse.quote(kw)
    j = get_json("https://api.bilibili.com/x/web-interface/search/type"
                 "?search_type=video&keyword=%s&page=1" % q)
    if j.get("code") != 0:
        print("search failed:", j.get("code"), j.get("message"))
        return []
    out = []
    for it in (j["data"].get("result") or [])[:n]:
        title = (it.get("title") or "").replace('<em class="keyword">', "").replace("</em>", "")
        out.append({
            "bvid": it.get("bvid"),
            "title": title,
            "author": it.get("author"),
            "duration": it.get("duration"),
            "play": it.get("play"),
            "pubdate": it.get("pubdate"),
        })
    return out


def meta(bvid):
    j = get_json("https://api.bilibili.com/x/web-interface/view?bvid=" + bvid)
    if j.get("code") != 0:
        raise SystemExit("view failed: %s %s" % (j.get("code"), j.get("message")))
    d = j["data"]
    return {"bvid": bvid, "cid": d["cid"], "title": d["title"],
            "duration": d["duration"], "owner": d["owner"]["name"],
            "desc": d.get("desc", "")}


def stream_url(bvid, cid):
    url = ("https://api.bilibili.com/x/player/playurl?bvid=%s&cid=%s&qn=16&fnval=1&fourk=0"
           % (bvid, cid))
    j = get_json(url)
    if j.get("code") != 0:
        raise SystemExit("playurl failed: %s %s" % (j.get("code"), j.get("message")))
    durl = j["data"].get("durl") or []
    if not durl:
        raise SystemExit("no durl (video may need login)")
    return durl[0]["url"], durl[0].get("size", 0)


def download(bvid):
    m = meta(bvid)
    print("title:", m["title"])
    print("owner:", m["owner"], "duration:", m["duration"], "sec")
    url, size = stream_url(bvid, m["cid"])
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, bvid + ".mp4")
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Referer": "https://www.bilibili.com/"})
    got = 0
    with urllib.request.urlopen(req, timeout=60) as r, open(path, "wb") as f:
        while True:
            chunk = r.read(262144)
            if not chunk:
                break
            f.write(chunk)
            got += len(chunk)
            if got % (2 << 20) < 262144:
                print("  %.1f / %.1f MB" % (got / 1048576, size / 1048576))
    print("saved:", path, os.path.getsize(path), "bytes")
    return path


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "search"
    if cmd == "search":
        kw = sys.argv[2] if len(sys.argv) > 2 else "AI"
        n = int(sys.argv[3]) if len(sys.argv) > 3 else 8
        for r in search(kw, n):
            print("%s | %s | %s | %s | %s" % (r["bvid"], r["duration"], r["play"],
                                              r["author"], r["title"]))
    elif cmd == "dl":
        download(sys.argv[2])
    else:
        print("unknown command:", cmd)

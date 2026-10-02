"""네이버 증권 테마 분류(테마 → 종목) 수집. GitHub Actions에서 실행.

결과: data/ref/naver_themes.json
  {"updated": "...", "themes": {"테마명": {"no": 123, "codes": ["005930", ...]}}, "names": {"005930": "삼성전자"}}
"""
import json
import os
import re
import time
import urllib.request
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"}


def fetch(url):
    for i in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                raw = r.read()
            for enc in ("euc-kr", "cp949", "utf-8"):
                try:
                    return raw.decode(enc)
                except UnicodeDecodeError:
                    pass
            return raw.decode("utf-8", "ignore")
        except Exception as e:
            print("retry", url, e)
            time.sleep(2 * (i + 1))
    return ""


def main():
    themes = {}
    debug = {}
    for page in range(1, 20):
        html = fetch(f"https://finance.naver.com/sise/theme.naver?&page={page}")
        found = re.findall(r'sise_group_detail\.naver\?type=theme&(?:amp;)?no=(\d+)"[^>]*>([^<]+)</a>', html)
        new = [(no, name.strip()) for no, name in found if name.strip() not in themes]
        if page == 1:
            print("page1 len", len(html), "found", len(found))
            i = html.find("group_detail")
            debug["page1_len"] = len(html)
            debug["page1_found"] = len(found)
            debug["sample"] = html[max(0, i - 300):i + 300] if i >= 0 else html[:1500]
        if not new:
            break
        for no, name in new:
            themes[name] = {"no": int(no), "codes": []}
        time.sleep(0.3)
    print("themes", len(themes))
    names = {}
    for name, t in themes.items():
        html = fetch(f"https://finance.naver.com/sise/sise_group_detail.naver?type=theme&no={t['no']}")
        for code, sname in re.findall(r'/item/main\.naver\?code=(\d{6})"[^>]*>([^<]+)</a>', html):
            if code not in t["codes"]:
                t["codes"].append(code)
            names[code] = sname.strip()
        time.sleep(0.2)
    out = {"updated": datetime.now(timezone(timedelta(hours=9))).isoformat(timespec="seconds"),
           "themes": themes, "names": names, "debug": debug}
    os.makedirs(os.path.join(ROOT, "data", "ref"), exist_ok=True)
    with open(os.path.join(ROOT, "data", "ref", "naver_themes.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print("stocks", len(names))


if __name__ == "__main__":
    main()

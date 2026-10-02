"""네이버 증권 테마 분류(테마 → 종목) 수집. GitHub Actions에서 실행.

결과: data/ref/naver_themes.json
  {"updated": "...", "themes": {"테마명": {"no": 586, "desc": "...", "codes": [...]}}, "names": {"005930": "삼성전자"},
   "reasons": {"테마no:종목코드": "네이버 테마 편입 사유"}}
"""
import json
import os
import time
import urllib.request
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
      "Referer": "https://m.stock.naver.com/"}


def get(url):
    for i in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            print("retry", url, e)
            time.sleep(2 * (i + 1))
    return {}


def main():
    groups = []
    for page in range(1, 30):
        d = get(f"https://m.stock.naver.com/api/stocks/theme?page={page}&pageSize=100")
        g = d.get("groups") or []
        groups += g
        if len(g) < 100:
            break
        time.sleep(0.3)
    print("themes", len(groups))
    themes, names, reasons = {}, {}, {}
    for g in groups:
        no, tname = g["no"], g["name"]
        codes, desc = [], ""
        for page in range(1, 10):
            d = get(f"https://m.stock.naver.com/api/stocks/theme/{no}?page={page}&pageSize=100")
            desc = desc or d.get("themeDescription") or ""
            info = d.get("themeItemInfoMap") or {}
            st = d.get("stocks") or []
            for s in st:
                c = s.get("itemCode")
                if not c:
                    continue
                codes.append(c)
                names[c] = s.get("stockName", "")
                r = info.get(c)
                if isinstance(r, dict):
                    r = r.get("description") or r.get("reason") or json.dumps(r, ensure_ascii=False)
                if r:
                    reasons[f"{no}:{c}"] = str(r)[:300]
            if len(st) < 100:
                break
            time.sleep(0.2)
        themes[tname] = {"no": no, "desc": desc[:300], "codes": codes}
        time.sleep(0.15)
    out = {"updated": datetime.now(timezone(timedelta(hours=9))).isoformat(timespec="seconds"),
           "themes": themes, "names": names, "reasons": reasons}
    os.makedirs(os.path.join(ROOT, "data", "ref"), exist_ok=True)
    with open(os.path.join(ROOT, "data", "ref", "naver_themes.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print("stocks", len(names), "reasons", len(reasons))


if __name__ == "__main__":
    main()

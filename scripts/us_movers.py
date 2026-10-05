"""전날 밤 미국 개별 종목 급등 상위 (지수만 보고 놓치는 재료 찾기용). GitHub Actions 06:30 에 실행.

결과: data/ref/us_movers.json
  {"updated": ..., "gainers": [{"sym","name","chg","cap_b"}], "losers": [...], "watch": [미국 짝 종목 중 ±3% 이상]}
07:00 예측 작업은 gainers 상위(시총 20억 달러 이상)의 상승 이유를 영어 뉴스로 찾아 국내 테마에 연결한다.
"""
import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"}


def screener(sid, n=100):
    url = f"https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?scrIds={sid}&count={n}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
            q = json.loads(r.read().decode("utf-8"))["finance"]["result"][0]["quotes"]
    except Exception as e:
        print("screener fail", sid, e)
        return []
    out = []
    for x in q:
        cap = (x.get("marketCap") or 0) / 1e9
        out.append({"sym": x.get("symbol"), "name": x.get("shortName") or x.get("longName"),
                    "chg": round(x.get("regularMarketChangePercent") or 0, 2), "cap_b": round(cap, 1)})
    return out


def main():
    g = [x for x in screener("day_gainers") if x["cap_b"] >= 2][:40]
    l = [x for x in screener("day_losers") if x["cap_b"] >= 2][:20]
    watch = []
    try:
        us = json.load(open(os.path.join(ROOT, "data", "ref", "us_daily.json"), encoding="utf-8"))["tickers"]
        for sym, t in us.items():
            ds = sorted(t["close"])
            if len(ds) >= 2 and t["close"][ds[-2]]:
                r = (t["close"][ds[-1]] / t["close"][ds[-2]] - 1) * 100
                if abs(r) >= 3:
                    watch.append({"sym": sym, "name": t["name"], "group": t["group"], "date": ds[-1], "chg": round(r, 2)})
    except (OSError, ValueError, KeyError):
        pass
    out = {"updated": datetime.now(timezone(timedelta(hours=9))).isoformat(timespec="seconds"),
           "gainers": g, "losers": l, "watch": sorted(watch, key=lambda x: -abs(x["chg"]))}
    json.dump(out, open(os.path.join(ROOT, "data", "ref", "us_movers.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("gainers", len(g), "losers", len(l), "watch", len(watch))


if __name__ == "__main__":
    main()

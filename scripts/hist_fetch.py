"""과거 달력 복원용: 전 종목 일봉(약 2년)을 받아 날짜별 급등 종목(+5% 이상)만 남긴다. GitHub Actions에서 실행.

결과: data/hist/movers.json
  {"days": {"2024-10-07": {"n": 2400, "up": [[code, name, chg, amt_eok], ...]}}, "src": "naver fchart", ...}
한계: 지금 상장된 종목만 있다(상장폐지 종목 빠짐). 거래대금은 종가×거래량 근사.
"""
import glob
import json
import os
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"}
COUNT = int(os.environ.get("HIST_COUNT", "520"))


def fetch(code):
    url = f"https://fchart.stock.naver.com/sise.nhn?symbol={code}&timeframe=day&count={COUNT}&requestType=0"
    for i in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
                raw = r.read().decode("euc-kr", "ignore")
            rows = []
            for part in raw.split('data="')[1:]:
                v = part.split('"', 1)[0].split("|")
                if len(v) >= 6 and v[4] not in ("", "0"):
                    rows.append((v[0], float(v[4]), float(v[5] or 0), float(v[2] or 0)))
            return code, rows
        except Exception:
            time.sleep(1 + i)
    return code, []


def main():
    snap = sorted(glob.glob(os.path.join(ROOT, "data", "20*", "krx.json")))[-1]
    krx = json.load(open(snap, encoding="utf-8"))
    days = defaultdict(lambda: {"n": 0, "up": []})
    ok = 0
    with ThreadPoolExecutor(8) as ex:
        for code, rows in ex.map(fetch, list(krx)):
            if not rows:
                continue
            ok += 1
            name = krx[code][0]
            for (d0, c0, _, _), (d1, c1, vol, hi) in zip(rows, rows[1:]):
                if not c0:
                    continue
                day = f"{d1[:4]}-{d1[4:6]}-{d1[6:]}"
                chg = (c1 / c0 - 1) * 100
                days[day]["n"] += 1
                if chg >= 5:
                    days[day]["up"].append([code, name, round(chg, 2), round(c1 * vol / 1e8)])
    out = {"src": "naver fchart (수정주가)", "base_list": os.path.basename(os.path.dirname(snap)), "stocks_ok": ok,
           "days": {d: days[d] for d in sorted(days)}}
    os.makedirs(os.path.join(ROOT, "data", "hist"), exist_ok=True)
    json.dump(out, open(os.path.join(ROOT, "data", "hist", "movers.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("stocks", ok, "days", len(days))


if __name__ == "__main__":
    main()

"""
테마 달력 시세 수집기 (GitHub Actions에서 실행, API 키 불필요)

  python collect.py main   → 15:45 본장 마감: 오늘 급등 종목 50~90개
  python collect.py after  → 20:10 넥장 마감: 본장 종가 대비 장후(NXT 애프터마켓) 급등 종목

결과: data/YYYY-MM-DD/main.json, after.json
데이터 출처: 네이버페이 증권 공개 시세 (개인 참고용)
"""
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
ROOT = os.path.dirname(os.path.abspath(__file__))
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"}

MAIN_MIN_RATE, MAIN_MIN_COUNT, MAIN_MAX_COUNT = 7.0, 50, 90
AFTER_MIN_RATE, AFTER_MAX_COUNT = 3.0, 60


def now():
    return datetime.now(KST)


TODAY = now().strftime("%Y-%m-%d")


def get(url, retry=3):
    for i in range(retry):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            if i == retry - 1:
                raise
            print("retry", url, e)
            time.sleep(2 * (i + 1))


def f(v):
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def is_common_stock(s):
    name = s.get("stockName", "")
    return s.get("stockEndType") == "stock" and "스팩" not in name


def ranked(market, stop_below=None, max_pages=30, kind="up"):
    """등락률 순 종목 목록(kind=up: 상승, down: 하락). stop_below 미만 등락률이 나오면 중단."""
    out = []
    for page in range(1, max_pages + 1):
        d = get(f"https://m.stock.naver.com/api/stocks/{kind}/{market}?page={page}&pageSize=100")
        items = d.get("stocks", [])
        for s in items:
            s["_market"] = market
            out.append(s)
        if not items or len(items) < 100:
            break
        if stop_below is not None and f(items[-1].get("fluctuationsRatio")) is not None \
                and f(items[-1]["fluctuationsRatio"]) < stop_below:
            break
        time.sleep(0.3)
    return out


def traded_today(stocks):
    """가장 최근 체결 시각이 오늘인지로 거래일 여부 판단."""
    for s in stocks[:20]:
        t = s.get("localTradedAt", "")
        if t.startswith(TODAY):
            return True
    return False


def index_change():
    res = {}
    for key, code in (("kospi", "KOSPI"), ("kosdaq", "KOSDAQ")):
        try:
            d = get(f"https://polling.finance.naver.com/api/realtime/domestic/index/{code}")
            it = (d.get("datas") or [{}])[0]
            r = f(it.get("fluctuationsRatioRaw") or it.get("fluctuationsRatio"))
            if r is not None:
                res[key] = f"{r:+.2f}%"
        except Exception as e:
            print("index fail", code, e)
    return res


def save(kind, payload):
    payload["generatedAt"] = now().isoformat(timespec="seconds")
    folder = os.path.join(ROOT, "data", "_test" if os.environ.get("TEST") else TODAY)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, f"{kind}.json"), "w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False, indent=1)
    print(f"saved data/{TODAY}/{kind}.json", payload.get("status"), len(payload.get("stocks", [])))


def run_main():
    rows = ranked("KOSPI", stop_below=4) + ranked("KOSDAQ", stop_below=4)
    if not traded_today(rows):
        return save("main", {"date": TODAY, "status": "closed", "stocks": []})
    picked = []
    for s in rows:
        if not is_common_stock(s):
            continue
        chg = f(s.get("fluctuationsRatio"))
        if chg is None:
            continue
        picked.append({
            "code": s["itemCode"], "name": s["stockName"], "market": s["_market"],
            "chg": round(chg, 2), "price": f(s.get("closePriceRaw")),
            "amount_eok": round((f(s.get("accumulatedTradingValueRaw")) or 0) / 1e8),
            "limit": (s.get("compareToPreviousPrice") or {}).get("name") == "UPPER_LIMIT",
        })
    picked.sort(key=lambda x: x["chg"], reverse=True)
    strong = [p for p in picked if p["chg"] >= MAIN_MIN_RATE]
    stocks = (strong if len(strong) >= MAIN_MIN_COUNT else picked[:MAIN_MIN_COUNT])[:MAIN_MAX_COUNT]
    save("main", {"date": TODAY, "status": "open", "source": "naver-finance",
                  "rule": f"KRX 정규장 등락률 {MAIN_MIN_RATE}% 이상(부족하면 상위 {MAIN_MIN_COUNT}개), ETF·ETN·스팩 제외",
                  "strong_count": len(strong), **index_change(), "stocks": stocks})


def run_after():
    rows = [s for s in ranked("KOSPI") + ranked("KOSDAQ") if is_common_stock(s)]
    if not traded_today(rows):
        return save("after", {"date": TODAY, "status": "closed", "stocks": []})
    # 본장에서 내렸거나 보합인 종목도 장후에 급등할 수 있으므로 하락 목록도 함께 본다
    for mk in ("KOSPI", "KOSDAQ"):
        for kind in ("down", "same"):
            try:
                rows += [s for s in ranked(mk, kind=kind) if is_common_stock(s)]
            except Exception as e:
                print("list fail", mk, kind, e)
    meta = {s["itemCode"]: s for s in rows}
    codes = list(meta)
    moved, sessions, nxt_map = [], {}, {}
    for i in range(0, len(codes), 60):
        d = get("https://polling.finance.naver.com/api/realtime/domestic/stock/" + ",".join(codes[i:i + 60]))
        for it in d.get("datas", []):
            o = it.get("overMarketPriceInfo")
            if not o:
                continue   # NXT 거래 대상이 아닌 종목
            st = o.get("tradingSessionType")
            sessions[st] = sessions.get(st, 0) + 1
            close, over = f(it.get("closePriceRaw")), f(o.get("overPrice"))
            if close and over:
                # 모든 NXT 종목의 [넥장 등락률(종가 대비), 본장 등락률] — 달력에 "본장 x% · 넥장 y%" 표시용
                nxt_map[it["stockName"]] = [round((over / close - 1) * 100, 2), f(it.get("fluctuationsRatioRaw"))]
            if not close or not over or over == close:
                continue
            m = meta.get(it["itemCode"], {})
            moved.append({
                "code": it["itemCode"], "name": it["stockName"], "market": m.get("_market"),
                "close": close, "last": over, "after_chg": round((over / close - 1) * 100, 2),
                "day_chg": f(it.get("fluctuationsRatioRaw")),
                "nxt_amount_eok": round((f(o.get("accumulatedTradingValueRaw")) or 0) / 1e8),
            })
        time.sleep(0.3)
    up = sorted([m for m in moved if m["after_chg"] >= AFTER_MIN_RATE], key=lambda x: -x["after_chg"])[:AFTER_MAX_COUNT]
    down = sorted([m for m in moved if m["after_chg"] <= -AFTER_MIN_RATE], key=lambda x: x["after_chg"])[:15]
    save("after", {"date": TODAY, "status": "open", "source": "naver-finance",
                   "rule": f"KRX 종가 대비 NXT 장후 가격 {AFTER_MIN_RATE}% 이상",
                   "sessions": sessions, "moved_count": len(moved), "stocks": up, "down": down,
                   "nxt_map": nxt_map})


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "main"
    {"main": run_main, "after": run_after}[mode]()

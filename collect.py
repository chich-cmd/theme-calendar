"""
테마 달력 시세 수집기 (GitHub Actions에서 실행, API 키 불필요)

  python collect.py main   → 15:45 본장 마감: 오늘 급등 종목 50~90개
  python collect.py after  → 20:10 넥장 마감: 본장 종가 대비 장후(NXT 애프터마켓) 급등 종목
  python collect.py pre    → 08:20/08:35 넥장 프리마켓: 전 거래일 종가 대비 급등 종목 (장전 예측 보정용)

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


def save_krx_snapshot():
    """본장 마감 직후 전 종목의 KRX 종가·등락률을 저장 (넥장 최종 등락률과 비교하는 기준)."""
    snap = {}
    for mk in ("KOSPI", "KOSDAQ"):
        for kind in ("up", "down", "same"):
            try:
                for s in ranked(mk, kind=kind):
                    if is_common_stock(s) and f(s.get("closePriceRaw")):
                        snap[s["itemCode"]] = [s["stockName"], f(s.get("closePriceRaw")), f(s.get("fluctuationsRatio")), mk]
            except Exception as e:
                print("snapshot fail", mk, kind, e)
    folder = os.path.join(ROOT, "data", "_test" if os.environ.get("TEST") else TODAY)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "krx.json"), "w", encoding="utf-8") as fp:
        json.dump(snap, fp, ensure_ascii=False, separators=(",", ":"))
    print("krx snapshot", len(snap))


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
    save_krx_snapshot()
    save("main", {"date": TODAY, "status": "open", "source": "naver-finance",
                  "rule": f"KRX 정규장 등락률 {MAIN_MIN_RATE}% 이상(부족하면 상위 {MAIN_MIN_COUNT}개), ETF·ETN·스팩 제외",
                  "strong_count": len(strong), **index_change(), "stocks": stocks})


def load_json(*parts):
    try:
        with open(os.path.join(ROOT, *parts), encoding="utf-8") as fp:
            return json.load(fp)
    except (OSError, ValueError):
        return None


def run_after():
    """넥장(NXT 20:00) 마감 후: 종목별 최종 등락률(전일 대비)과 KRX 종가 대비 장후 등락률.

    네이버 실시간 시세의 closePriceRaw / fluctuationsRatioRaw 는 20:00 이후 KRX+NXT 통합 최종가 기준이다.
    KRX 종가는 15:45 수집 때 저장한 data/<오늘>/krx.json (없으면 main.json) 을 쓴다.
    """
    krx = load_json("data", TODAY, "krx.json") or {}
    main = load_json("data", TODAY, "main.json") or {}
    for s in main.get("stocks", []):
        krx.setdefault(s["code"], [s["name"], s.get("price"), s.get("chg"), s.get("market")])
    if not krx:   # 기준 데이터가 없으면 목록에서 종목 코드만이라도 모은다
        for mk in ("KOSPI", "KOSDAQ"):
            for kind in ("up", "down", "same"):
                try:
                    for s in ranked(mk, kind=kind):
                        if is_common_stock(s):
                            krx[s["itemCode"]] = [s["stockName"], None, None, mk]
                except Exception as e:
                    print("list fail", mk, kind, e)
    if main.get("status") == "closed":
        return save("after", {"date": TODAY, "status": "closed", "stocks": []})
    codes = list(krx)
    moved, nxt_map, sessions, traded = [], {}, {}, False
    for i in range(0, len(codes), 60):
        d = get("https://polling.finance.naver.com/api/realtime/domestic/stock/" + ",".join(codes[i:i + 60]))
        for it in d.get("datas", []):
            code, name = it.get("itemCode"), it.get("stockName")
            final, ratio = f(it.get("closePriceRaw")), f(it.get("fluctuationsRatioRaw"))
            if final is None or ratio is None:
                continue
            o = it.get("overMarketPriceInfo") or {}
            st = o.get("tradingSessionType")
            if st:
                sessions[st] = sessions.get(st, 0) + 1
            if (o.get("localTradedAt") or "").startswith(TODAY):
                traded = True
            k = krx.get(code) or [name, None, None, None]
            kclose, kchg = k[1], k[2]
            after_chg = round((final / kclose - 1) * 100, 2) if kclose else None
            nxt_map[name] = {"final": ratio, "krx": kchg, "after": after_chg,
                             "nxt_eok": round((f(o.get("accumulatedTradingValueRaw")) or 0) / 1e8)}
            if after_chg is None or abs(after_chg) < 0.005:
                continue
            moved.append({
                "code": code, "name": name, "market": k[3],
                "close": kclose, "last": final, "after_chg": after_chg,
                "day_chg": kchg, "final_chg": ratio,
                "nxt_amount_eok": nxt_map[name]["nxt_eok"],
            })
        time.sleep(0.3)
    if not traded and not main.get("stocks"):
        return save("after", {"date": TODAY, "status": "closed", "stocks": []})
    up = sorted([m for m in moved if m["after_chg"] >= AFTER_MIN_RATE], key=lambda x: -x["after_chg"])[:AFTER_MAX_COUNT]
    down = sorted([m for m in moved if m["after_chg"] <= -AFTER_MIN_RATE], key=lambda x: x["after_chg"])[:15]
    save("after", {"date": TODAY, "status": "open", "source": "naver-finance",
                   "rule": f"KRX 종가 대비 넥장 최종가 {AFTER_MIN_RATE}% 이상 (최종가 = 20:00 KRX+NXT 통합)",
                   "sessions": sessions, "nxt_traded_today": traded, "moved_count": len(moved),
                   "stocks": up, "down": down, "nxt_map": nxt_map})


PRE_MIN_RATE = 3.0


def run_pre():
    """NXT 프리마켓(08:00~08:50) 중: 전 거래일 KRX 종가 대비 등락. 기준 종가는 가장 최근 data/<날짜>/krx.json."""
    prev = sorted(d for d in os.listdir(os.path.join(ROOT, "data"))
                  if d[:2] == "20" and d < TODAY and os.path.exists(os.path.join(ROOT, "data", d, "krx.json")))
    krx = load_json("data", prev[-1], "krx.json") if prev else {}
    if not krx:
        return save("pre", {"date": TODAY, "status": "error", "note": "기준 종가 없음", "stocks": []})
    codes = list(krx)
    moved, sessions, traded, sample = [], {}, 0, None
    for i in range(0, len(codes), 60):
        try:
            d = get("https://polling.finance.naver.com/api/realtime/domestic/stock/" + ",".join(codes[i:i + 60]))
        except Exception as e:
            print("poll fail", e); continue
        for it in d.get("datas", []):
            o = it.get("overMarketPriceInfo") or {}
            st = o.get("tradingSessionType")
            if st:
                sessions[st] = sessions.get(st, 0) + 1
            if not (o.get("localTradedAt") or "").startswith(TODAY):
                continue
            if sample is None:
                sample = o
            traded += 1
            code = it.get("itemCode")
            k = krx.get(code) or [it.get("stockName"), None, None, None]
            price = f(o.get("overPrice"))
            chg = round((price / k[1] - 1) * 100, 2) if price and k[1] else f(o.get("fluctuationsRatio"))
            if chg is None:
                continue
            moved.append({"code": code, "name": it.get("stockName") or k[0], "market": k[3], "base": k[1], "price": price,
                          "chg": chg, "eok": round((f(o.get("accumulatedTradingValueRaw")) or 0) / 1e8, 1),
                          "vol": f(o.get("accumulatedTradingVolumeRaw") or o.get("accumulatedTradingVolume"))})
        time.sleep(0.25)
    up = sorted([m for m in moved if m["chg"] >= PRE_MIN_RATE], key=lambda x: -x["chg"])[:80]
    down = sorted([m for m in moved if m["chg"] <= -PRE_MIN_RATE], key=lambda x: x["chg"])[:20]
    save("pre", {"date": TODAY, "status": "open" if traded else "closed", "source": "naver-finance",
                 "time": now().strftime("%H:%M"), "base_day": prev[-1],
                 "rule": f"NXT 프리마켓 가격이 전 거래일 KRX 종가 대비 {PRE_MIN_RATE}% 이상",
                 "sessions": sessions, "traded": traded, "stocks": up, "down": down, "sample": sample})


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "main"
    {"main": run_main, "after": run_after, "pre": run_pre}[mode]()

"""미국 업종 대표주·지수·원자재 일별 종가 수집 (GitHub Actions에서 실행, 키 불필요).

결과: data/ref/us_daily.json
  {"updated": "...", "tickers": {"COHR": {"name": "...", "group": "광통신", "close": {"2026-10-01": 315.7, ...}}}}
날짜는 미국 거래일(현지) 기준. 다음 날 한국장에 대응한다.
"""
import csv
import io
import json
import os
import time
import urllib.request
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"}

# 달력 테마 → 미국 짝 (docs/pre_method.md 와 같은 대응)
TICKERS = {
    "^GSPC": ("S&P500", "시장"), "^IXIC": ("나스닥", "시장"), "^SOX": ("필라델피아 반도체", "반도체"),
    "^TNX": ("미 10년물 금리", "금리"), "CL=F": ("WTI", "정유·화학"), "KRW=X": ("원/달러", "환율"),
    "AMAT": ("어플라이드머티리얼즈", "반도체 소부장"), "LRCX": ("램리서치", "반도체 소부장"), "KLAC": ("KLA", "반도체 소부장"),
    "MU": ("마이크론", "반도체"), "NVDA": ("엔비디아", "반도체"), "SNPS": ("시놉시스", "반도체"),
    "COHR": ("코히런트", "광통신"), "LITE": ("루멘텀", "광통신"), "GLW": ("코닝", "광통신"), "CIEN": ("시에나", "광통신"),
    "TSLA": ("테슬라", "2차전지"), "ALB": ("앨버말", "2차전지"), "SQM": ("SQM", "2차전지"), "LIT": ("리튬 ETF", "2차전지"),
    "CEG": ("콘스텔레이션", "원전·에너지"), "VST": ("비스트라", "원전·에너지"), "NLR": ("원전 ETF", "원전·에너지"), "URA": ("우라늄 ETF", "원전·에너지"), "OKLO": ("오클로", "원전·에너지"), "SMR": ("뉴스케일", "원전·에너지"), "CCJ": ("카메코", "원전·에너지"),
    "GEV": ("GE버노바", "전력기기·전선"), "ETN": ("이튼", "전력기기·전선"), "VRT": ("버티브", "전력기기·전선"),
    "RKLB": ("로켓랩", "방산·우주항공"), "SPCX": ("스페이스X", "방산·우주항공"), "UFO": ("우주 ETF", "방산·우주항공"), "ARKX": ("우주탐사 ETF", "방산·우주항공"), "ASTS": ("AST스페이스모바일", "방산·우주항공"), "LMT": ("록히드마틴", "방산·우주항공"),
    "XBI": ("바이오 ETF", "제약·바이오"), "LLY": ("일라이릴리", "제약·바이오"),
    "XOM": ("엑슨모빌", "정유·화학"), "VLO": ("발레로", "정유·화학"),
    "BOTZ": ("로봇 ETF", "로봇"), "COIN": ("코인베이스", "디지털자산"), "BTC-USD": ("비트코인", "디지털자산"),
    "AAPL": ("애플", "스마트폰 부품"),
    "TSM": ("TSMC ADR", "아시아"), "^N225": ("닛케이225", "아시아"), "ES=F": ("S&P500 선물", "아시아"), "NQ=F": ("나스닥 선물", "아시아"),
}


def get(url):
    for i in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                return r.read().decode("utf-8")
        except Exception as e:
            print("retry", url, e)
            time.sleep(2 * (i + 1))
    return ""


def yahoo(sym, rng="1y"):
    raw = get(f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.request.quote(sym)}?range={rng}&interval=1d")
    try:
        r = json.loads(raw)["chart"]["result"][0]
        ts, cl = r["timestamp"], r["indicators"]["quote"][0]["close"]
        off = r["meta"].get("gmtoffset", 0)
        return {datetime.fromtimestamp(t + off, timezone.utc).strftime("%Y-%m-%d"): round(c, 4) for t, c in zip(ts, cl) if c}
    except Exception:
        return {}


def stooq(sym):
    s = {"^GSPC": "^spx", "^IXIC": "^ndq", "CL=F": "cl.f", "KRW=X": "usdkrw", "BTC-USD": "btcusd", "^SOX": "^sox"}.get(sym, sym.lower() + ".us")
    raw = get(f"https://stooq.com/q/d/l/?s={s}&i=d")
    out = {}
    for row in csv.DictReader(io.StringIO(raw)):
        try:
            out[row["Date"]] = float(row["Close"])
        except (KeyError, ValueError):
            pass
    return out


def main():
    path = os.path.join(ROOT, "data", "ref", "us_daily.json")
    try:
        old = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        old = {"tickers": {}}
    out = {"updated": datetime.now(timezone(timedelta(hours=9))).isoformat(timespec="seconds"), "tickers": {}, "source": {}}
    for sym, (name, group) in TICKERS.items():
        close = yahoo(sym)
        src = "yahoo"
        if len(close) < 20:
            close = stooq(sym)
            src = "stooq"
        prev = (old.get("tickers", {}).get(sym) or {}).get("close", {})
        merged = {**prev, **close}
        cut = (datetime.now() - timedelta(days=400)).strftime("%Y-%m-%d")
        merged = {d: v for d, v in sorted(merged.items()) if d >= cut}
        out["tickers"][sym] = {"name": name, "group": group, "close": merged}
        out["source"][sym] = f"{src}:{len(close)}"
        time.sleep(0.4)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print({k: v for k, v in out["source"].items()})


if __name__ == "__main__":
    main()

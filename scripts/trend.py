"""종목 종가 시계열: data/hist/closes.json.gz(주간 갱신) + 매일 data/<날짜>/krx.json 종가."""
import glob
import gzip
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_cache = {}


def series():
    if "s" in _cache:
        return _cache["s"]
    close, name2code = {}, {}
    try:
        raw = json.load(gzip.open(os.path.join(ROOT, "data", "hist", "closes.json.gz"), "rt", encoding="utf-8"))
        for code, (name, rows) in raw.items():
            name2code[name] = code
            close[code] = {f"{d[:4]}-{d[4:6]}-{d[6:]}": v for d, v in rows}
    except (OSError, ValueError):
        pass
    for p in sorted(glob.glob(os.path.join(ROOT, "data", "20*", "krx.json"))):
        day = os.path.basename(os.path.dirname(p))
        for code, v in json.load(open(p, encoding="utf-8")).items():
            name2code.setdefault(v[0], code)
            if v[1]:
                close.setdefault(code, {})[day] = v[1]
    _cache["s"] = (close, name2code)
    return _cache["s"]


def ret(name, upto, n=60):
    """upto 이전 마지막 종가 기준 최근 n거래일 수익률(%). 없으면 None."""
    close, n2c = series()
    c = close.get(n2c.get(name, ""), {})
    ds = [d for d in sorted(c) if d < upto]
    if len(ds) < 20:
        return None
    a = c[ds[-min(n, len(ds) - 1) - 1]]
    return round((c[ds[-1]] / a - 1) * 100, 1) if a else None

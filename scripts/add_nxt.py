"""본장 주도주에 넥장(NXT 장후) 등락률을, 넥장 종목에 본장 등락률을 붙인다.

  python scripts/add_nxt.py [YYYY-MM-DD]

data/<날짜>/after.json 의 nxt_map {종목명: {final: 넥장 마감 최종 등락률(전일 대비), krx: 본장 등락률, after: KRX 종가 대비}} 로
themes/days/<날짜>.json 의 main 종목에 "nxt", after 종목에 "day"·"fin" 을 채운다.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def nxt_map(day):
    try:
        with open(os.path.join(ROOT, "data", day, "after.json"), encoding="utf-8") as f:
            return json.load(f).get("nxt_map") or {}
    except (OSError, ValueError):
        return {}


def _get(v, key):
    if isinstance(v, dict):
        return v.get(key)
    if isinstance(v, list):   # 예전 형식 [넥장(종가 대비), 본장]
        return {"krx": v[1]}.get(key)
    return None


def apply(doc, m):
    """본장 종목에 nxt(넥장 마감 최종 등락률, 전일 대비)를, 넥장 종목에 day(본장)·fin(최종)을 채운다."""
    if not m:
        return False
    changed = False
    for t in (doc.get("main") or {}).get("themes", []):
        for s in t.get("stocks", []):
            nv = _get(m.get(s.get("name")), "final")
            if s.get("nxt", "missing") != nv:
                s["nxt"] = nv
                changed = True
    for t in (doc.get("after") or {}).get("themes", []):
        for s in t.get("stocks", []):
            v = m.get(s.get("name"))
            for key, src in (("day", "krx"), ("fin", "final")):
                x = _get(v, src)
                if isinstance(x, (int, float)) and s.get(key) != x:
                    s[key] = x
                    changed = True
    return changed


def main():
    day = sys.argv[1] if len(sys.argv) > 1 else datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d")
    path = os.path.join(ROOT, "themes", "days", f"{day}.json")
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError):
        print("no day doc"); return
    if apply(doc, nxt_map(day)):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False)
        print("updated", day)
    else:
        print("no change", day)


if __name__ == "__main__":
    main()

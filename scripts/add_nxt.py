"""본장 주도주에 넥장(NXT 장후) 등락률을, 넥장 종목에 본장 등락률을 붙인다.

  python scripts/add_nxt.py [YYYY-MM-DD]

data/<날짜>/after.json 의 nxt_map {종목명: [넥장 등락률, 본장 등락률]} 을 사용해
themes/days/<날짜>.json 의 main 종목에 "nxt", after 종목에 "day" 를 채운다.
NXT에서 거래되지 않는 종목은 nxt = null (화면에 "–").
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


def apply(doc, m):
    """doc(하루 문서)에 넥장/본장 등락률을 채운다. 바뀌었으면 True."""
    if not m:
        return False
    changed = False
    for t in (doc.get("main") or {}).get("themes", []):
        for s in t.get("stocks", []):
            v = m.get(s.get("name"))
            nv = v[0] if v else None
            if s.get("nxt", "missing") != nv:
                s["nxt"] = nv
                changed = True
    for t in (doc.get("after") or {}).get("themes", []):
        for s in t.get("stocks", []):
            v = m.get(s.get("name"))
            if v and isinstance(v[1], (int, float)) and s.get("day") != v[1]:
                s["day"] = v[1]
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

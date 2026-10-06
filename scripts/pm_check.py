"""08:20/08:35 넥장 프리마켓 점검: 프리마켓 급등 종목을 달력 테마로 묶어 장전 예측에 붙인다.

  python3 scripts/pm_check.py [YYYY-MM-DD]

입력: data/<날짜>/pre.json (collect.py pre), themes/days/<날짜>.json 의 pre(07:00 예측)
결과: 같은 문서의 pre.pm = {time, n, themes:[{name, stocks:[{name, chg}]}], confirm:[...], new:[...]}
  confirm = 예측 테마 중 프리마켓에서도 2종목 이상 오른 테마
  new     = 예측에 없는데 프리마켓에서 3종목 이상 오른 테마 (장중 재료 후보)
원래 예측 5개는 바꾸지 않는다 (예측 채점은 그대로, 보정은 따로 채점).
"""
import glob
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ETC = lambda n: n.startswith("기타") or "개별" in n or n == "신규상장주"
# 네이버 분류가 다른 테마와 겹쳐 엉뚱하게 묶이는 대표주는 테마를 고정한다 (10/6 안랩·한컴이 AI 소프트웨어로 묶인 사례)
FIXED = {n: "보안" for n in ("안랩", "한컴", "지니언스", "파수", "라온시큐어", "드림시큐리티", "이글루", "윈스", "샌즈랩",
                             "시큐레터", "SGA솔루션즈", "한컴위드", "엑스게이트", "모니터랩", "케이사인", "에스투더블유", "싸이버원")}


def history_map(day, window=60):
    """종목 → 최근 60거래일 달력에서 들어갔던 테마 (최근일수록 무게 큼)."""
    files = sorted(p for p in glob.glob(os.path.join(ROOT, "themes", "days", "*.json")) if os.path.basename(p)[:-5] < day)
    hm = defaultdict(Counter)
    n = 0
    for p in reversed(files):
        doc = json.load(open(p, encoding="utf-8"))
        ths = (doc.get("main") or {}).get("themes") or []
        if not ths:
            continue
        for t in ths:
            if ETC(t["name"]):
                continue
            for s in t["stocks"]:
                hm[s["name"]][t["name"]] += 0.9 ** n
        n += 1
        if n >= window:
            break
    return hm


def main():
    day = sys.argv[1] if len(sys.argv) > 1 else datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d")
    try:
        raw = json.load(open(os.path.join(ROOT, "data", day, "pre.json"), encoding="utf-8"))
    except (OSError, ValueError):
        print("no premarket data"); return
    path = os.path.join(ROOT, "themes", "days", f"{day}.json")
    try:
        doc = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        print("no day doc"); return
    if doc.get("status") == "holiday" or raw.get("status") != "open" or not doc.get("pre", {}).get("themes"):
        print("skip:", doc.get("status"), raw.get("status"), bool(doc.get("pre"))); return
    stocks = [s for s in raw.get("stocks", []) if s["chg"] < 29.9 or s.get("eok", 0) >= 1]   # 거래 거의 없는 상한가 호가 제외
    stocks = [s for s in stocks if (s.get("eok") or 0) >= 0.3 or s["chg"] >= 5]
    hm = history_map(day)
    try:
        from theme_map import Ref
        ref = Ref()
    except Exception:
        ref = None
    groups = defaultdict(list)
    for s in stocks:
        c = hm.get(s["name"])
        if s["name"] in FIXED:
            t = FIXED[s["name"]]
        elif c:
            t = c.most_common(1)[0][0]
        elif ref:
            cs = ref.canons(code=s.get("code"), name=s["name"])
            t = max(cs, key=cs.get) if cs else None
        else:
            t = None
        if t and not ETC(t):
            groups[t].append({"name": s["name"], "chg": s["chg"], "eok": s.get("eok", 0)})
    themes = sorted(([n, v] for n, v in groups.items() if len(v) >= 2), key=lambda x: (-len(x[1]), -sum(s["eok"] for s in x[1])))
    preds = [p["name"] for p in doc["pre"]["themes"]]
    pm = {"time": raw.get("time") or "", "n": len(stocks),
          "themes": [{"name": n, "stocks": [{"name": s["name"], "chg": s["chg"]} for s in sorted(v, key=lambda x: -x["chg"])[:5]]}
                     for n, v in themes[:6]],
          "confirm": [p for p in preds if p in groups and len(groups[p]) >= 2],
          "new": [n for n, v in themes if n not in preds and len(v) >= 3][:3]}
    doc["pre"]["pm"] = pm
    json.dump(doc, open(path, "w", encoding="utf-8"), ensure_ascii=False)
    print(json.dumps(pm, ensure_ascii=False))


if __name__ == "__main__":
    main()

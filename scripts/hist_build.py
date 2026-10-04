"""과거 달력 복원: data/hist/movers.json(전 종목 일봉 급등) + 네이버 테마 분류 → 날짜별 테마·주도 테마.

  python3 scripts/hist_build.py   → data/ref/hist_leads.json {"L": {day: [주도 3]}, "P": {day: {테마: 종목 수}}}

실제 달력과 주도 테마 일치율 약 56% (2026.7~10 비교). 테마 고르기가 아니라 '규칙의 크기'(모멘텀·미국 연동)를
길게(약 2년) 재는 용도. 지금 상장 종목·지금 테마 분류 기준이라 생존 편향이 있다.
"""
import json
import os
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from theme_map import Ref  # noqa: E402


def build(day_rec, ref):
    up = sorted(day_rec["up"], key=lambda x: -x[2])
    st = [u for u in up if u[2] >= 7]
    if len(st) < 50:
        st = up[:50]
    st = st[:90]
    cn = {u[0]: ref.canons(code=u[0]) for u in st}
    cnt = Counter(c for u in st for c in cn[u[0]])
    th = defaultdict(list)
    for u in st:
        cs = [c for c in cn[u[0]] if cnt[c] >= 2]
        # 같은 날 많이 겹치면서도 좁은(구체적인) 테마를 고른다 (예: 통신장비보다 광통신)
        t = max(cs, key=lambda c: cnt[c] * cn[u[0]][c]) if cs else "기타(개별)"
        th[t].append(u)
    for t in [t for t, v in th.items() if len(v) < 2 and t != "기타(개별)"]:
        th["기타(개별)"] += th.pop(t)
    n, a = len(st) or 1, sum(u[3] for u in st) or 1
    sc = {t: len(v) / n + sum(u[3] for u in v) / a for t, v in th.items() if not t.startswith("기타") and len(v) >= 2}
    lead = sorted(sc, key=lambda t: -sc[t])[:3]
    return lead, {t: len(v) for t, v in th.items() if not t.startswith("기타")}


def main():
    h = json.load(open(os.path.join(ROOT, "data", "hist", "movers.json"), encoding="utf-8"))["days"]
    ref = Ref()
    out = {"note": "복원 달력(실제 달력과 주도 일치 약 56%). 규칙 크기 측정용", "L": {}, "P": {}}
    for d in sorted(h):
        if h[d]["n"] < 1500:
            continue
        out["L"][d], out["P"][d] = build(h[d], ref)
    json.dump(out, open(os.path.join(ROOT, "data", "ref", "hist_leads.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("days", len(out["L"]))


if __name__ == "__main__":
    main()

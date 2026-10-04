"""장전 예측 성적표: 근거(src)별로 얼마나 맞았는지 집계한다.

  python3 scripts/pre_eval.py            → 화면 출력 + data/ref/pre_eval.json

예측 json 의 각 테마에 src 를 적어 둔다 (docs/pre_method.md 7단계):
  base(달력 순환) · us(미국 짝) · event(예정 일정) · article(장전 기사) · nxt(넥장 흐름) · news(밤사이 사건)
20거래일쯤 쌓이면 어떤 근거를 더 믿을지 정한다.
"""
import glob
import json
import os
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    docs = {os.path.basename(p)[:-5]: json.load(open(p, encoding="utf-8")) for p in glob.glob(os.path.join(ROOT, "themes", "days", "*.json"))}
    days = sorted(d for d, x in docs.items() if x.get("pre") and (x.get("main") or {}).get("themes"))
    by = defaultdict(lambda: [0, 0, 0])   # 예측 수, 주도 적중, 등장
    rank = defaultdict(lambda: [0, 0])
    tot = [0, 0, 0]
    per_day = []
    for d in days:
        th = {t["name"]: t for t in docs[d]["main"]["themes"]}
        hit = 0
        for i, p in enumerate(docs[d]["pre"].get("themes", [])):
            t = th.get(p["name"])
            lead, seen = bool(t and t.get("lead")), t is not None
            hit += lead
            for s in p.get("src") or ["(미기록)"]:
                by[s][0] += 1; by[s][1] += lead; by[s][2] += seen
            rank[i + 1][0] += 1; rank[i + 1][1] += lead
            tot[0] += 1; tot[1] += lead; tot[2] += seen
        per_day.append((d, hit, len(docs[d]["pre"].get("themes", []))))
    out = {"days": len(days), "total": tot,
           "by_src": {k: {"n": v[0], "lead": v[1], "seen": v[2]} for k, v in by.items()},
           "by_rank": {k: {"n": v[0], "lead": v[1]} for k, v in sorted(rank.items())},
           "per_day": per_day}
    json.dump(out, open(os.path.join(ROOT, "data", "ref", "pre_eval.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if not days:
        print("아직 채점할 예측이 없습니다."); return
    print(f"{len(days)}거래일 · 예측 {tot[0]}개 · 주도 적중 {tot[1]} ({tot[1] / tot[0]:.0%}) · 등장 {tot[2]} ({tot[2] / tot[0]:.0%})"
          f" · 1개 이상 맞춘 날 {sum(h > 0 for _, h, _ in per_day)}/{len(days)}")
    for k, (n, l, s) in sorted(by.items(), key=lambda kv: -kv[1][1] / max(kv[1][0], 1)):
        print(f"  {k:8s} {n:3d}개  주도 {l / n:.0%}  등장 {s / n:.0%}")
    print("  순위별 주도:", " ".join(f"{k}위 {v[1]}/{v[0]}" for k, v in sorted(rank.items())))


if __name__ == "__main__":
    main()

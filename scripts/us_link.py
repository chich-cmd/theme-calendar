"""미국 짝 종목(전날 밤) 등락 → 다음 날 국내 테마 주도 여부 검증.

  python3 scripts/us_link.py      → data/ref/us_link.json 저장 + 요약 출력

테마마다: 미국 짝 평균 등락이 +2% 이상인 날 / -2% 이하인 날 / 그 밖의 날에
그 테마가 주도(lead)였던 비율과 등장(3종목 이상) 비율을 비교한다.
"""
import glob
import json
import os
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    us = json.load(open(os.path.join(ROOT, "data", "ref", "us_daily.json"), encoding="utf-8"))["tickers"]
    ret = {}  # sym -> {date: % change}
    for sym, t in us.items():
        ds = sorted(t["close"])
        ret[sym] = {d: (t["close"][d] / t["close"][p] - 1) * 100 for p, d in zip(ds, ds[1:]) if t["close"][p]}
    groups = {}
    for sym, t in us.items():
        groups.setdefault(t["group"], []).append(sym)
    us_dates = sorted(set(d for s in ret.values() for d in s))
    docs = {os.path.basename(p)[:-5]: json.load(open(p, encoding="utf-8")) for p in glob.glob(os.path.join(ROOT, "themes", "days", "*.json"))}
    kr = sorted(d for d, x in docs.items() if (x.get("main") or {}).get("themes"))
    out = {}
    for g, syms in groups.items():
        if g in ("시장", "금리", "환율"):
            continue
        rows = []
        for d in kr:
            prev = [u for u in us_dates if u < d]
            if not prev:
                continue
            u = prev[-1]
            vals = [ret[s][u] for s in syms if u in ret[s]]
            if not vals:
                continue
            sig = sum(vals) / len(vals)
            ts = docs[d]["main"]["themes"]
            t = next((x for x in ts if x["name"] == g), None)
            rows.append((sig, bool(t and t.get("lead")), bool(t and len(t["stocks"]) >= 3)))
        def rate(sel):
            sel = list(sel)
            return {"n": len(sel), "lead": round(sum(r[1] for r in sel) / len(sel), 2) if sel else None,
                    "seen": round(sum(r[2] for r in sel) / len(sel), 2) if sel else None}
        out[g] = {"proxies": syms, "up2": rate(r for r in rows if r[0] >= 2), "flat": rate(r for r in rows if -2 < r[0] < 2),
                  "down2": rate(r for r in rows if r[0] <= -2), "all": rate(rows)}
    json.dump({"updated": datetime.now().isoformat(timespec="seconds"), "days": len(kr), "themes": out},
              open(os.path.join(ROOT, "data", "ref", "us_link.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for g, v in sorted(out.items(), key=lambda kv: -(kv[1]["all"]["lead"] or 0)):
        print(f"{g:10s} 전체 주도 {v['all']['lead']} | 미국 +2%↑ n={v['up2']['n']} 주도 {v['up2']['lead']} 등장 {v['up2']['seen']}"
              f" | 보합 n={v['flat']['n']} 주도 {v['flat']['lead']} | -2%↓ n={v['down2']['n']} 주도 {v['down2']['lead']} 등장 {v['down2']['seen']}")


if __name__ == "__main__":
    main()

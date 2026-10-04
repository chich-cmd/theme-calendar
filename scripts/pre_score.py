"""장전 예측 점수 계산 (07:00 예측 작업이 참고하는 기본 점수).

  python3 scripts/pre_score.py 2026-10-06          → 그날 테마별 점수표 출력 (+ data/ref/pre_score.json)
  python3 scripts/pre_score.py --backtest           → 지난 기록으로 적중률 검증 (기준선과 비교)

점수 = 기본(최근 20거래일 주도 비율)
     + 미국 신호(전날 밤 미국 짝 종목 평균 ±2% 이상일 때, 지난 기록에서 주도 비율이 얼마나 달라졌는지)
     - 피로도(전날 주도했고, 다음 날 잘 이어지지 않는 테마)
기사·사건 뉴스(발사, 수주, 정책 등)는 사람이(또는 분석 작업이) 따로 더한다.
"""
import glob
import itertools
import json
import os
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ETC = lambda n: n.startswith("기타") or "개별" in n or n == "신규상장주"


def load():
    docs = {os.path.basename(p)[:-5]: json.load(open(p, encoding="utf-8")) for p in glob.glob(os.path.join(ROOT, "themes", "days", "*.json"))}
    days = sorted(d for d, x in docs.items() if (x.get("main") or {}).get("themes"))
    lead = {d: {t["name"] for t in docs[d]["main"]["themes"] if t.get("lead")} for d in days}
    seen = {d: {t["name"] for t in docs[d]["main"]["themes"] if len(t["stocks"]) >= 3 and not ETC(t["name"])} for d in days}
    us = json.load(open(os.path.join(ROOT, "data", "ref", "us_daily.json"), encoding="utf-8"))["tickers"]
    ret = {}
    for sym, t in us.items():
        ds = sorted(t["close"])
        ret[sym] = {d: (t["close"][d] / t["close"][p] - 1) * 100 for p, d in zip(ds, ds[1:]) if t["close"][p]}
    groups = defaultdict(list)
    for sym, t in us.items():
        if t["group"] not in ("시장", "금리", "환율"):
            groups[t["group"]].append(sym)
    us_dates = sorted(ret.get("^GSPC", {}))   # 미국 증시 거래일 기준(비트코인 주말 제외)
    return docs, days, lead, seen, ret, groups, us_dates


def us_signal(day, ret, groups, us_dates):
    prev = [u for u in us_dates if u < day]
    if not prev:
        return {}, None
    u = prev[-1]
    sig = {}
    for g, syms in groups.items():
        v = [ret[s][u] for s in syms if u in ret[s]]
        if v:
            sig[g] = sum(v) / len(v)
    return sig, u


def link_rates(days, lead, ret, groups, us_dates, exclude=None):
    """테마별 미국 신호 구간(+2%↑, -2%↓, 그 밖)의 주도 비율. exclude 날짜는 빼고 계산(검증용)."""
    acc = defaultdict(lambda: {"up": [0, 0], "down": [0, 0], "all": [0, 0]})
    for d in days:
        if d == exclude:
            continue
        sig, _ = us_signal(d, ret, groups, us_dates)
        for g, s in sig.items():
            k = "up" if s >= 2 else "down" if s <= -2 else None
            hit = g in lead[d]
            acc[g]["all"][0] += hit; acc[g]["all"][1] += 1
            if k:
                acc[g][k][0] += hit; acc[g][k][1] += 1
    out = {}
    for g, a in acc.items():
        base = a["all"][0] / a["all"][1] if a["all"][1] else 0
        f = lambda x: (x[0] + base * 2) / (x[1] + 2)   # 표본이 적을 때 평균 쪽으로 당김
        out[g] = {"base": base, "up": f(a["up"]), "down": f(a["down"]), "n_up": a["up"][1], "n_down": a["down"][1]}
    return out


def persistence(days, lead, exclude=None):
    rep, cnt = Counter(), Counter()
    for a, b in zip(days, days[1:]):
        if b == exclude:
            continue
        for t in lead[a]:
            cnt[t] += 1
            rep[t] += t in lead[b]
    return {t: (rep[t] + 0.3 * 2) / (cnt[t] + 2) for t in cnt}


def similar(days, seen, upto, window=60, min_together=4, min_lift=1.5):
    ds = [d for d in days if d < upto][-window:]
    if len(ds) < 40:
        return {}
    n = len(ds) or 1
    c, pair = Counter(), Counter()
    for d in ds:
        c.update(seen[d])
        for a, b in itertools.combinations(sorted(seen[d]), 2):
            pair[(a, b)] += 1
    out = defaultdict(list)
    for (a, b), k in pair.items():
        lift = k * n / (c[a] * c[b])
        if k >= min_together and lift >= min_lift:
            out[a].append((round(lift, 1), b, k))
            out[b].append((round(lift, 1), a, k))
    return {t: [x[1] for x in sorted(v, reverse=True)[:3]] for t, v in out.items()}


US_W = float(os.environ.get('US_W', '1.0'))
FADE_W = float(os.environ.get('FADE_W', '0'))


def score(day, data, loo=False):
    docs, days, lead, seen, ret, groups, us_dates = data
    hist = [d for d in days if d < day]
    last20 = hist[-20:]
    base = Counter(t for d in last20 for t in lead[d])
    rates = link_rates(days, lead, ret, groups, us_dates, exclude=day if loo else None)
    pers = persistence(days, lead, exclude=day if loo else None)
    sig, u = us_signal(day, ret, groups, us_dates)
    yday = lead[hist[-1]] if hist else set()
    cands = set(base) | set(sig) | yday
    rows = []
    for t in cands:
        if ETC(t):
            continue
        s = base[t] / max(len(last20), 1)
        reason = [f"최근20일 주도 {base[t]}회"]
        strong = t in rates and rates[t]["n_up"] >= 8 and rates[t]["n_down"] >= 8 and rates[t]["up"] - rates[t]["down"] >= 0.15
        if t in sig and t in rates and not strong:
            reason.append(f"미국 짝 {sig[t]:+.1f}% (연관 약함)")
        elif t in sig and t in rates:
            r = rates[t]
            if sig[t] >= 2:
                s += US_W * (r["up"] - r["base"]); reason.append(f"미국 짝 {sig[t]:+.1f}% (과거 +2%↑ 주도율 {r['up']:.0%})")
            elif sig[t] <= -2:
                s += US_W * (r["down"] - r["base"]); reason.append(f"미국 짝 {sig[t]:+.1f}% (과거 -2%↓ 주도율 {r['down']:.0%})")
            else:
                reason.append(f"미국 짝 {sig[t]:+.1f}%")
        if t in yday:
            p = pers.get(t, 0.3)
            s -= max(0, 0.35 - p) * FADE_W; reason.append(f"전날 주도(다음날 이어짐 {p:.0%})")
        rows.append((round(s, 3), t, " · ".join(reason)))
    rows.sort(reverse=True)
    return rows, sig, u


def backtest():
    data = load()
    days, lead = data[1], data[2]
    res = {"score": [0, 0, 0], "base20": [0, 0, 0]}
    for i in range(20, len(days)):
        d = days[i]
        rows, _, _ = score(d, data, loo=True)
        pred = [t for _, t, _ in rows[:3]]
        b = Counter(t for x in days[i - 20:i] for t in lead[x])
        base = [t for t, _ in b.most_common(3)]
        for k, p in (("score", pred), ("base20", base)):
            h = len(set(p) & lead[d])
            res[k][0] += h; res[k][1] += 3; res[k][2] += h > 0
    n = len(days) - 20
    for k, (h, tot, any1) in res.items():
        print(f"{k:7s} 예측 1개당 적중 {h / tot:.0%} · 하루 1개 이상 {any1 / n:.0%}  ({n}거래일, 처음 20일 제외)")


def main():
    if "--backtest" in sys.argv:
        backtest()
        return
    day = sys.argv[1]
    data = load()
    rows, sig, u = score(day, data)
    sim = similar(data[1], data[3], day)
    out = {"day": day, "us_date": u, "us_signal": {k: round(v, 2) for k, v in sig.items()},
           "ranking": [{"theme": t, "score": s, "why": w, "similar": sim.get(t, [])} for s, t, w in rows[:10]]}
    json.dump(out, open(os.path.join(ROOT, "data", "ref", "pre_score.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{day} (미국 {u})")
    for r in out["ranking"]:
        print(f"{r['score']:6.3f} {r['theme']:10s} {r['why']}  유사: {', '.join(r['similar'])}")


if __name__ == "__main__":
    main()

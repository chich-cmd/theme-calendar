"""장전 예측 점수 계산 (07:00 예측 작업이 참고하는 기본 점수).

  python3 scripts/pre_score.py 2026-10-06          → 그날 테마별 점수표 출력 (+ data/ref/pre_score.json)
  python3 scripts/pre_score.py --backtest           → 지난 기록으로 적중률 검증 (기준선과 비교)

점수 = 기본(최근 20거래일 주도 비율) — 테마 고르기는 최근 기록으로
     + 미국 신호(전날 밤 미국 짝 종목 평균 ±2% 이상일 때, 지난 기록에서 주도 비율이 얼마나 달라졌는지)
     + 예정 일정(data/ref/events.json: 실적·공모주·지표 발표 — 5일 검증에서 가장 효과가 컸던 방법)
     - 피로도(전날 주도했고, 다음 날 잘 이어지지 않는 테마, 기본 0)
     + 전날 급등 종목 수 가점(최근 60일 '전날 주도→다음날 주도' 비율이 28% 이상인 장세에서만)
규칙의 크기(미국 연동, 이어짐)는 긴 기록(복원 2년 + 실제 달력, data/ref/hist_leads.json)으로 잰다.
  python3 scripts/pre_score.py --backtest-long  → 긴 기록 검증 (각 날짜 이전 정보만 사용)
넥장 흐름은 표본이 쌓일 때까지 점수에 넣지 않고 근거에만 적는다(NXT_W=0).
테마마다 '관련주 묶음'(최근 3번 등장에서 자주 오른 5종목)과 '대장 유지율'을 함께 낸다.
대장주 하나는 다음번에도 대장일 확률이 8%뿐이라, 종목은 항상 묶음으로 본다.
기사·사건 뉴스(발사, 수주, 정책 등)는 분석 작업이 따로 더한다.
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
        if t["group"] not in ("시장", "금리", "환율", "아시아"):
            groups[t["group"]].append(sym)
    us_dates = sorted(ret.get("^GSPC", {}))   # 미국 증시 거래일 기준(비트코인 주말 제외)
    return docs, days, lead, seen, ret, groups, us_dates, load_long(docs, days, lead)


def load_long(docs, days, lead):
    """규칙 크기 측정용 긴 기록: 복원 달력(약 2년, data/ref/hist_leads.json) 위에 실제 달력을 덮어쓴다."""
    L, P = {}, {}
    try:
        h = json.load(open(os.path.join(ROOT, "data", "ref", "hist_leads.json"), encoding="utf-8"))
        L = {d: set(v) for d, v in h["L"].items()}
        P = {d: dict(v) for d, v in h["P"].items()}
    except (OSError, ValueError, KeyError):
        pass
    for d in days:
        L[d] = set(lead[d])
        P[d] = {t["name"]: len(t["stocks"]) for t in docs[d]["main"]["themes"] if not ETC(t["name"])}
    return {"days": sorted(L), "L": L, "P": P}


def us_signal(day, ret, groups, us_dates, prev_kr=None):
    """직전 한국 거래일 장 마감 이후 열린 미국장(들)의 누적 등락. 연휴로 미국장이 2번 이상 열렸으면 합쳐서 본다
    (예: 10/2 금 → 10/6 화: 미국 10/2·10/5 두 거래일)."""
    prev = [u for u in us_dates if u < day]
    if not prev:
        return {}, None
    us = [u for u in prev if prev_kr and u >= prev_kr] or prev[-1:]
    sig = {}
    for g, syms in groups.items():
        v = []
        for sym in syms:
            r = [ret[sym][u] for u in us if u in ret[sym]]
            if r:
                acc = 1.0
                for x in r:
                    acc *= 1 + x / 100
                v.append((acc - 1) * 100)
        if v:
            sig[g] = sum(v) / len(v)
    return sig, (us[0] + "~" + us[-1]) if len(us) > 1 else us[-1]


def link_rates(days, lead, ret, groups, us_dates, exclude=None):
    """테마별 미국 신호 구간(+2%↑, -2%↓, 그 밖)의 주도 비율. exclude 날짜는 빼고 계산(검증용)."""
    acc = defaultdict(lambda: {"up": [0, 0], "down": [0, 0], "all": [0, 0]})
    for i, d in enumerate(days):
        if d == exclude:
            continue
        sig, _ = us_signal(d, ret, groups, us_dates, days[i - 1] if i else None)
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


def momentum(long, upto, exclude=None, prior=5):
    """같은 테마끼리 비교한 '전날 주도 → 다음날 주도' 효과(긴 기록, upto 이전만).
    eff_led = P(주도|전날 주도) - P(주도|전날 주도 아님), eff_n5 = P(주도|전날 5종목+·주도 아님) - P(주도|전날 주도 아님).
    2년 검증: 테마 14개 중 14개에서 전날 주도 효과가 양수(평균 +14%p). 반도체 소부장·2차전지는 거의 0."""
    ds = [d for d in long["days"] if d < upto]
    c = defaultdict(lambda: {"led": [0, 0], "n5": [0, 0], "not": [0, 0], "all": [0, 0]})
    for a, b in zip(ds, ds[1:]):
        if b == exclude:
            continue
        La, Pa, Lb = long["L"][a], long["P"][a], long["L"][b]
        for t in set(Pa) | La | Lb:
            y = t in Lb
            k = "led" if t in La else "not"
            c[t][k][0] += y; c[t][k][1] += 1
            c[t]["all"][0] += y; c[t]["all"][1] += 1
            if k == "not" and Pa.get(t, 0) >= 5:
                c[t]["n5"][0] += y; c[t]["n5"][1] += 1
    out = {}
    for t, v in c.items():
        if v["led"][1] < 15:
            continue
        base = v["all"][0] / v["all"][1]
        r = lambda x: (x[0] + base * prior) / (x[1] + prior)
        out[t] = {"led": round(r(v["led"]) - r(v["not"]), 3), "n5": round(r(v["n5"]) - r(v["not"]), 3), "n": v["led"][1]}
    return out


def regime(long, upto, n=60):
    """최근 n거래일 vs 긴 기록의 '전날 주도 → 다음날 주도' 비율 (경고등)."""
    ds = [d for d in long["days"] if d < upto]
    def rate(sub):
        hit = tot = 0
        for a, b in zip(sub, sub[1:]):
            for t in long["L"][a]:
                tot += 1; hit += t in long["L"][b]
        return round(hit / tot, 3) if tot else None
    return {"recent": rate(ds[-n:]), "long": rate(ds)}


SIM_EXCLUDE = {("광통신", "엔터·미디어"), ("광통신", "2차전지")}  # 업종 관계 없는 우연 묶음


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
        if k >= min_together and lift >= min_lift and (a, b) not in SIM_EXCLUDE and (b, a) not in SIM_EXCLUDE:
            out[a].append((round(lift, 1), b, k))
            out[b].append((round(lift, 1), a, k))
    return {t: [x[1] for x in sorted(v, reverse=True)[:3]] for t, v in out.items()}


US_W = float(os.environ.get('US_W', '1.0'))
FADE_W = float(os.environ.get('FADE_W', '0'))
EVENT_W = float(os.environ.get('EVENT_W', '0.3'))
MOM_W = float(os.environ.get('MOM_W', '0'))        # 테마별 이어짐 효과(근거 표시용, 점수엔 안 넣음: 2년 검증에서 효과 없음)
BREADTH_W = float(os.environ.get('BREADTH_W', '0.2'))  # 전날 급등 종목 수 가점 — 최근 60일 이어짐 비율이 높을 때만
REGIME_ON = float(os.environ.get('REGIME_ON', '0.28'))  # 2년 검증: 이 기준일 때 상위3 38.4%→39.5%, 앞·뒤 1년 모두 기준 이상
NXT_W = float(os.environ.get('NXT_W', '0'))


def events(day):
    try:
        ev = json.load(open(os.path.join(ROOT, "data", "ref", "events.json"), encoding="utf-8"))["events"]
    except (OSError, ValueError, KeyError):
        return []
    return [e for e in ev if e.get("date") == day]


def appearances(docs, days, upto):
    app = defaultdict(list)
    for d in days:
        if d >= upto:
            continue
        for t in docs[d]["main"]["themes"]:
            if ETC(t["name"]) or len(t["stocks"]) < 2:
                continue
            st = t["stocks"]
            top = max(st, key=lambda s: s.get("amt") or 0)["name"]
            app[t["name"]].append((d, top, st))
    return app


def basket(app, theme, k=3, n=5):
    """최근 k번 등장에서 자주(같으면 거래대금 큰 순) 오른 n종목."""
    cnt, amt = Counter(), Counter()
    for _, _, st in app.get(theme, [])[-k:]:
        for s in st:
            cnt[s["name"]] += 1
            amt[s["name"]] += s.get("amt") or 0
    return [x for x in sorted(cnt, key=lambda x: (-cnt[x], -amt[x]))[:n]]


def trend_basket(docs, days, theme, upto, n=5, window=60):
    """관련주 5종목 (10/6 개정 — 3개월 추세만 보면 스피어·센서뷰 같은 핵심 우주주가 빠지는 문제).
    1) 최근 3개월(60거래일) 달력에서 이 테마로 2번 이상 급등한 종목
    2) 네이버 테마 분류상 이 테마가 그 종목의 '주 테마'인 종목 우선 (예: RF머트리얼즈는 광통신이 주 테마라 방산에서 뒤로)
    3) 최근일수록 무게를 둔 등장 횟수(반감기 20거래일) 순, 같으면 3개월 주가 추세 순"""
    import trend
    from theme_map import Ref
    ref = _REF.setdefault("r", Ref())
    ds = [d for d in days if d < upto][-window:]
    w, k = Counter(), Counter()
    for i, d in enumerate(ds):
        wt = 0.5 ** ((len(ds) - 1 - i) / 20)
        for t in docs[d]["main"]["themes"]:
            if t["name"] == theme:
                for st in t["stocks"]:
                    w[st["name"]] += wt; k[st["name"]] += 1
    core = core_members(theme)
    rows = []
    for name in w:
        if core is not None:
            if name not in core:     # 핵심 네이버 테마에 없는 종목은 제외 (예: 보안 → CCTV·지문인식·AI데이터 제외)
                continue
        elif k[name] < 2:
            continue
        c = ref.canons(name=name)
        primary = not c or theme not in c or c[theme] >= max(c.values()) - 1e-9 if c else True
        if c and theme in c and c[theme] < max(c.values()) - 1e-9:
            primary = False
        if core is not None:
            primary = True       # 핵심 테마 소속이면 주 테마 여부는 따지지 않는다
        r = trend.ret(name, upto, window)
        rows.append((primary, round(w[name], 2), r if r is not None else -999, k[name], name))
    rows.sort(reverse=True)
    if len(rows) < n:   # 2번 이상 등장 종목이 모자라면 1번 등장 종목으로 채운다
        extra = sorted(((w[x], x) for x in w if k[x] == 1), reverse=True)
        rows += [(False, round(a, 2), trend.ret(x, upto, window) or -999, 1, x) for a, x in extra[: n - len(rows)]]
    return [{"name": nm, "ret60": (r if r != -999 else None), "times": kk, "primary": pr} for pr, _, r, kk, nm in rows[:n]]


_REF = {}
# 테마별 '핵심' 네이버 테마와 사업 설명 키워드 — 여기에 맞는 종목만 관련주로 쓴다
#   (보안: CCTV·지문인식·보안인쇄·AI데이터 같은 주변 종목이 섞이는 문제, 우주항공: 알루미늄 등 주변 종목)
CORE = {"보안": (["보안주(정보)"], r"정보보안|보안 ?솔루션|보안 ?소프트웨어|사이버|해킹|관제|인증|암호|백신|위협|네트워크 보안|PKI|보안·인증|보안 플랫폼", r"인쇄|CCTV|지문"),
        "우주항공": (["스페이스X(SpaceX)", "우주항공산업(누리호/인공위성 등)"], r"우주|위성|스페이스|발사|항공|누리호", r"알루미늄 ?압출"),
        "방산": (["방위산업/전쟁 및 테러"], r"방산|방위산업|국방|군용|군수|군사|무기|미사일|유도|탄약|전차|자주포|박격포|전자전|드론",
                 r"수입판매|보도채널|자동차 그룹|조선 및 건설")}


def core_members(theme):
    import re
    if theme not in CORE:
        return None
    if "nt" not in _REF:
        _REF["nt"] = json.load(open(os.path.join(ROOT, "data", "ref", "naver_themes.json"), encoding="utf-8"))
    nt = _REF["nt"]
    tns, inc, exc = CORE[theme]
    out = set()
    for tn in tns:
        t = nt["themes"].get(tn)
        if not t:
            continue
        for c in t["codes"]:
            r = nt["reasons"].get(f"{t['no']}:{c}") or ""
            if re.search(inc, r) and not (exc and re.search(exc, r)):
                out.add(nt["names"].get(c))
    return out


def leader_keep(app, theme):
    a = app.get(theme, [])
    if len(a) < 5:
        return None
    return round(sum(x[1] == y[1] for x, y in zip(a, a[1:])) / (len(a) - 1), 2)


def nxt_flow(docs, days, day):
    """전 거래일 본장 테마별 넥장 평균 추가 등락(통합 최종가 vs KRX 종가)."""
    prev = [d for d in days if d < day]
    if not prev:
        return {}
    p = prev[-1]
    try:
        nm = json.load(open(os.path.join(ROOT, "data", p, "after.json"), encoding="utf-8")).get("nxt_map") or {}
    except (OSError, ValueError):
        return {}
    out = {}
    for t in docs[p]["main"]["themes"]:
        v = [nm[s["name"]]["after"] for s in t["stocks"] if s["name"] in nm and isinstance(nm[s["name"]].get("after"), (int, float))]
        if len(v) >= 2:
            out[t["name"]] = round(sum(v) / len(v), 2)
    return out


def score(day, data, loo=False):
    docs, days, lead, seen, ret, groups, us_dates, long = data
    hist = [d for d in long["days"] if d < day]
    last20 = hist[-20:]
    base = Counter(t for d in last20 for t in long["L"][d])
    # 규칙 크기(미국 연동·모멘텀)는 긴 기록으로, 테마 고르기(기본 점수)는 최근 20거래일로
    rates = link_rates(long["days"], long["L"], ret, groups, us_dates, exclude=day if loo else None)
    # 복원 달력에 거의 안 잡히는 테마(예: 광통신 — 네이버 분류에선 통신장비로 묶임)는 실제 달력만으로 잰다
    real = set(days)
    cover = Counter(t for d in long["days"] if d not in real for t in long["L"][d])
    short = link_rates(days, lead, ret, groups, us_dates, exclude=day if loo else None)
    for t in short:
        if cover[t] < 20:
            rates[t] = short[t]
    mom = momentum(long, day, exclude=day if loo else None)
    sig, u = us_signal(day, ret, groups, us_dates, hist[-1] if hist else None)
    yday = long["L"][hist[-1]] if hist else set()
    ypres = long["P"][hist[-1]] if hist else {}
    rg = regime(long, day)
    breadth_on = (rg["recent"] or 0) >= REGIME_ON
    ev = events(day)
    evt = defaultdict(list)
    for e in ev:
        for t in e.get("themes", []):
            evt[t].append(e)
    nflow = nxt_flow(docs, days, day)
    cands = set(base) | set(sig) | yday | set(evt) | {t for t, n in ypres.items() if n >= 5}
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
        for e in evt.get(t, []):
            s += EVENT_W * e.get("weight", 1.0); reason.append(f"일정: {e['what']}")
        if t in nflow and abs(nflow[t]) >= 1:
            s += NXT_W * nflow[t] / 10; reason.append(f"전날 넥장 {nflow[t]:+.1f}%")
        m = mom.get(t)
        if t in yday:
            e = max(0, m["led"]) if m else 0
            s += MOM_W * e; reason.append(f"전날 주도 (2년 기록 이어짐 효과 {e * 100:+.0f}%p)" if m else "전날 주도")
        if ypres.get(t, 0) and breadth_on:
            s += BREADTH_W * min(ypres[t], 8) / 8; reason.append(f"전날 {ypres[t]}종목 급등 (이어지는 장세 가점)")
        elif ypres.get(t, 0) >= 5 and t not in yday:
            reason.append(f"전날 {ypres[t]}종목 급등")
        rows.append((round(s, 3), t, " · ".join(reason)))
    # 동점이면 최근 20일 주도 횟수 → 미국 짝 등락이 큰 순 (테마 이름 순서로 정해지지 않게)
    rows.sort(key=lambda r: (r[0], base[r[1]], sig.get(r[1], -99)), reverse=True)
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


def backtest_long(start=280):
    """긴 기록(복원 2년 + 실제)으로 검증. 각 날짜 이전 정보만 사용. 기본 vs 모멘텀 vs 미국 vs 둘 다."""
    global BREADTH_W, US_W
    data = load()
    long = data[7]
    ds = long["days"]
    res = defaultdict(lambda: [0, 0, 0, 0])
    for i in range(start, len(ds)):
        d = ds[i]
        for name, (bw, uw) in {"기본": (0, 0), "+급등수(경고등)": (0.2, 0), "+미국": (0, 1), "+둘다": (0.2, 1)}.items():
            BREADTH_W, US_W = bw, uw
            rows, _, _ = score(d, data)
            for k, idx in ((3, 0), (5, 2)):
                h = len({t for _, t, _ in rows[:k]} & long["L"][d])
                res[name][idx] += h; res[name][idx + 1] += h > 0
    n = len(ds) - start
    for name, (h3, a3, h5, a5) in res.items():
        print(f"{name:6s} 상위3 적중 {h3 / (3 * n):.1%} (하루1개+ {a3 / n:.0%}) · 상위5 {h5 / (5 * n):.1%} (하루1개+ {a5 / n:.0%})  {n}거래일")


def main():
    if "--backtest" in sys.argv:
        backtest()
        return
    if "--backtest-long" in sys.argv:
        backtest_long()
        return
    day = sys.argv[1]
    data = load()
    rows, sig, u = score(day, data)
    sim = similar(data[1], data[3], day)
    app = appearances(data[0], data[1], day)
    out = {"day": day, "us_date": u, "us_signal": {k: round(v, 2) for k, v in sig.items()},
           "events": events(day), "nxt_flow": nxt_flow(data[0], data[1], day), "regime": regime(data[7], day),
           "baskets": {t: trend_basket(data[0], data[1], t, day) for t in
                       {x["name"] for d in [x for x in data[1] if x < day][-60:] for x in data[0][d]["main"]["themes"] if not ETC(x["name"])}},
           "ranking": [{"theme": t, "score": s, "why": w, "similar": sim.get(t, []),
                        "basket": [b["name"] for b in trend_basket(data[0], data[1], t, day)],
                        "basket_detail": trend_basket(data[0], data[1], t, day), "leader_keep": leader_keep(app, t)} for s, t, w in rows[:10]]}
    json.dump(out, open(os.path.join(ROOT, "data", "ref", "pre_score.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    rg = out["regime"]
    print(f"{day} (미국 {u})  전날 주도 테마가 다음날도 주도한 비율: 최근60일 {rg['recent']} / 긴 기록 {rg['long']}"
          f" → 급등 종목 수 가점 {'켜짐' if (rg['recent'] or 0) >= REGIME_ON else '꺼짐(순환이 빠른 장세)'}")
    for r in out["ranking"]:
        print(f"{r['score']:6.3f} {r['theme']:10s} {r['why']}  유사: {', '.join(r['similar'])}")
        rel = ", ".join("%s(%s회, %s)" % (b["name"], b["times"], "-" if b["ret60"] is None else "%+.0f%%" % b["ret60"]) for b in r["basket_detail"])
        print(f"        관련주(3개월 핵심 종목): {rel}  (대장 유지율 {r['leader_keep'] if r['leader_keep'] is not None else '-'})")
    if "--emit" in sys.argv:
        emit(sys.argv[sys.argv.index("--emit") + 1], day, out, sig, data)


def emit(path, day, out, sig, data):
    """데이터대로만: 점수 순 상위 5개를 그대로 예측으로 쓴다(순서를 판단으로 바꾸지 않는다).
    뉴스·일정은 미리 data/ref/events.json 에 고정 가중치로 넣어 점수에 반영한 뒤 이 명령을 돌린다."""
    from datetime import datetime, timedelta, timezone
    ret = data[4]
    long = data[7]
    prev_kr = ([d for d in long["days"] if d < day] or [None])[-1]
    def last(sym):
        """직전 한국 거래일 이후 미국 거래일(들) 누적 등락"""
        r = ret.get(sym) or {}
        ds = [d for d in sorted(r) if d < day]
        us = [d for d in ds if prev_kr and d >= prev_kr] or ds[-1:]
        if not us:
            return None, None
        acc = 1.0
        for d in us:
            acc *= 1 + r[d] / 100
        return us[-1], (acc - 1) * 100
    market = []
    for sym, label in (("^IXIC", "나스닥"), ("^GSPC", "S&P500"), ("^SOX", "美 반도체"), ("CL=F", "WTI"), ("KRW=X", "원/달러")):
        d, v = last(sym)
        if v is not None:
            market.append({"label": label, "value": f"{v:+.2f}%", "dir": "up" if v > 0 else "down" if v < 0 else ""})
    themes = []
    for r in out["ranking"][:5]:
        rel = "·".join(b["name"] for b in r["basket_detail"])
        themes.append({"name": r["theme"], "why": r["why"], "note": f"관련주 {rel}" if rel else "",
                       "src": ["base"] + (["us"] if "미국 짝" in r["why"] and "연관 약함" not in r["why"] else [])
                              + (["event"] if "일정:" in r["why"] else [])})
    # 조심 테마: 미국 짝이 -2% 이하인 테마(연관 확인된 테마 우선). 없으면 비운다.
    neg = sorted((v, t) for t, v in sig.items() if v <= -2)
    warn = f"{neg[0][1]} — 미국 짝 종목 평균 {neg[0][0]:+.1f}%" if neg else ""
    pre = {"time": datetime.now(timezone(timedelta(hours=9))).strftime("%H:%M"), "market": market,
           "themes": themes, "warn": warn, "method": "data-only v2026-10-06"}
    json.dump(pre, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("emit →", path, [t["name"] for t in themes], "| 조심:", warn or "없음")


if __name__ == "__main__":
    main()

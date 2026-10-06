"""전체 점검: 그날 급등 목록(검증된 종가 기준)의 모든 종목이 테마에 들어갔는지 확인하고 빠진 종목을 채운다.

  python3 scripts/audit_days.py <lists.json> [--write]

- lists.json: {날짜: [{name, code, chg, amount_eok, new}]} (KRX 정규장 7% 이상, 50~90종목)
- 기존 테마와 종목(기사로 확인한 이유)은 그대로 두고, 등락률만 검증값으로 맞춘다.
- 빠진 종목은 네이버 테마 분류로 그날 있는 테마에 넣고, 같은 분류가 2종목 이상이면 새 테마로 묶는다.
  나머지는 "기타(개별)". 신규 상장 첫날 종목은 "신규상장주".
- 주도 테마(lead)는 종목 수·거래대금 순위로 다시 정한다(기타·신규상장 제외, 상위 3개).
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from theme_map import Ref  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RENAME = {"2차전지 소재": "2차전지", "헬스케어": "의료AI·의료기기", "정유": "정유·화학",
          "고유가 수혜": "정유·화학", "AI 반도체": "반도체"}
SKIP_LEAD = ("기타(개별)", "신규상장주")
GENERIC_PREFIX = {"한국", "대한", "동양", "우리", "신성", "대성", "삼성", "현대", "한일", "대동", "동국", "세아", "서울", "대원",
                  "한국", "아이", "에스", "케이", "디에", "엘에", "티에", "제이", "코리", "유니", "에이", "엔에", "비에",
                  "와이", "오리", "글로", "인터", "디지", "바이", "메디", "파워", "그린", "뉴로", "에코", "하이", "세종",
                  "동아", "대우", "금호", "한솔", "효성", "동원", "태영", "신세", "롯데", "엘지", "에스케", "코스", "제일", "소프", "미래", "한미", "대한", "진흥"}
SUB = {"MLCC": "MLCC·수동부품", "PCB": "기판", "반도체 기판": "기판"}


def is_etc(name):
    return name.startswith("기타") or "개별" in name


def audit(day, doc, lst, ref, amount_of):
    main = doc.get("main") or {}
    themes = main.get("themes") or []
    # 1) 이름 통일 + 같은 이름 합치기
    merged = {}
    order = []
    for t in themes:
        t["name"] = RENAME.get(t["name"], t["name"])
        if t["name"] in merged:
            m = merged[t["name"]]
            have = {s["name"] for s in m["stocks"]}
            m["stocks"] += [s for s in t["stocks"] if s["name"] not in have]
            m["lead"] = bool(m.get("lead") or t.get("lead"))
        else:
            merged[t["name"]] = t
            order.append(t["name"])
    themes = [merged[n] for n in order]
    by_name = {t["name"]: t for t in themes}
    verified = {x["name"]: x for x in lst}
    placed = set()
    for t in themes:
        for s in t["stocks"]:
            placed.add(s["name"])
            v = verified.get(s["name"])
            if v and isinstance(s.get("chg"), (int, float)) and abs(s["chg"] - v["chg"]) >= 0.05:
                s["chg"] = round(v["chg"], 2)
            if v and v["chg"] >= 29.5:
                s["limit"] = True
    added = []
    missing = [x for x in lst if x["name"] not in placed]
    rest = []

    def add(theme_name, x, canon=None):
        t = by_name.get(theme_name)
        if not t:
            t = {"name": theme_name, "reason": "", "stocks": []}
            themes.append(t)
            by_name[theme_name] = t
        code = x.get("code") or ref.by_name.get(x["name"])
        if theme_name == "신규상장주":
            reason = "신규 상장 첫날 급등"
        else:
            desc = ref.describe(code, canon or theme_name) if code else ""
            reason = (desc + " · " if desc else "") + f"{theme_name} 동반 강세"
        s = {"name": x["name"], "chg": round(x["chg"], 2), "reason": reason, "tag": "동반", "auto": True}
        if theme_name == "신규상장주":
            s.pop("tag")
        if x["chg"] >= 29.5:
            s["limit"] = True
        if theme_name == "전자부품":
            s["sub"] = "기타 부품"
        t["stocks"].append(s)
        placed.add(x["name"])
        added.append((theme_name, x["name"]))

    # 2-0) 우선주는 본주와 같은 테마로
    def base_of(nm):
        b = re.sub(r"(\d?우[A-Z]?|\(전환\))$", "", nm)
        return b if b != nm else None
    order_missing = sorted(missing, key=lambda x: 1 if base_of(x["name"]) else 0)
    missing = order_missing
    # 2) 신규 상장 / 그날 있는 테마에 넣기
    for x in missing:
        b = base_of(x["name"])
        if b:
            home = next((t for t in themes if any(s["name"] == b for s in t["stocks"])), None)
            if home:
                s = {"name": x["name"], "chg": round(x["chg"], 2), "reason": f"{b} 우선주, 본주 동반 강세", "tag": "동반", "auto": True}
                if x["chg"] >= 29.5:
                    s["limit"] = True
                if home["name"] == "전자부품":
                    s["sub"] = next((s2.get("sub") for s2 in home["stocks"] if s2["name"] == b), "기타 부품")
                home["stocks"].append(s)
                placed.add(x["name"])
                added.append((home["name"], x["name"]))
                continue
        if x.get("new"):
            add("신규상장주", x)
            continue
        cs = ref.canons(code=x.get("code"), name=x["name"])
        cand = [c for c in cs if c in by_name and not is_etc(c)]
        if cand:
            best = max(cand, key=lambda c: cs[c] + 0.1 * min(len(by_name[c]["stocks"]), 10))
            add(best, x, best)
        else:
            rest.append(x)
    # 3) 같은 분류끼리 2종목 이상이면 새 테마
    while True:
        cnt = {}
        for x in rest:
            for c in ref.canons(code=x.get("code"), name=x["name"]):
                cnt[c] = cnt.get(c, 0) + 1
        if not cnt:
            break
        c, n = max(cnt.items(), key=lambda kv: kv[1])
        if n < 2:
            break
        keep = []
        for x in rest:
            if c in ref.canons(code=x.get("code"), name=x["name"]):
                add(c, x, c)
            else:
                keep.append(x)
        by_name[c]["reason"] = by_name[c]["reason"] or f"{c} 관련주 동반 강세 (개별 뉴스 미확인)"
        rest = keep
    # 3-1) 같은 그룹 이름(앞 두 글자)으로 2종목 이상 오르면 그룹주로 묶기
    groups = {}
    for x in rest:
        pre = x["name"][:2]
        if len(pre) == 2 and all("가" <= ch <= "힣" for ch in pre) and pre not in GENERIC_PREFIX:
            groups.setdefault(pre, []).append(x)
    for pre, xs in groups.items():
        if len(xs) >= 2:
            names_ = [x["name"] for x in xs]
            lcp = names_[0]
            for nm in names_[1:]:
                while not nm.startswith(lcp):
                    lcp = lcp[:-1]
            gname = f"{lcp} 본주·우선주" if lcp in names_ else f"{lcp}그룹주"
            pre = lcp
            for x in xs:
                t = by_name.get(gname)
                if not t:
                    t = {"name": gname, "reason": f"{pre} 계열사 동반 급등", "stocks": []}
                    themes.append(t)
                    by_name[gname] = t
                s = {"name": x["name"], "chg": round(x["chg"], 2), "reason": f"{pre} 계열사 동반 강세", "tag": "동반", "auto": True}
                if x["chg"] >= 29.5:
                    s["limit"] = True
                t["stocks"].append(s)
                added.append((gname, x["name"]))
            rest = [x for x in rest if x not in xs]
    # 4) 나머지는 기타(개별)
    for x in rest:
        t = by_name.get("기타(개별)")
        if not t:
            t = {"name": "기타(개별)", "reason": "개별 재료 또는 이유 미확인", "stocks": []}
            themes.append(t)
            by_name["기타(개별)"] = t
        code = x.get("code") or ref.by_name.get(x["name"])
        cs = ref.canons(code=code)
        hint = max(cs, key=cs.get) if cs else ""
        desc = ref.describe(code, hint) if code and hint else ""
        s = {"name": x["name"], "chg": round(x["chg"], 2), "reason": (desc + " · " if desc else "") + "이유 미확인", "auto": True}
        if x["chg"] >= 29.5:
            s["limit"] = True
        t["stocks"].append(s)
        added.append(("기타(개별)", x["name"]))
    # 전자부품 세부분류
    for t in themes:
        if t["name"] == "전자부품":
            for s in t["stocks"]:
                if not s.get("sub"):
                    s["sub"] = "기타 부품"
    # 5) 정렬·주도 테마
    for t in themes:
        t["stocks"].sort(key=lambda s: -(s["chg"] if isinstance(s.get("chg"), (int, float)) else -1e9))
        if not t.get("reason"):
            t["reason"] = f"{t['name']} 관련주 동반 강세"
    # 종목별 본장 거래대금(억원)
    for t in themes:
        for s in t["stocks"]:
            v = amount_of.get(s["name"])
            if isinstance(v, (int, float)):
                s["amt"] = int(round(v))
    scored = []
    for t in themes:
        if t["name"] in SKIP_LEAD or is_etc(t["name"]):
            continue
        amt = sum(amount_of.get(s["name"], 0) for s in t["stocks"])
        scored.append((len(t["stocks"]), amt, t["name"]))
    # 주도 테마: 종목 수 비중 + 거래대금 비중 합계 상위 3개 (2종목 이상, 기타·신규상장 제외)
    tot_n = sum(c for c, _, _ in scored) or 1
    tot_a = sum(a for _, a, _ in scored) or 1
    top = sorted(scored, key=lambda x: -(x[0] / tot_n + x[1] / tot_a))
    old_leads = {t["name"] for t in themes if t.get("lead")}
    leads = set([n for c, a, n in top if c >= 2][:3])
    for t in themes:
        if t["name"] in leads:
            t["lead"] = True
        else:
            t.pop("lead", None)
    key = {n: i for i, (_, _, n) in enumerate(top)}
    themes.sort(key=lambda t: (0 if t.get("lead") else 1, 2 if is_etc(t["name"]) else (1 if t["name"] == "신규상장주" else 0),
                               key.get(t["name"], 99), -len(t["stocks"])))
    main["themes"] = themes
    n = len(lst)
    main["basis"] = f"KRX 정규장 급등 {n}종목 전체 분류 (기사 확인 + 네이버 테마 분류 보완)"
    doc["main"] = main
    return added, old_leads, leads


def main():
    lists = json.load(open(sys.argv[1], encoding="utf-8"))
    write = "--write" in sys.argv
    ref = Ref()
    report = {}
    for day, lst in sorted(lists.items()):
        path = os.path.join(ROOT, "themes", "days", f"{day}.json")
        if not os.path.exists(path):
            continue
        doc = json.load(open(path, encoding="utf-8"))
        if doc.get("status") == "holiday" or not doc.get("main"):
            continue
        amount_of = {x["name"]: x.get("amount_eok", 0) for x in lst}
        added, old, new = audit(day, doc, lst, ref, amount_of)
        report[day] = {"added": len(added), "old_leads": sorted(old), "new_leads": sorted(new),
                       "themes": [(t["name"], len(t["stocks"])) for t in doc["main"]["themes"]]}
        if write:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(doc, f, ensure_ascii=False)
    json.dump(report, open(os.path.join(ROOT, "data", "ref", "audit_report.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("days", len(report), "added", sum(r["added"] for r in report.values()))


if __name__ == "__main__":
    main()

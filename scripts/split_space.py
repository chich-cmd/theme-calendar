"""1회성: 달력 기록의 '방산·우주항공' 테마를 '우주항공'과 '방산'으로 나누고 주도 테마를 다시 계산한다."""
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from theme_map import Ref  # noqa: E402

SPACE_KW = re.compile(r"우주|위성|스페이스|발사|누리호|로켓|항공기|항공 ?부품|UAM|에어로|궤도|저궤도|탐사")
DEF_KW = re.compile(r"방산|방위|무기|미사일|전쟁|탄약|국방|군|K-?9|K2|레드백|천무|수출 계약|드론|전차|함정|레이더")
SPACE_NAMES = {"스피어", "센서뷰", "나라스페이스테크놀로지", "에이치브이엠", "켄코아에어로스페이스", "와이제이링크", "나노팀",
               "쎄트렉아이", "인텔리안테크", "AP위성", "컨텍", "이노스페이스", "제노코", "루미르", "한컴인스페이스", "비츠로넥스텍",
               "모델솔루션", "이녹스첨단소재", "미래에셋벤처투자", "아주IB투자", "에이치브이엠", "케이피항공산업", "스피어"}
SKIP = ("기타(개별)", "신규상장주")
ref = Ref()


def side(s):
    n = s["name"]
    if n in SPACE_NAMES:
        return "우주항공"
    r = s.get("reason") or ""
    sp, df = bool(SPACE_KW.search(r)), bool(DEF_KW.search(r))
    if sp and not df:
        return "우주항공"
    if df and not sp:
        return "방산"
    c = ref.canons(name=n)
    a, b = c.get("우주항공", 0), c.get("방산", 0)
    if a or b:
        return "우주항공" if a >= b else "방산"
    return "방산"


def relead(themes):
    scored = []
    for t in themes:
        if t["name"] in SKIP or t["name"].startswith("기타"):
            continue
        scored.append((len(t["stocks"]), sum(s.get("amt") or 0 for s in t["stocks"]), t["name"]))
    tn = sum(c for c, _, _ in scored) or 1
    ta = sum(a for _, a, _ in scored) or 1
    top = sorted(scored, key=lambda x: -(x[0] / tn + x[1] / ta))
    leads = set([n for c, a, n in top if c >= 2][:3])
    for t in themes:
        if t["name"] in leads:
            t["lead"] = True
        else:
            t.pop("lead", None)
    key = {n: i for i, (_, _, n) in enumerate(top)}
    themes.sort(key=lambda t: (0 if t.get("lead") else 1, 2 if t["name"].startswith("기타") else (1 if t["name"] == "신규상장주" else 0),
                               key.get(t["name"], 99), -len(t["stocks"])))


def split_list(themes, recompute):
    out, changed = [], False
    for t in themes:
        if t["name"] != "방산·우주항공":
            out.append(t)
            continue
        changed = True
        g = {"우주항공": [], "방산": []}
        for s in t["stocks"]:
            g[side(s)].append(s)
        for nm in ("우주항공", "방산"):
            if g[nm]:
                nt = {k: v for k, v in t.items() if k not in ("stocks", "lead", "name")}
                nt["name"] = nm
                nt["stocks"] = g[nm]
                if nt.get("reason") and nm == "우주항공" and "방산" in nt["reason"] and not g["방산"]:
                    nt["reason"] = nt["reason"].replace("방산·", "").replace("방산", "")
                out.append(nt)
    # 같은 이름이 이미 있으면 합친다
    merged = {}
    for t in out:
        if t["name"] in merged:
            merged[t["name"]]["stocks"] += t["stocks"]
        else:
            merged[t["name"]] = t
    out = list(merged.values())
    if changed and recompute:
        relead(out)
    return out, changed


def rename_list(items):
    ch = False
    for p in items:
        if p.get("name") == "방산·우주항공":
            p["name"] = "우주항공"; ch = True
    return ch


def main():
    changed_days = []
    for p in sorted(glob.glob(os.path.join(ROOT, "themes", "days", "*.json"))):
        doc = json.load(open(p, encoding="utf-8"))
        ch = False
        if (doc.get("main") or {}).get("themes"):
            doc["main"]["themes"], c = split_list(doc["main"]["themes"], True); ch |= c
        if (doc.get("after") or {}).get("themes"):
            doc["after"]["themes"], c = split_list(doc["after"]["themes"], False); ch |= c
        pre = doc.get("pre") or {}
        if pre.get("themes"):
            ch |= rename_list(pre["themes"])
        pm = pre.get("pm") or {}
        if pm.get("themes"):
            pm["themes"], c = split_list(pm["themes"], False); ch |= c
            for k in ("confirm", "new"):
                if "방산·우주항공" in pm.get(k, []):
                    pm[k] = ["우주항공" if x == "방산·우주항공" else x for x in pm[k]]; ch = True
        if ch:
            json.dump(doc, open(p, "w", encoding="utf-8"), ensure_ascii=False)
            changed_days.append(os.path.basename(p)[:-5])
    print(len(changed_days), "days changed")
    json.dump(changed_days, open(os.path.join(ROOT, "data", "ref", "split_days.json"), "w"), indent=0)


if __name__ == "__main__":
    main()

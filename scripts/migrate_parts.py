"""전자부품 계열 테마를 하나의 "전자부품" 테마로 합치고, 종목마다 세부 분류(sub)를 붙인다.

  python scripts/migrate_parts.py <입력폴더> <출력폴더>

입력폴더의 YYYY-MM-DD.json 중 바뀐 문서만 출력폴더에 같은 이름으로 쓰고, 바뀐 날짜를 출력한다.
"""
import glob
import json
import os
import sys

SRC = {"전자부품(MLCC)": "MLCC·수동부품", "PCB·기판": "기판", "전자부품": None}
SUB_BY_NAME = {
    "MLCC·수동부품": ["삼성전기", "삼성전기우", "삼화콘덴서", "아모텍", "코칩"],
    "기판": ["대덕전자", "코리아써키트", "티엘비", "심텍", "이수페타시스", "해성디에스", "기가비스"],
}


def sub_for(name, default):
    for sub, names in SUB_BY_NAME.items():
        if name in names:
            return sub
    return default or "기타 부품"


def migrate(doc):
    changed = False
    for sec in ("main", "after"):
        themes = (doc.get(sec) or {}).get("themes")
        if not themes:
            continue
        out, merged = [], None
        for t in themes:
            if t.get("name") not in SRC:
                out.append(t)
                continue
            changed = True
            default = SRC[t["name"]]
            stocks = []
            for s in t.get("stocks", []):
                s = dict(s)
                s["sub"] = s.get("sub") or sub_for(s["name"], default)
                stocks.append(s)
            if merged is None:
                merged = {"name": "전자부품", "reason": t.get("reason", ""), "stocks": stocks}
                for k in ("lead", "kind"):
                    if t.get(k):
                        merged[k] = t[k]
                out.append(merged)
            else:
                merged["stocks"] += stocks
                if t.get("lead"):
                    merged["lead"] = True
                if t.get("reason") and t["reason"] not in merged["reason"]:
                    merged["reason"] = (merged["reason"] + " / " + t["reason"]).strip(" /")
        if merged:
            seen, uniq = set(), []
            for s in sorted(merged["stocks"], key=lambda x: -(x["chg"] if isinstance(x.get("chg"), (int, float)) else -1e9)):
                if s["name"] not in seen:
                    seen.add(s["name"])
                    uniq.append(s)
            merged["stocks"] = uniq
        doc[sec]["themes"] = out
    return changed


def main():
    src, dst = sys.argv[1], sys.argv[2]
    os.makedirs(dst, exist_ok=True)
    for p in sorted(glob.glob(os.path.join(src, "*.json"))):
        with open(p, encoding="utf-8") as f:
            doc = json.load(f)
        if migrate(doc):
            with open(os.path.join(dst, os.path.basename(p)), "w", encoding="utf-8") as f:
                json.dump(doc, f, ensure_ascii=False)
            print(os.path.basename(p)[:-5])


if __name__ == "__main__":
    main()

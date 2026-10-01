"""themes/days/*.json → 월별 묶음 themes/YYYY-MM.json 과 목록 themes/months.json 생성 (GitHub Actions가 실행)"""
import glob
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
days = {}
for p in sorted(glob.glob(os.path.join(ROOT, "themes", "days", "*.json"))):
    d = os.path.basename(p)[:-5]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d):
        continue
    with open(p, encoding="utf-8") as f:
        days[d] = json.load(f)

months = {}
for d, doc in days.items():
    months.setdefault(d[:7], {})[d] = doc

for old in glob.glob(os.path.join(ROOT, "themes", "????-??.json")):
    if os.path.basename(old)[:-5] not in months:
        os.remove(old)
for m, docs in months.items():
    with open(os.path.join(ROOT, "themes", f"{m}.json"), "w", encoding="utf-8") as f:
        json.dump(docs, f, ensure_ascii=False, separators=(",", ":"))

summary = {m: sum(1 for x in docs.values() if x.get("status") != "holiday") for m, docs in sorted(months.items())}
with open(os.path.join(ROOT, "themes", "months.json"), "w", encoding="utf-8") as f:
    json.dump({"months": summary, "latest": max(days) if days else None}, f, ensure_ascii=False)
print("built", len(days), "days in", len(months), "months")

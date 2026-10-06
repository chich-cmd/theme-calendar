"""밤사이 뉴스 제목·요약 → catalyst_map 대응 찾기 (07:00 예측 작업 보조).

  python3 scripts/catalyst_match.py /tmp/news.txt     (한 줄에 뉴스 하나: "제목 | 요약")
→ 줄마다 걸린 catalyst id, 달력 테마, 국내 관련주를 출력. 맞는 게 없으면 '미대응'으로 표시 → catalyst_map 에 새로 추가할 후보.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load():
    return json.load(open(os.path.join(ROOT, "data", "ref", "catalyst_map.json"), encoding="utf-8"))["catalysts"]


def match(text, cats=None):
    cats = cats or load()
    low = text.lower()
    hits = []
    for cid, c in cats.items():
        k = sum(1 for kw in c["keywords"] if kw.lower() in low)
        if k:
            hits.append((k, cid))
    return [cid for _, cid in sorted(hits, reverse=True)]


def main():
    cats = load()
    for line in open(sys.argv[1], encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        ids = match(line, cats)
        if not ids:
            print("미대응 |", line[:80]); continue
        for cid in ids[:2]:
            c = cats[cid]
            print(f"{cid:14s} → {c['theme']:10s} {'·'.join(c['stocks'][:6])} | {line[:60]}")


if __name__ == "__main__":
    main()

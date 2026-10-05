"""전 종목 최근 약 6개월(130거래일) 종가 → data/hist/closes.json.gz. 매주 hist 워크플로에서 갱신.
관련주 '최근 2~3개월 추세' 계산과 눌림 검증에 쓴다. 그 사이 날짜는 매일 저장되는 data/<날짜>/krx.json 종가로 이어 붙인다."""
import gzip
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
import glob

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hist_fetch import fetch, ROOT  # noqa: E402


def main():
    krx = json.load(open(sorted(glob.glob(os.path.join(ROOT, "data", "20*", "krx.json")))[-1], encoding="utf-8"))
    out = {}
    with ThreadPoolExecutor(8) as ex:
        for code, rows in ex.map(fetch, list(krx)):
            if rows:
                out[code] = [krx[code][0], [[r[0], r[1]] for r in rows[-130:]]]
    with gzip.open(os.path.join(ROOT, "data", "hist", "closes.json.gz"), "wt", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print("stocks", len(out))


if __name__ == "__main__":
    main()

"""눌림 검증용(1회성): 전 종목 일봉 종가를 data/hist/closes.json.gz 로 저장. 수동 실행."""
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
                out[code] = [krx[code][0], [[r[0], r[1]] for r in rows]]
    with gzip.open(os.path.join(ROOT, "data", "hist", "closes.json.gz"), "wt", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print("stocks", len(out))


if __name__ == "__main__":
    main()

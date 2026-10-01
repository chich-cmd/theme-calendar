"""안전장치: Claude 분석이 아직(또는 실패로) 기록되지 않았으면 수집 데이터로 기본 기록을 만든다.

  python scripts/fallback.py main|after

themes/days/<오늘>.json 에 해당 구간(main/after)이 이미 있으면 아무것도 하지 않는다.
Claude 분석 작업이 나중에 같은 파일을 덮어쓰면 분석본으로 바뀐다.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TODAY = datetime.now(KST).strftime("%Y-%m-%d")


def load(p):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def main(kind):
    src = load(os.path.join(ROOT, "data", TODAY, f"{kind}.json"))
    if not src:
        print("no collected data"); return
    path = os.path.join(ROOT, "themes", "days", f"{TODAY}.json")
    doc = load(path) or {"date": TODAY}
    if doc.get(kind) or doc.get("status") == "holiday":
        print("already has", kind); return
    now = datetime.now(KST).isoformat(timespec="seconds")
    if src.get("status") == "closed":
        if not doc.get("main") and not doc.get("after"):
            doc.update({"status": "holiday", "note": "휴장"})
        else:
            return
    elif kind == "main":
        st = src.get("stocks", [])
        doc["status"] = "open"
        doc["main"] = {
            "kospi": src.get("kospi", ""), "kosdaq": src.get("kosdaq", ""), "auto": True,
            "summary": "테마 분석 전 자동 수집 결과입니다. 분석이 끝나면 테마별로 바뀝니다.",
            "basis": f"KRX 정규장 급등 {len(st)}종목 (자동 수집)", "updatedAt": now,
            "themes": [{"name": "급등 종목", "reason": "등락률 상위 (분석 대기)", "stocks": [
                {"name": s["name"], "chg": s["chg"], "reason": f"거래대금 {s.get('amount_eok', 0)}억", **({"limit": True} if s.get("limit") else {})}
                for s in st[:30]]}],
            "sources": [],
        }
    else:
        st = src.get("stocks", [])
        doc.setdefault("status", "open")
        doc["after"] = {
            "updatedAt": now, "auto": True,
            "basis": f"NXT 장후 거래 확인, 종가 대비 3% 이상 상승 {len(st)}종목 (자동 수집)",
            "watch": "" if st else "장후 3% 이상 상승한 종목이 없었습니다.",
            "themes": ([{"name": "장후 상승 종목", "kind": "신규", "reason": "종가 대비 장후 상승 (분석 대기)", "stocks": [
                {"name": s["name"], "chg": s["after_chg"], "reason": f"NXT 거래대금 {s.get('nxt_amount_eok', 0)}억"}
                for s in st[:20]]}] if st else []),
            "sources": [],
        }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False)
    print("wrote fallback", kind)


if __name__ == "__main__":
    main(sys.argv[1])

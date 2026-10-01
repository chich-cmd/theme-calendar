"""Claude 분석 작업용: 분석 결과 한 구간(main/after)을 공개 달력에 반영하고 push 한다.

  python3 scripts/publish_section.py main /tmp/main_section.json [YYYY-MM-DD]
  python3 scripts/publish_section.py after /tmp/after_section.json
  python3 scripts/publish_section.py holiday "휴장 사유"
  python3 scripts/publish_section.py log "메시지"          # 실행 기록만 남김

입력 파일은 main 또는 after 객체 하나(JSON)입니다. 다른 구간은 그대로 둡니다.
저장소 루트에서 실행합니다. 성공하면 "OK", 실패하면 "FAIL: 이유"를 출력합니다.
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def sh(*args):
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True)


def push(msg, paths):
    sh("git", "add", *paths)
    if sh("git", "diff", "--cached", "--quiet").returncode == 0:
        return "nothing to commit"
    r = sh("git", "-c", "user.name=Claude", "-c", "user.email=noreply@anthropic.com", "commit", "-m", msg)
    if r.returncode:
        return "commit failed: " + (r.stderr or r.stdout).strip()[-300:]
    err = ""
    for i in range(4):
        sh("git", "pull", "--rebase", "-q")
        r = sh("git", "push", "-q")
        if r.returncode == 0:
            return None
        err = (r.stderr or r.stdout).strip()[-300:]
        time.sleep(5 * (i + 1))
    return "push failed: " + err


def log(day, text):
    os.makedirs(os.path.join(ROOT, "data", "_meta"), exist_ok=True)
    p = os.path.join(ROOT, "data", "_meta", f"runs-{day[:7]}.log")
    with open(p, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now(KST).isoformat(timespec='seconds')} {text}\n")
    return p


def main():
    kind, arg = sys.argv[1], sys.argv[2]
    day = sys.argv[3] if len(sys.argv) > 3 else datetime.now(KST).strftime("%Y-%m-%d")
    sh("git", "pull", "--rebase", "-q")
    if kind == "log":
        e = push(f"meta: run log {day} [skip ci]", [log(day, arg)])
        print("OK" if not e or e == "nothing to commit" else "FAIL: " + e)
        return
    path = os.path.join(ROOT, "themes", "days", f"{day}.json")
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError):
        doc = {"date": day}
    if kind == "holiday":
        if doc.get("main") or doc.get("after"):
            print("OK (already has data, not marked holiday)"); return
        doc.update({"date": day, "status": "holiday", "note": arg})
    else:
        with open(arg, encoding="utf-8") as f:
            sec = json.load(f)
        if isinstance(sec, dict) and kind in sec and isinstance(sec[kind], dict):
            sec = sec[kind]   # 문서 전체를 넘긴 경우
        for t in sec.get("themes", []):
            t["stocks"] = sorted(t.get("stocks", []), key=lambda s: -(s["chg"] if isinstance(s.get("chg"), (int, float)) else -1e9))
        doc.update({"date": day, "status": "open"})
        doc.pop("note", None)
        doc[kind] = sec
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import add_nxt
        add_nxt.apply(doc, add_nxt.nxt_map(day))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False)
    lp = log(day, f"{kind} published ({len(doc.get(kind, {}).get('themes', [])) if kind != 'holiday' else 0} themes)")
    e = push(f"themes: {day} {kind}", [path, lp])
    print("OK" if not e or e == "nothing to commit" else "FAIL: " + e)


if __name__ == "__main__":
    main()

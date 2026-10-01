# theme-calendar

한국 주식 테마 달력용 시세 수집기. GitHub Actions가 평일마다 자동 실행합니다 (API 키 불필요).

- 15:45 KST `main`: KRX 정규장 급등 종목 50~90개 → `data/YYYY-MM-DD/main.json`
- 20:10 KST `after`: KRX 종가 대비 NXT 장후 급등 종목 → `data/YYYY-MM-DD/after.json`

데이터 출처: 네이버페이 증권 공개 시세 (개인 참고용). 수동 실행: Actions → collect → Run workflow.

## 공개 달력 (GitHub Pages)
- `index.html` : 달력 페이지. `themes/YYYY-MM.json` 을 읽어 표시합니다.
- `themes/days/YYYY-MM-DD.json` : 하루치 테마 기록 (Claude 예약 작업이 매일 추가)
- `scripts/build_themes.py` : 하루 파일 → 월별 묶음·목록 생성 (build-themes 워크플로가 자동 실행)

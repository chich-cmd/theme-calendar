# theme-calendar

한국 주식 테마 달력용 시세 수집기. GitHub Actions가 평일마다 자동 실행합니다 (API 키 불필요).

- 15:45 KST `main`: KRX 정규장 급등 종목 50~90개 → `data/YYYY-MM-DD/main.json`
- 20:10 KST `after`: KRX 종가 대비 NXT 장후 급등 종목 → `data/YYYY-MM-DD/after.json`

데이터 출처: 네이버페이 증권 공개 시세 (개인 참고용). 수동 실행: Actions → collect → Run workflow.

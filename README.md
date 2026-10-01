# theme-calendar

한국 주식 테마 달력용 시세 수집기 (토스증권 Open API, 개인 투자용).

- `collector/collect.ps1` : 수집 스크립트 (Windows 기본 PowerShell, 설치 불필요)
- `setup.bat` : 처음 한 번 실행 → 키 입력, 연결 테스트, 평일 자동 실행(15:35 / 20:05) 등록
- `data/YYYY-MM-DD/main.json` : 본장 급등 종목
- `data/YYYY-MM-DD/after.json` : 넥장(장후) 급등 종목

키는 `collector/settings.json` 에만 저장되며 GitHub에 올라가지 않습니다.

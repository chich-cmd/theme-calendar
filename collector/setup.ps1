# 테마 달력 수집기 설치 (한 번만 실행)
$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Script = Join-Path $Here "collect.ps1"
$SettingsPath = Join-Path $Here "settings.json"

function Ask([string]$label) {
  while ($true) {
    $v = (Read-Host $label).Trim()
    if ($v) { return $v }
    Write-Host "  값이 비어 있습니다. 다시 붙여넣어 주세요." -ForegroundColor Yellow
  }
}

Write-Host ""
Write-Host "=== 테마 달력 수집기 설치 ===" -ForegroundColor Cyan
Write-Host "키는 이 PC의 collector\settings.json 에만 저장됩니다. (붙여넣기: 마우스 오른쪽 클릭)"
Write-Host ""

$redo = $true
if (Test-Path $SettingsPath) {
  $a = Read-Host "이미 저장된 키가 있습니다. 새로 입력할까요? (y/N)"
  $redo = ($a -eq "y" -or $a -eq "Y")
}
if ($redo) {
  $id     = Ask "1) 토스 Client ID"
  $secret = Ask "2) 토스 Client Secret"
  $gh     = Ask "3) GitHub 토큰 (github_pat_ 로 시작)"
  $obj = [ordered]@{ toss_client_id = $id; toss_client_secret = $secret; github_token = $gh }
  [IO.File]::WriteAllText($SettingsPath, ($obj | ConvertTo-Json), (New-Object Text.UTF8Encoding($false)))
  Write-Host "  저장했습니다." -ForegroundColor Green
}

Write-Host ""
try {
  $ip = (Invoke-WebRequest -UseBasicParsing -Uri "https://api.ipify.org" -TimeoutSec 15).Content.Trim()
  Write-Host "이 PC의 인터넷 IP: $ip" -ForegroundColor Cyan
  Write-Host "토스증권 PC 웹(WTS) > 설정 > Open API 에서 이 IP를 허용 IP로 등록하세요."
} catch {
  Write-Host "IP를 자동으로 확인하지 못했습니다. 브라우저에서 '내 IP'를 검색해 확인 후 토스에 등록하세요." -ForegroundColor Yellow
}
Read-Host "등록을 마쳤으면 Enter"

Write-Host ""
Write-Host "연결 테스트 중..." -ForegroundColor Cyan
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Script test
if ($LASTEXITCODE -ne 0) {
  Write-Host ""
  Write-Host "테스트가 실패했습니다. 위 오류 메시지를 Claude에게 알려주세요 (키 값은 보내지 마세요)." -ForegroundColor Red
  Read-Host "Enter를 누르면 종료합니다"
  exit 1
}

Write-Host ""
Write-Host "자동 실행 예약 중 (평일 15:35 본장, 20:05 넥장)..." -ForegroundColor Cyan
$settings = New-ScheduledTaskSettingsSet -WakeToRun -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 20)
$days = @("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")
foreach ($t in @(@{ name = "ThemeCalendar-Main"; mode = "main"; at = "15:35" }, @{ name = "ThemeCalendar-After"; mode = "after"; at = "20:05" })) {
  $action  = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Script`" $($t.mode)"
  $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $days -At $t.at
  Register-ScheduledTask -TaskName $t.name -Action $action -Trigger $trigger -Settings $settings -Description "테마 달력 시세 수집 ($($t.mode))" -Force | Out-Null
  Write-Host "  등록: $($t.name) 평일 $($t.at)" -ForegroundColor Green
}

Write-Host ""
Write-Host "설치 완료! 평일마다 자동으로 수집해 GitHub에 올립니다." -ForegroundColor Green
Write-Host "실행 기록은 collector\logs 폴더에서 볼 수 있습니다."
Read-Host "Enter를 누르면 종료합니다"

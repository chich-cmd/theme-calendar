# 테마 달력 시세 수집기 (토스증권 Open API) - Windows 기본 PowerShell만 사용, 설치 필요 없음
#   test  : 연결 확인 (토큰 발급 + 상승률 순위 5개 출력)
#   main  : 15:35 본장 마감 - 급등 종목 + 전 종목 종가 스냅샷
#   after : 20:05 넥장 마감 - 본장 종가 대비 장후 급등 종목
# 결과는 GitHub 저장소 data/YYYY-MM-DD/main.json, after.json 으로 올라갑니다.
# 키는 collector\settings.json 에만 저장되며 GitHub에 올라가지 않습니다.
param([string]$Mode = "test")

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Here  = Split-Path -Parent $MyInvocation.MyCommand.Path
$State = Join-Path $Here "state"
$Logs  = Join-Path $Here "logs"
New-Item -ItemType Directory -Force -Path $State, $Logs | Out-Null

$Base = "https://openapi.tossinvest.com"
$Repo = "chich-cmd/theme-calendar"
$Inv  = [Globalization.CultureInfo]::InvariantCulture
$Kst  = [TimeZoneInfo]::FindSystemTimeZoneById("Korea Standard Time")
function KNow { [TimeZoneInfo]::ConvertTime([DateTime]::UtcNow, $Kst) }
$Today = (KNow).ToString("yyyy-MM-dd")

$MainMinRate = 7.0; $MainMinCount = 50; $MainMaxCount = 90
$AfterMinRate = 3.0; $AfterMaxCount = 60

$LogFile = Join-Path $Logs "$Mode.log"
function Log([string]$m) {
  $line = "$((KNow).ToString('yyyy-MM-dd HH:mm:ss')) $m"
  Write-Host $line
  Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

$SettingsPath = Join-Path $Here "settings.json"
if (-not (Test-Path $SettingsPath)) { Log "settings.json 이 없습니다. setup.bat 을 먼저 실행하세요."; exit 1 }
$S = Get-Content $SettingsPath -Raw -Encoding UTF8 | ConvertFrom-Json

function Num($v) {
  $d = 0.0
  if ([double]::TryParse([string]$v, [Globalization.NumberStyles]::Float, $Inv, [ref]$d)) { return $d }
  return 0.0
}

function Invoke-Json([string]$Method, [string]$Url, [hashtable]$Headers = @{}, $Body = $null, [string]$ContentType = $null) {
  for ($i = 0; $i -lt 3; $i++) {
    try {
      $p = @{ Method = $Method; Uri = $Url; Headers = $Headers; UseBasicParsing = $true; TimeoutSec = 60 }
      if ($null -ne $Body) { $p.Body = $Body }
      if ($ContentType) { $p.ContentType = $ContentType }
      $r = Invoke-WebRequest @p
      $ms = $r.RawContentStream; $ms.Position = 0
      $text = (New-Object IO.StreamReader($ms, [Text.Encoding]::UTF8)).ReadToEnd()
      if (-not $text) { return $null }
      return ($text | ConvertFrom-Json)
    } catch {
      $code = $null; $msg = $_.Exception.Message
      if ($_.Exception.Response) {
        $code = [int]$_.Exception.Response.StatusCode
        try { $msg = (New-Object IO.StreamReader($_.Exception.Response.GetResponseStream())).ReadToEnd() } catch {}
      }
      if ($code -eq 429 -and $i -lt 2) { Start-Sleep -Milliseconds (1500 * ($i + 1)); continue }
      if ($null -eq $code -and $i -lt 2) { Start-Sleep -Seconds 2; continue }
      throw "HTTP $code $Url : $msg"
    }
  }
}

# ---------- 토스 토큰 (클라이언트당 1개만 유효 → 파일에 저장해 재사용) ----------
function Get-Token([switch]$Force) {
  $tp = Join-Path $State "token.json"
  $nowSec = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
  if (-not $Force -and (Test-Path $tp)) {
    $t = Get-Content $tp -Raw | ConvertFrom-Json
    if (($t.expires_at - $nowSec) -gt 600) { return $t.access_token }
  }
  $body = "grant_type=client_credentials&client_id=" + [uri]::EscapeDataString($S.toss_client_id) +
          "&client_secret=" + [uri]::EscapeDataString($S.toss_client_secret)
  $r = Invoke-Json "POST" "$Base/oauth2/token" @{} $body "application/x-www-form-urlencoded"
  @{ access_token = $r.access_token; expires_at = $nowSec + [int]$r.expires_in } | ConvertTo-Json | Set-Content $tp -Encoding UTF8
  return $r.access_token
}

$script:Token = $null
function Toss([string]$Path, [hashtable]$Query) {
  if (-not $script:Token) { $script:Token = Get-Token }
  $qs = ($Query.GetEnumerator() | ForEach-Object { "$($_.Key)=$([uri]::EscapeDataString([string]$_.Value))" }) -join "&"
  $url = "$Base$($Path)?$qs"
  try {
    $r = Invoke-Json "GET" $url @{ Authorization = "Bearer $($script:Token)" }
  } catch {
    $e = "$_"
    if ($e -match "HTTP 401") {
      $script:Token = Get-Token -Force
      $r = Invoke-Json "GET" $url @{ Authorization = "Bearer $($script:Token)" }
    } elseif ($e -match "HTTP 403") {
      Log "403 거부: 토스 WTS 설정에 이 PC의 IP가 등록되어 있는지 확인하세요."
      throw
    } else { throw }
  }
  if ($r.PSObject.Properties.Name -contains "result") { return ,@($r.result) }
  return ,@($r)
}

# ---------- 데이터 ----------
function Get-Master {
  # KOSPI·KOSDAQ '주식'만 (ETF·ETN·리츠·스팩 제외). 하루 한 번 받아 저장.
  $mp = Join-Path $State "master-$Today.json"
  $h = @{}
  if (Test-Path $mp) {
    (Get-Content $mp -Raw -Encoding UTF8 | ConvertFrom-Json).PSObject.Properties | ForEach-Object { $h[$_.Name] = $_.Value }
    return $h
  }
  foreach ($m in @("KOSPI", "KOSDAQ")) {
    foreach ($s in (Toss "/api/v1/stocks/all" @{ market = $m; securityType = "STOCK" })) {
      if ([string]$s.name -like "*스팩*") { continue }
      $h[[string]$s.symbol] = [pscustomobject]@{ name = $s.name; market = $m }
    }
    Start-Sleep -Milliseconds 300
  }
  $h | ConvertTo-Json -Depth 3 -Compress | Set-Content $mp -Encoding UTF8
  return $h
}

function Get-Prices($Syms) {
  $out = @{}
  for ($i = 0; $i -lt $Syms.Count; $i += 200) {
    $chunk = $Syms[$i..([Math]::Min($i + 199, $Syms.Count - 1))]
    foreach ($p in (Toss "/api/v1/prices" @{ symbols = ($chunk -join ",") })) {
      $v = Num $p.lastPrice
      if ($v -gt 0) { $out[[string]$p.symbol] = $v }
    }
    Start-Sleep -Milliseconds 250
  }
  return $out
}

function Save-Result([string]$Kind, $Obj) {
  $Obj | Add-Member -NotePropertyName generatedAt -NotePropertyValue ((KNow).ToString("yyyy-MM-ddTHH:mm:ss") + "+09:00") -Force
  $json = $Obj | ConvertTo-Json -Depth 8
  $dir = Join-Path $Here "out\$Today"
  New-Item -ItemType Directory -Force -Path $dir | Out-Null
  [IO.File]::WriteAllText((Join-Path $dir "$Kind.json"), $json, (New-Object Text.UTF8Encoding($false)))
  Put-GitHub "data/$Today/$Kind.json" $json "data: $Today $Kind"
}

function Put-GitHub([string]$RepoPath, [string]$Json, [string]$Msg) {
  $h = @{ Authorization = "Bearer $($S.github_token)"; Accept = "application/vnd.github+json"; "User-Agent" = "theme-calendar-collector" }
  $url = "https://api.github.com/repos/$Repo/contents/$RepoPath"
  $sha = $null
  try { $sha = (Invoke-Json "GET" $url $h).sha } catch { if ("$_" -notmatch "HTTP 404") { throw } }
  $body = @{ message = $Msg; content = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($Json)) }
  if ($sha) { $body.sha = $sha }
  Invoke-Json "PUT" $url $h ($body | ConvertTo-Json) "application/json" | Out-Null
  Log "GitHub 업로드 완료: $RepoPath"
}

function Get-Rankings([int]$Count) {
  $rows = Toss "/api/v1/rankings" @{ country = "KR"; rankingType = "PRICE_INCREASE_RATE"; period = "1d"; count = $Count }
  # 등락률이 0.2998 같은 소수로 오면 % 로 변환
  $top = 0.0; foreach ($r in $rows) { $v = [Math]::Abs((Num $r.priceChangeRate)); if ($v -gt $top) { $top = $v } }
  $scale = if ($top -gt 0 -and $top -lt 1.5) { 100.0 } else { 1.0 }
  return @{ rows = $rows; scale = $scale }
}

# ---------- 본장 ----------
function Run-Main {
  $cal = $null
  try { $cal = Toss "/api/v1/market-calendar/KR" @{ date = $Today } } catch { Log "장 운영 정보 조회 실패(무시): $_" }
  if ($cal) { Put-GitHub "data/_meta/market-calendar-$Today.json" ($cal | ConvertTo-Json -Depth 8) "meta: market calendar $Today" }

  $master = Get-Master
  $rk = Get-Rankings 200
  $picked = New-Object System.Collections.ArrayList
  foreach ($r in $rk.rows) {
    $sym = [string]$r.symbol
    if (-not $master.ContainsKey($sym)) { continue }
    [void]$picked.Add([pscustomobject]@{
      symbol = $sym; name = $master[$sym].name; market = $master[$sym].market
      chg = [Math]::Round((Num $r.priceChangeRate) * $rk.scale, 2)
      price = (Num $r.lastPrice)
      amount_eok = [Math]::Round((Num $r.tradingAmount) / 1e8)
    })
  }
  if ($picked.Count -eq 0) { Log "상승률 순위가 비어 있습니다(휴장일 가능성)."; Save-Result "main" ([pscustomobject]@{ date = $Today; status = "empty"; stocks = @() }); return }
  $strong = @($picked | Where-Object { $_.chg -ge $MainMinRate })
  $stocks = if ($strong.Count -ge $MainMinCount) { $strong } else { @($picked | Select-Object -First $MainMinCount) }
  $stocks = @($stocks | Select-Object -First $MainMaxCount)

  # 넥장 비교용 전 종목 종가 스냅샷 (15:39 이전에만 - 넥장 애프터마켓은 15:40 시작)
  $k = KNow
  if ($k.Hour -lt 15 -or ($k.Hour -eq 15 -and $k.Minute -lt 40)) {
    $snap = Get-Prices @($master.Keys | Sort-Object)
    $snap | ConvertTo-Json -Compress | Set-Content (Join-Path $State "close-$Today.json") -Encoding UTF8
    Log "종가 스냅샷 $($snap.Count)종목 저장"
  } else { Log "15:40 이후 실행이라 종가 스냅샷은 건너뜁니다(오늘 넥장 비교 불가)." }

  Log "본장 급등 $($stocks.Count)종목 (7% 이상 $($strong.Count)개)"
  Save-Result "main" ([pscustomobject]@{
    date = $Today; status = "open"; source = "toss-openapi"
    rule = "등락률 $MainMinRate% 이상(부족하면 상위 $MainMinCount개), ETF·ETN·스팩 제외"
    stocks = $stocks
  })
}

# ---------- 넥장 ----------
function Run-After {
  $cp = Join-Path $State "close-$Today.json"
  if (-not (Test-Path $cp)) {
    Log "오늘 15:35 종가 스냅샷이 없어 넥장 비교를 할 수 없습니다."
    Save-Result "after" ([pscustomobject]@{ date = $Today; status = "no-close-snapshot"; stocks = @() }); return
  }
  $close = @{}
  (Get-Content $cp -Raw | ConvertFrom-Json).PSObject.Properties | ForEach-Object { $close[$_.Name] = [double]$_.Value }
  $master = Get-Master
  $syms = @($master.Keys | Where-Object { $close.ContainsKey($_) } | Sort-Object)
  $last = Get-Prices $syms
  $moved = New-Object System.Collections.ArrayList
  foreach ($s in $syms) {
    $c = $close[$s]; $l = $last[$s]
    if (-not $c -or -not $l -or $l -eq $c) { continue }
    [void]$moved.Add([pscustomobject]@{
      symbol = $s; name = $master[$s].name; market = $master[$s].market
      close = $c; last = $l; after_chg = [Math]::Round(($l / $c - 1) * 100, 2)
    })
  }
  $up   = @($moved | Where-Object { $_.after_chg -ge $AfterMinRate } | Sort-Object after_chg -Descending | Select-Object -First $AfterMaxCount)
  $down = @($moved | Where-Object { $_.after_chg -le -$AfterMinRate } | Sort-Object after_chg | Select-Object -First 15)
  Log "장후 가격 변동 $($moved.Count)종목, $AfterMinRate% 이상 상승 $($up.Count)개"
  Save-Result "after" ([pscustomobject]@{
    date = $Today; status = "open"; source = "toss-openapi"
    rule = "본장 종가(15:35 스냅샷) 대비 $AfterMinRate% 이상, 20:05 기준"
    moved_count = $moved.Count; stocks = $up; down = $down
  })
}

try {
  switch ($Mode) {
    "test" {
      $script:Token = Get-Token
      Log "토스 토큰 발급 성공"
      $rk = Get-Rankings 5
      foreach ($r in $rk.rows) { Write-Host ("   {0}. {1} ({2})  {3}%" -f $r.rank, $r.name, $r.symbol, [Math]::Round((Num $r.priceChangeRate) * $rk.scale, 2)) }
      $h = @{ Authorization = "Bearer $($S.github_token)"; Accept = "application/vnd.github+json"; "User-Agent" = "theme-calendar-collector" }
      $null = Invoke-Json "GET" "https://api.github.com/repos/$Repo" $h
      Log "GitHub 연결 성공"
      Log "테스트 완료. 위에 종목 5개가 보이면 정상입니다."
    }
    "main"  { Run-Main }
    "after" { Run-After }
    default { Log "사용법: collect.ps1 test | main | after"; exit 1 }
  }
} catch {
  Log "오류: $_"
  exit 1
}

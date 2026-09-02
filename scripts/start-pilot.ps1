# BidProof 公网试点：本机 FastAPI + Cloudflare Tunnel
# 用法：在项目根目录 .\scripts\start-pilot.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Port = 8016
$TrialCode = if ($env:BIDPROOF_TRIAL_JOIN_CODE) { $env:BIDPROOF_TRIAL_JOIN_CODE } else { "BidProof-Trial-2026" }
$env:BIDPROOF_TRIAL_JOIN_CODE = $TrialCode

$Uvicorn = Join-Path $Root ".venv\Scripts\uvicorn.exe"
if (-not (Test-Path $Uvicorn)) {
  Write-Error "未找到 .venv。请先运行: uv sync"
}

$Cf = Get-Command cloudflared -ErrorAction SilentlyContinue
if (-not $Cf) {
  $CfPath = "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\Cloudflare.cloudflared_Microsoft.Winget.Source_8wekyb3d8bbwe\cloudflared.exe"
  if (-not (Test-Path $CfPath)) { Write-Error "未找到 cloudflared，请先安装 Cloudflare Tunnel CLI" }
  $Cf = $CfPath
} else {
  $Cf = $Cf.Source
}

New-Item -ItemType Directory -Force -Path (Join-Path $Root "work") | Out-Null

# 停旧进程
Get-CimInstance Win32_Process -Filter "Name='uvicorn.exe'" -ErrorAction SilentlyContinue |
  Where-Object { $_.CommandLine -match "--port $Port" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Get-CimInstance Win32_Process -Filter "Name='cloudflared.exe'" -ErrorAction SilentlyContinue |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

$UvOut = Join-Path $Root "work\bidproof-uvicorn-live.log"
$UvErr = Join-Path $Root "work\bidproof-uvicorn-live.err.log"
$uv = Start-Process -FilePath $Uvicorn `
  -ArgumentList "app.main:app","--host","127.0.0.1","--port",$Port,"--proxy-headers" `
  -WorkingDirectory $Root -PassThru -WindowStyle Hidden `
  -RedirectStandardOutput $UvOut -RedirectStandardError $UvErr
Write-Host "uvicorn started pid $($uv.Id) -> http://127.0.0.1:$Port"

Start-Sleep -Seconds 3
$health = curl.exe -s -m 5 "http://127.0.0.1:$Port/healthz"
if ($health -notmatch '"status":"ok"') { Write-Error "本机 healthz 失败: $health" }
Write-Host "local healthz ok"

# cloudflared may write version warnings to stderr; with $ErrorActionPreference=Stop that
# would abort before the JWT is captured. Pull stdout via a file instead.
$tokenOut = Join-Path $env:TEMP "bidproof-tunnel-token.out"
$tokenErr = Join-Path $env:TEMP "bidproof-tunnel-token.err"
$tokenProc = Start-Process -FilePath $Cf -ArgumentList "tunnel","token","bidproof-local" `
  -NoNewWindow -Wait -PassThru -RedirectStandardOutput $tokenOut -RedirectStandardError $tokenErr
$token = ((Get-Content $tokenOut -Raw -ErrorAction SilentlyContinue) -split "\s+" | Where-Object { $_ } | Select-Object -Last 1)
Remove-Item $tokenOut, $tokenErr -Force -ErrorAction SilentlyContinue
if (-not $token -or $tokenProc.ExitCode -ne 0) { Write-Error "无法获取 bidproof-local tunnel token，请运行 cloudflared tunnel login" }

$CfLog = Join-Path $Root "work\bidproof-tunnel-live.log"
$CfErr = Join-Path $Root "work\bidproof-tunnel-live.err.log"
$tunnel = Start-Process -FilePath $Cf `
  -ArgumentList "tunnel","--no-autoupdate","--logfile",$CfLog,"run","--token",$token `
  -WorkingDirectory $Root -PassThru -WindowStyle Hidden -RedirectStandardError $CfErr
Write-Host "cloudflared started pid $($tunnel.Id)"

Start-Sleep -Seconds 8
$pub = curl.exe -s -m 20 "https://bidproof.marketcase.net/healthz"
Write-Host "public healthz: $pub"
Write-Host "试用加入码: $TrialCode"
Write-Host "工作台: https://bidproof.marketcase.net/app"

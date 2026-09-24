# Local auth smoke harness: loopback SMTP sink + the real app on 127.0.0.1:8772.
#
# Verifies the email one-time-code journey (landing -> /app -> OTP -> workspace) without any
# external provider. Runtime state stays in %TEMP%; nothing is written into the repository.
# The recipient address is synthetic and delivery stops at 127.0.0.1.
#
#   powershell -File scripts\start-smoke.ps1
#
# Then drive a browser against http://127.0.0.1:8772/ and read the code from the printed path.
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = (Resolve-Path (Join-Path $here '..')).Path
$state = Join-Path $env:TEMP 'bidproof-smoke'
New-Item -ItemType Directory -Force -Path $state | Out-Null
$otpPath = Join-Path $state 'otp.txt'
Remove-Item -LiteralPath $otpPath -Force -ErrorAction SilentlyContinue

$env:BIDPROOF_ENV = 'development'
$env:BIDPROOF_DATA_ROOT = $state
$env:BIDPROOF_DATABASE_URL = 'sqlite+pysqlite:///' + (($state + '\smoke.sqlite3') -replace '\\', '/')
$env:BIDPROOF_ALLOW_TRUSTED_HEADERS = '0'
$env:BIDPROOF_SMOKE_OTP_PATH = $otpPath
# Local-only secret and loopback transport; never reuse these values for a real deployment.
$env:BIDPROOF_OTP_SECRET = 'local-smoke-only-secret-not-for-production-0123456789'
$env:BIDPROOF_EMAIL_PROVIDER = 'smtp'
$env:BIDPROOF_SMTP_HOST = '127.0.0.1'
$env:BIDPROOF_SMTP_PORT = '2525'
$env:BIDPROOF_SMTP_SECURITY = 'plain'
$env:BIDPROOF_SMTP_FROM = 'login@example.test'
$env:BIDPROOF_SMTP_USERNAME = ''
$env:BIDPROOF_PERSONAL_SIGNUP = '1'

Set-Location $root
uv run python -m app.dbctl upgrade

$sink = Start-Process -FilePath 'uv' -ArgumentList @('run', 'python', 'scripts\smoke_smtp_sink.py', '2525') `
  -WorkingDirectory $root -WindowStyle Hidden -PassThru `
  -RedirectStandardOutput (Join-Path $state 'sink.log') -RedirectStandardError (Join-Path $state 'sink.err')
$web = Start-Process -FilePath 'uv' -ArgumentList @('run', 'python', '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8772') `
  -WorkingDirectory $root -WindowStyle Hidden -PassThru `
  -RedirectStandardOutput (Join-Path $state 'web.log') -RedirectStandardError (Join-Path $state 'web.err')

Write-Output ("sink pid=" + $sink.Id + "  web pid=" + $web.Id)
Write-Output ("data root: " + $state)
Write-Output ("otp file:  " + $otpPath)

$deadline = (Get-Date).AddSeconds(45)
do {
  Start-Sleep -Milliseconds 1500
  try { $probe = Invoke-WebRequest -Uri 'http://127.0.0.1:8772/healthz' -UseBasicParsing -TimeoutSec 3; $ok = $probe.StatusCode } catch { $ok = $null }
} while (-not $ok -and (Get-Date) -lt $deadline)
Write-Output ("healthz=" + $ok + "   landing: http://127.0.0.1:8772/   workbench: http://127.0.0.1:8772/app")


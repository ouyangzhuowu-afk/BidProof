# Local CI mirror for Windows / Cursor Cloud Agent
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

$env:BIDPROOF_ENV = "test"
$env:BIDPROOF_ALLOW_TRUSTED_HEADERS = "1"

Write-Host "==> workflow check"
uv run python -m app.workflow check

if (Get-Command node -ErrorAction SilentlyContinue) {
  Write-Host "==> javascript syntax"
  node --check static/app.js
}

Write-Host "==> pytest"
uv run --group dev pytest -q

Write-Host "CI local: PASS"

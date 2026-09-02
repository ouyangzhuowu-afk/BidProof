# Sync gitignored real-upload PDFs from a full local checkout into work/uploads/.
# Usage: .\scripts\sync-real-upload-fixtures.ps1 [-Source "C:\path\to\full\checkout"]

param(
  [string]$Source = "C:\Users\35938\Documents\Codex\2026-06-11\workspace-sop-project-agent-md-sop\project-025-bid-evidence-agent"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$Target = Join-Path $Root "work\uploads"
$SourceUploads = Join-Path $Source "work\uploads"

if (-not (Test-Path $SourceUploads)) {
  Write-Error "Source uploads not found: $SourceUploads"
}

New-Item -ItemType Directory -Force -Path $Target | Out-Null
$files = Get-ChildItem -Path $SourceUploads -File
if ($files.Count -eq 0) {
  Write-Error "No files in $SourceUploads"
}

foreach ($file in $files) {
  Copy-Item -Path $file.FullName -Destination (Join-Path $Target $file.Name) -Force
}

Write-Host "Synced $($files.Count) PDF(s) to $Target"
Write-Host "Run: uv run --group dev pytest -q tests/test_real_fixture_manifest.py tests/test_ground_truth_workflow.py"

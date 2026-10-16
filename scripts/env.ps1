$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$python = Join-Path $root ".venv\Scripts\python.exe"

Write-Host "Workspace: $root"
Write-Host ""

Write-Host "Python:"
& $python --version
& $python -m pip --version
& $python -m django --version

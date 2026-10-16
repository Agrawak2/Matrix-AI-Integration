$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$python = Join-Path $root ".venv\Scripts\python.exe"

Write-Host "Running Python unit tests..."
& $python -m unittest discover -s tests -v

Write-Host ""
Write-Host "Running Django checks and gateway tests..."
& $python manage.py check
& $python manage.py test gateway -v 2

Write-Host ""
Write-Host "All checks passed."

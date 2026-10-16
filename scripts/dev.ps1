$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$python = Join-Path $root ".venv\Scripts\python.exe"
$port = if ($args.Count -gt 0) { $args[0] } else { "8000" }

if (-not (Test-Path $python)) {
    throw "Python executable not found at $python"
}

Write-Host "Applying Django migrations..."
& $python manage.py migrate --noinput

Write-Host ""
Write-Host "Starting Django dev server..."
Write-Host "URL: http://127.0.0.1:$port"
Write-Host "Press Ctrl+C to stop."

& $python manage.py runserver "127.0.0.1:$port"

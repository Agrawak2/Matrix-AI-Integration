param(
    [string] $Query = "PCB",
    [string] $Username = "engineer"
)

$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$python = Join-Path $root ".venv\Scripts\python.exe"

& $python (Join-Path $root "scripts\matrix_rest_smoke.py") --query $Query --username $Username
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

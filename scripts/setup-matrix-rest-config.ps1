param(
    [string] $PassportUrl,
    [string] $SpaceUrl,
    [string] $Identifier,
    [string] $ServiceName,
    [string] $ServiceSecret,
    [string] $SecurityContext = "",
    [string] $ProfileName = "matrix-qa",
    [switch] $SkipCatalogUpdate
)

$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$configDir = Join-Path $root "config"
$ticketNote = Join-Path $root "REST API Info\RestAPI_TransientToken_Ticket.txt"
$python = Join-Path $root ".venv\Scripts\python.exe"

function First-Match([string] $Text, [string] $Pattern) {
    $match = [regex]::Match($Text, $Pattern, [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
    if ($match.Success) {
        return $match.Groups[1].Value.Trim()
    }
    return ""
}

if (Test-Path $ticketNote) {
    $note = Get-Content $ticketNote -Raw
    if (-not $PassportUrl) {
        $PassportUrl = First-Match $note "(https://[^\s`"']+/3dpassport)"
    }
    if (-not $SpaceUrl) {
        $SpaceUrl = First-Match $note "(https://[^\s`"']+/3dspace)"
    }
    if (-not $Identifier) {
        $Identifier = First-Match $note "[?&]identifier=([A-Za-z0-9_.-]+)"
    }
    if (-not $ServiceName) {
        $ServiceName = First-Match $note "DS-SERVICE-NAME\s*=\s*([^\s]+)"
    }
    if (-not $ServiceSecret) {
        $ServiceSecret = First-Match $note "DS-SERVICE-SECRET\s*=\s*([^\s]+)"
    }
}

$missing = @()
if (-not $PassportUrl) { $missing += "PassportUrl" }
if (-not $SpaceUrl) { $missing += "SpaceUrl" }
if (-not $Identifier) { $missing += "Identifier" }
if (-not $ServiceName) { $missing += "ServiceName" }
if (-not $ServiceSecret) { $missing += "ServiceSecret" }
if ($missing.Count -gt 0) {
    throw "Missing Matrix config values: $($missing -join ', '). Pass them as parameters or update REST API Info\RestAPI_TransientToken_Ticket.txt."
}

New-Item -ItemType Directory -Force -Path $configDir | Out-Null

$profileConfig = [ordered]@{
    active_profile = $ProfileName
    profiles = @(
        [ordered]@{
            name = $ProfileName
            passport_url = $PassportUrl.TrimEnd("/")
            space_url = $SpaceUrl.TrimEnd("/")
            identifier = $Identifier
            service_name = $ServiceName
            service_secret = $ServiceSecret
            security_context = $SecurityContext
        }
    )
}

$templateConfig = [ordered]@{
    templates = [ordered]@{
        get_part = 'print bus Part "{part_number}" * select current owner description dump |'
        search_parts = 'temp query bus Part "{query_pattern}" * select current owner description dump |'
        duplicate_parts = 'temp query bus Part "{query_pattern}" * select current owner description dump |'
        open_ecos_for_parts = 'temp query bus ECO * * where "current != ''Released''" select current owner description dump |'
        where_used = 'print bus Part "{part_numbers}" * select from[EBOM].to.name from[EBOM].to.current dump |'
    }
}

$profilePath = Join-Path $configDir "matrix_profiles.local.json"
$templatePath = Join-Path $configDir "matrix_mql_templates.local.json"

$profileConfig | ConvertTo-Json -Depth 10 | Set-Content -Path $profilePath -Encoding UTF8
$templateConfig | ConvertTo-Json -Depth 10 | Set-Content -Path $templatePath -Encoding UTF8

Write-Host "Wrote Matrix profile config: $profilePath"
Write-Host "Wrote Matrix MQL template config: $templatePath"
Write-Host "Profile: $ProfileName"
Write-Host "3DPassport: $($PassportUrl.TrimEnd('/'))"
Write-Host "3DSpace: $($SpaceUrl.TrimEnd('/'))"
Write-Host "Identifier: $Identifier"
Write-Host "Service name: $ServiceName"
Write-Host "Service secret: configured (hidden)"

if (-not $SkipCatalogUpdate) {
    Write-Host ""
    Write-Host "Preparing local API catalog for executeMQL..."
    & $python (Join-Path $root "scripts\matrix_rest_prepare.py")
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

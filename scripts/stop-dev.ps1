$ErrorActionPreference = "Stop"

$port = if ($args.Count -gt 0) { $args[0] } else { "8000" }
$matches = netstat.exe -ano | Select-String -Pattern "127\.0\.0\.1:$port\s+.*LISTENING\s+(\d+)"

if (-not $matches) {
    Write-Host "No Django server is listening on 127.0.0.1:$port."
    exit 0
}

$processIds = $matches | ForEach-Object {
    ($_ -split "\s+")[-1]
} | Sort-Object -Unique

foreach ($processId in $processIds) {
    Write-Host "Stopping Django process $processId on port $port..."
    Stop-Process -Id ([int] $processId)
}

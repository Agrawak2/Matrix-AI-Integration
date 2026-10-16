param(
    [string] $Query = "PCB",
    [string] $Url = "http://127.0.0.1:8000/api/",
    [string] $Username = "engineer",
    [switch] $UseMatrixServer
)

$ErrorActionPreference = "Stop"

$apiUri = [Uri] $Url
$rootBuilder = [System.UriBuilder]::new($apiUri)
$rootBuilder.Path = $apiUri.AbsolutePath -replace "/api/?$", "/"
$rootBuilder.Query = ""
$rootUrl = $rootBuilder.Uri.AbsoluteUri

Write-Host "Loading $rootUrl to collect CSRF token..."
$homeResponse = Invoke-WebRequest -Uri $rootUrl -SessionVariable apiSession -UseBasicParsing
$csrfToken = (
    $apiSession.Cookies.GetCookies($rootBuilder.Uri) |
        Where-Object { $_.Name -eq "csrftoken" } |
        Select-Object -First 1
).Value

if (-not $csrfToken -and $homeResponse.Content -match '<meta name="csrf-token" content="([^"]+)">') {
    $csrfToken = $Matches[1]
}

if (-not $csrfToken) {
    throw "Could not find a Django CSRF token at $rootUrl."
}

$headers = @{
    "X-CSRFToken" = $csrfToken
}

Write-Host "Logging in to $Url as '$Username'..."
$loginPayload = @{
    action = "auth.login"
    payload = @{
        username = $Username
    }
} | ConvertTo-Json -Depth 10 -Compress

$login = Invoke-RestMethod `
    -Uri $Url `
    -Method Post `
    -ContentType "application/json" `
    -Body $loginPayload `
    -WebSession $apiSession `
    -Headers $headers

if (-not $login.ok) {
    throw "Login failed: $($login.errors -join '; ')"
}

Write-Host "Searching for parts matching '$Query'..."
$searchPayload = @{
    action = "matrix.part.search"
    payload = @{
        part_number = $Query
        use_matrix_server = [bool] $UseMatrixServer
    }
} | ConvertTo-Json -Depth 10 -Compress

$search = Invoke-RestMethod `
    -Uri $Url `
    -Method Post `
    -ContentType "application/json" `
    -Body $searchPayload `
    -WebSession $apiSession `
    -Headers $headers

if (-not $search.ok) {
    throw "Part search failed: $($search.errors -join '; ')"
}

Write-Host ""
Write-Host "Found $($search.data.count) $($search.data.source) match(es) for '$($search.data.query)':"
$search.data.matches |
    Select-Object part_number, name, revision, lifecycle_state, classification |
    Format-Table -AutoSize

Write-Host "Matches JSON:"
$search.data.matches | ConvertTo-Json -Depth 10

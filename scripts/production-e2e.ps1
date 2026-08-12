param([string]$BaseUrl = "https://api.alterai.ru")
$ErrorActionPreference = "Stop"
$token = if ($env:AUTH_TOKEN) { $env:AUTH_TOKEN.Trim() } else { "" }
function Get-Status($path, $headers = @{}) {
  try { (Invoke-WebRequest -UseBasicParsing -Uri "$BaseUrl$path" -Headers $headers -TimeoutSec 20).StatusCode }
  catch { if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { throw } }
}
if ((Get-Status "/health") -ne 200 -or (Get-Status "/ready") -ne 200) { throw "public health failed" }
$headers = @{}
if ($token) { $headers.Authorization = "Bearer $token" }
if (-not $token) { Write-Host "public production checks passed; authenticated checks skipped"; exit 0 }
foreach ($path in @("/api/v1/auth/me", "/api/v1/scenarios", "/api/v1/workflow", "/api/v1/action-log")) {
  if ((Get-Status $path $headers) -ne 200) { throw "authenticated check failed: $path" }
}
$body = '{"message":"test"}'
$streamHeaders = @{ Authorization = "Bearer $token"; Accept = "text/event-stream" }
$response = Invoke-WebRequest -UseBasicParsing -Uri "$BaseUrl/api/v1/chat/stream" -Method Post -Headers $streamHeaders -ContentType "application/json" -Body ([Text.Encoding]::UTF8.GetBytes($body)) -TimeoutSec 60
if ($response.StatusCode -ne 200 -or $response.Content -notmatch "done") { throw "stream check failed" }
Write-Host "authenticated production checks passed"

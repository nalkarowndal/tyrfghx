# M3-34 negative-security proof: production release must not expose WebDriver,
# even if automation-like environment variables are supplied.
# Only checks a disposable GitHub runner build; no model/GPU/UI clicks or uploads.
param([Parameter(Mandatory = $true)][string]$Application)
$ErrorActionPreference = "Stop"
$expected = [System.IO.Path]::GetFullPath((Join-Path (Get-Location).Path "src-tauri/target/release/aiimage.exe"))
$given = [System.IO.Path]::GetFullPath($Application)
if ($given -ine $expected) { throw "production_webdriver_absence: unapproved_executable" }
if (-not (Test-Path -LiteralPath $given -PathType Leaf)) { throw "production_webdriver_absence: binary_missing" }

# The TCP port is allocated on loopback, released, then probed; in rare cases
# another process could claim it in between, which is a safe test failure.
$listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
$listener.Start()
$port = ([System.Net.IPEndPoint]$listener.LocalEndpoint).Port
$listener.Stop()
$previousEnable = $env:AIIMAGE_E2E_ENABLE
$previousPort = $env:TAURI_WEBDRIVER_PORT
$process = $null
try {
  $env:AIIMAGE_E2E_ENABLE = "1"
  $env:TAURI_WEBDRIVER_PORT = [string]$port
  $process = Start-Process -FilePath $given -WorkingDirectory (Split-Path $given) -PassThru
  $tested = 0
  for ($i = 0; $i -lt 24; $i++) {
    Start-Sleep -Milliseconds 250
    $process.Refresh()
    if ($process.HasExited) { throw "production_webdriver_absence: application_exited" }
    $client = [System.Net.Sockets.TcpClient]::new()
    $connected = $false
    try {
      $attempt = $client.ConnectAsync("127.0.0.1", $port)
      try { $connected = $attempt.Wait(300) -and $client.Connected }
      catch { $connected = $false }
    } finally { $client.Dispose() }
    if ($connected) { throw "production_webdriver_absence: unexpected_listener" }
    $tested++
  }
  if ($tested -ne 24) { throw "production_webdriver_absence: incomplete_probe" }
  Write-Output "production_webdriver_absence: verified_no_listener"
} finally {
  $env:AIIMAGE_E2E_ENABLE = $previousEnable
  $env:TAURI_WEBDRIVER_PORT = $previousPort
  if ($null -ne $process) {
    try {
      $process.Refresh()
      if (-not $process.HasExited) {
        & taskkill.exe /PID $process.Id /T /F > $null 2>&1
      }
    } catch { Write-Output "production_webdriver_absence: cleanup_unconfirmed" }
  }
}

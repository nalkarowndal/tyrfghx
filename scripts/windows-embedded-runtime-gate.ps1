# M3-35: real Windows negative tests of the *feature-gated* E2E binary.
# In absence of complete operator opt-in, no WebDriver HTTP listener may start.
# Never opens model dialogs, touches weights, invokes GPU or captures images.
param(
  [Parameter(Mandatory = $true)][string]$Application,
  [switch]$ValidateOnly
)
$ErrorActionPreference = "Stop"
$expected = [System.IO.Path]::GetFullPath((Join-Path (Get-Location).Path "src-tauri/target/release/aiimage.exe"))
$requested = [System.IO.Path]::GetFullPath($Application)
if ($requested -ine $expected) { throw "embedded_runtime_gate: unapproved_executable" }
if ($ValidateOnly) { Write-Output "embedded_runtime_gate: expected_path_valid"; return }
if (-not (Test-Path -LiteralPath $requested -PathType Leaf)) { throw "embedded_runtime_gate: binary_missing" }

function New-IsolatedPort {
  $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
  try {
    $listener.Start()
    return ([System.Net.IPEndPoint]$listener.LocalEndpoint).Port
  } finally {
    $listener.Stop()
  }
}

function Test-Listener([int]$Port) {
  $client = [System.Net.Sockets.TcpClient]::new()
  try {
    $attempt = $client.ConnectAsync("127.0.0.1", $Port)
    try { return ($attempt.Wait(250) -and $client.Connected) }
    catch { return $false }
  } finally {
    $client.Dispose()
  }
}

function Assert-Disabled([string]$CaseName, [AllowNull()][string]$Enable,
                         [AllowNull()][string]$PortValue, [int]$ProbePort) {
  $env:AIIMAGE_E2E_ENABLE = $Enable
  $env:TAURI_WEBDRIVER_PORT = $PortValue
  $started = $null
  try {
    # No shell interpolation and exactly one owned process tree.
    $started = Start-Process -FilePath $requested -WorkingDirectory (Split-Path $requested) -PassThru
    for ($i = 0; $i -lt 16; $i++) {
      Start-Sleep -Milliseconds 250
      $started.Refresh()
      if ($started.HasExited) { throw "embedded_runtime_gate: application_exited" }
      if (Test-Listener $ProbePort) { throw "embedded_runtime_gate: unexpected_listener" }
    }
    Write-Output "embedded_runtime_gate: ${CaseName}_disabled"
  } finally {
    if ($null -ne $started) {
      try {
        $started.Refresh()
        if (-not $started.HasExited) {
          & taskkill.exe /PID $started.Id /T /F > $null 2>&1
        }
      } catch { Write-Output "embedded_runtime_gate: cleanup_unconfirmed" }
    }
  }
}

$priorEnable = $env:AIIMAGE_E2E_ENABLE
$priorPort = $env:TAURI_WEBDRIVER_PORT
try {
  # Check the plugin default port is free before running the missing-port cases.
  # Another process on it means no trustworthy verdict can be produced.
  if (Test-Listener 4445) { throw "embedded_runtime_gate: default_port_occupied" }
  $isolatedPort = New-IsolatedPort
  if ($isolatedPort -eq 4445) { $isolatedPort = New-IsolatedPort }
  if ($isolatedPort -eq 4445) { throw "embedded_runtime_gate: port_collision" }

  # The plugin default (4445) is checked for absent/invalid port settings.
  Assert-Disabled "neither_flag" $null $null 4445
  Assert-Disabled "enable_without_port" "1" $null 4445
  Assert-Disabled "invalid_port" "1" "not-a-port" 4445
  # The isolated port is checked with a valid port but no enable approval.
  Assert-Disabled "port_without_enable" $null ([string]$isolatedPort) $isolatedPort
} finally {
  $env:AIIMAGE_E2E_ENABLE = $priorEnable
  $env:TAURI_WEBDRIVER_PORT = $priorPort
}

# M3-32: operator/CI-opted-in standalone Tauri RELEASE startup probe.
# Launches only the exact, GPU-disabled release executable in this checkout.
# No model picker, WebDriver, GPU consent, screenshots, prompts or file traversal.
param(
  [Parameter(Mandatory = $true)][string]$Application
)
$ErrorActionPreference = "Stop"
$expected = [System.IO.Path]::GetFullPath((Join-Path (Get-Location).Path "src-tauri/target/release/aiimage.exe"))
$requested = [System.IO.Path]::GetFullPath($Application)
if ($requested -ine $expected) {
  throw "native_launch_probe: unsupported_application_path"
}
if (-not (Test-Path -LiteralPath $expected -PathType Leaf)) {
  throw "native_launch_probe: release_binary_missing"
}
$process = $null
$observedWindow = $false
$exited = $false
try {
  $process = Start-Process -FilePath $expected -WorkingDirectory (Split-Path $expected) -PassThru
  for ($n = 0; $n -lt 36; $n++) {
    Start-Sleep -Milliseconds 250
    $process.Refresh()
    if ($process.HasExited) { $exited = $true; break }
    if ($process.MainWindowHandle -ne [IntPtr]::Zero) {
      $observedWindow = $true
      break
    }
  }
  if ($exited) {
    # Only a category is emitted: never expose app exceptions, paths or logs.
    Write-Output "native_launch_probe: process_exited_before_window"
    throw "native_launch_probe: startup_failed"
  }
  if ($observedWindow) {
    Write-Output "native_launch_probe: main_window_handle_observed"
  } else {
    # Hosted GitHub runners may lack an interactive window station.
    # No window handle != a proof that the application did not launch.
    Write-Output "native_launch_probe: process_alive_window_not_observed"
  }
} finally {
  if ($null -ne $process) {
    try {
      $process.Refresh()
      if (-not $process.HasExited) {
        # Terminate only the exact process tree started by this probe.
        & taskkill.exe /PID $process.Id /T /F > $null 2>&1
      }
    } catch { Write-Output "native_launch_probe: cleanup_unconfirmed" }
  }
}

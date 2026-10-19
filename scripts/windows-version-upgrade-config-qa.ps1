# Safe, read-only QA of the two-version unsigned NSIS test configuration.
# Executed by ordinary Windows CI, WITHOUT building, installing or running apps.
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$base = Get-Content -LiteralPath (Join-Path $root 'src-tauri/tauri.conf.json') -Raw | ConvertFrom-Json
$backend = Get-Content -LiteralPath (Join-Path $root 'src-tauri/tauri.backend-qa.conf.json') -Raw | ConvertFrom-Json
$new = Get-Content -LiteralPath (Join-Path $root 'src-tauri/tauri.upgrade-qa.conf.json') -Raw | ConvertFrom-Json
if ($base.version -ne '0.1.0' -or $new.version -ne '0.1.1' -or
    @($new.PSObject.Properties.Name).Count -ne 1) {
  throw "upgrade_config_qa: version_overlay_not_exact"
}
if ($base.bundle.active -ne $false -or
    @($base.app.security.capabilities).Count -ne 1 -or
    $base.app.security.capabilities[0] -ne 'default') {
  throw "upgrade_config_qa: production_isolation_changed"
}
if (@($backend.build.features).Count -ne 1 -or
    $backend.build.features[0] -ne 'bundled-backend' -or
    $backend.bundle.targets[0] -ne 'nsis' -or
    $backend.bundle.windows.nsis.installMode -ne 'currentUser') {
  throw "upgrade_config_qa: bundled_backend_or_install_mode_changed"
}
Write-Output "upgrade_config_qa: safe_version_overlay_only"

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

# The third QA overlay must ONLY disable downgrade installs for the
# ephemeral NSIS test build. Neither normal production nor package metadata
# is overridden, and no test-only WebDriver capability can be enabled.
$guard = Get-Content -LiteralPath (Join-Path $root 'src-tauri/tauri.downgrade-guard-qa.conf.json') -Raw | ConvertFrom-Json
if (@($guard.PSObject.Properties.Name).Count -ne 1 -or
    @($guard.bundle.PSObject.Properties.Name).Count -ne 1 -or
    @($guard.bundle.windows.PSObject.Properties.Name).Count -ne 1 -or
    $guard.bundle.windows.allowDowngrades -ne $false -or
    @($backend.bundle.windows.PSObject.Properties.Name).Count -ne 1) {
  throw "upgrade_config_qa: downgrade_policy_not_isolated"
}
Write-Output "upgrade_config_qa: older_installer_downgrade_guard_enabled"
# M3-44: failpoint must exist ONLY in the disposable test overlay;
# the packaged read-only API and ordinary production hook must remain intact.
$preflight = Get-Content -LiteralPath (Join-Path $root 'src-tauri/tauri.preinstall-fault-qa.conf.json') -Raw | ConvertFrom-Json
$originalHook = Join-Path $root 'src-tauri/nsis/preserve-data.nsh'
$faultHook = Join-Path $root 'src-tauri/nsis/m3-44-preinstall-fault.nsh'
if (@($preflight.PSObject.Properties.Name).Count -ne 1 -or
    @($preflight.bundle.PSObject.Properties.Name).Count -ne 1 -or
    @($preflight.bundle.windows.PSObject.Properties.Name).Count -ne 1 -or
    @($preflight.bundle.windows.nsis.PSObject.Properties.Name).Count -ne 1 -or
    $preflight.bundle.windows.nsis.installerHooks -ne 'nsis/m3-44-preinstall-fault.nsh' -or
    $backend.bundle.windows.nsis.installerHooks -ne 'nsis/preserve-data.nsh' -or
    -not (Test-Path -LiteralPath $originalHook -PathType Leaf) -or
    -not (Test-Path -LiteralPath $faultHook -PathType Leaf)) {
  throw "upgrade_config_qa: preinstall_fault_overlay_not_isolated"
}
$source = Get-Content -LiteralPath $faultHook -Raw
$original = Get-Content -LiteralPath $originalHook -Raw
if ($source -notmatch [regex]::Escape('!include "${__FILEDIR__}\preserve-data.nsh"') -or
    $original -notmatch '!macro NSIS_HOOK_PREUNINSTALL' -or
    $source -notmatch '!macro NSIS_HOOK_PREINSTALL' -or
    $source -notmatch 'AIIMAGE_M3_44_ABORT_PREINSTALL' -or
    $source -notmatch 'SetErrorLevel 83' -or
    $source -notmatch '(?m)^\s+Quit\s*
 -or
    $source -match '(?m)^\s*(File|Delete|RMDir|WriteReg|Exec|ExecWait)\b') {
  throw "upgrade_config_qa: preinstall_abort_or_preserve_hook_invalid"
}
Write-Output "upgrade_config_qa: disposable_preinstall_failure_hook_isolated"
Write-Output "upgrade_config_qa: safe_version_overlay_only"

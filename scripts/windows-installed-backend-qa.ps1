# Disposable hosted CI only. Never run against an owner's existing installation.
param([switch] $VerifyTwoVersionUpgrade)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if ($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_OS -ne 'Windows') { throw 'installed_qa: disposable_ci_required' }
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$install = Join-Path $env:RUNNER_TEMP ('aiimage installed QA ' + [guid]::NewGuid().ToString())
$data = Join-Path $env:LOCALAPPDATA 'com.aiimage.studio'
if (Test-Path -LiteralPath $data) { throw 'installed_qa: existing_user_data_refused' }
$sentinel = Join-Path $data 'models/qa-preserve.txt'
New-Item -ItemType Directory -Path (Split-Path $sentinel) | Out-Null
[IO.File]::WriteAllText($sentinel, 'synthetic preservation fixture')
$outputSentinel = Join-Path $data 'outputs/qa-preserve.txt'
New-Item -ItemType Directory -Path (Split-Path $outputSentinel) | Out-Null
[IO.File]::WriteAllText($outputSentinel, 'synthetic output fixture')
$installer = @(Get-ChildItem (Join-Path $repo 'src-tauri/target/release/bundle/nsis') -Filter '*setup.exe')
if ($installer.Count -ne 1) { throw 'installed_qa: installer_count' }
$upgradeInstaller = $null
if ($VerifyTwoVersionUpgrade) {
  $upgradeInstaller = $installer[0]
  if ($upgradeInstaller.Name -notmatch '0\\.1\\.1') {
    throw 'installed_qa: upgrade_installer_version_unexpected'
  }
  $oldPath = Join-Path $env:RUNNER_TEMP 'aiimage-m3-42-original-setup.exe'
  if (-not (Test-Path -LiteralPath $oldPath -PathType Leaf)) {
    throw 'installed_qa: old_version_installer_missing'
  }
  $oldPath = (Resolve-Path -LiteralPath $oldPath).Path
  if ([IO.Path]::GetFullPath((Split-Path -Parent $oldPath)) -ne
      [IO.Path]::GetFullPath($env:RUNNER_TEMP)) {
    throw 'installed_qa: old_installer_outside_runner_temp'
  }
  $oldItem = Get-Item -LiteralPath $oldPath
  if (($oldItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
      $oldItem.Length -lt 100000) {
    throw 'installed_qa: old_installer_invalid'
  }
  $installer = @($oldItem)
}
$process = $null
$backendId = $null
try {
  $setup = Start-Process -FilePath $installer[0].FullName -ArgumentList "/S /D=$install" -PassThru
  if (-not $setup.WaitForExit(60000) -or $setup.ExitCode -ne 0) { throw 'installed_qa: install_failed' }
  $application = Join-Path $install 'aiimage.exe'
  if (-not (Test-Path -LiteralPath $application)) { throw 'installed_qa: app_missing' }
  python (Join-Path $repo 'scripts/backend-bundle-manifest.py') (Join-Path $install 'backend') --verify
  if ($LASTEXITCODE -ne 0) { throw 'installed_qa: payload_verification_failed' }

  # M3-41: same-version, same-directory /UPDATE repair on a disposable runner.
  # This is NOT a distinct-version upgrade or automatic updater acceptance.
  # No process is running yet; all payload and data checks precede GUI launch.
  $backendExecutable = Join-Path $install 'backend/aiimage-backend.exe'
  if (-not (Test-Path -LiteralPath $backendExecutable -PathType Leaf)) {
    throw 'installed_qa: backend_before_repair_missing'
  }
  $originalAppHash = (Get-FileHash -LiteralPath $application -Algorithm SHA256).Hash
  $originalBackendHash = (Get-FileHash -LiteralPath $backendExecutable -Algorithm SHA256).Hash
  $repair = Start-Process -FilePath $installer[0].FullName -ArgumentList "/S /UPDATE /D=$install" -PassThru
  if (-not $repair.WaitForExit(90000) -or $repair.ExitCode -ne 0) {
    throw 'installed_qa: same_version_repair_failed'
  }
  if (-not (Test-Path -LiteralPath $application -PathType Leaf) -or
      -not (Test-Path -LiteralPath $backendExecutable -PathType Leaf) -or
      -not (Test-Path -LiteralPath (Join-Path $install 'uninstall.exe') -PathType Leaf)) {
    throw 'installed_qa: repair_payload_missing'
  }
  if ((Get-FileHash -LiteralPath $application -Algorithm SHA256).Hash -ne $originalAppHash -or
      (Get-FileHash -LiteralPath $backendExecutable -Algorithm SHA256).Hash -ne $originalBackendHash) {
    throw 'installed_qa: repair_payload_changed_unexpectedly'
  }
  python (Join-Path $repo 'scripts/backend-bundle-manifest.py') (Join-Path $install 'backend') --verify
  if ($LASTEXITCODE -ne 0) { throw 'installed_qa: repair_manifest_failed' }
  if ([IO.File]::ReadAllText($sentinel) -ne 'synthetic preservation fixture' -or
      [IO.File]::ReadAllText($outputSentinel) -ne 'synthetic output fixture') {
    throw 'installed_qa: repair_user_data_changed'
  }
  Write-Output 'installed_qa: same_version_update_mode_repair_preserved_app_backend_models_and_outputs'

  if ($VerifyTwoVersionUpgrade) {
    # Two real different-version NSIS packages, not an updater plugin or
    # model data migration. This is a disposable per-user Windows runner.
    $uninstallKey = 'Registry::HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\aiimage'
    if (-not (Test-Path -LiteralPath $uninstallKey)) {
      throw 'installed_qa: older_version_uninstall_registration_missing'
    }
    $beforeVersion = (Get-ItemProperty -LiteralPath $uninstallKey -Name DisplayVersion).DisplayVersion
    if ($beforeVersion -ne '0.1.0') {
      throw 'installed_qa: older_version_not_registered'
    }
    $upgraded = Start-Process -FilePath $upgradeInstaller.FullName -ArgumentList "/S /UPDATE /D=$install" -PassThru
    if (-not $upgraded.WaitForExit(90000) -or $upgraded.ExitCode -ne 0) {
      throw 'installed_qa: different_version_upgrade_failed'
    }
    if (-not (Test-Path -LiteralPath $uninstallKey)) {
      throw 'installed_qa: upgraded_version_uninstall_registration_missing'
    }
    $afterVersion = (Get-ItemProperty -LiteralPath $uninstallKey -Name DisplayVersion).DisplayVersion
    if ($afterVersion -ne '0.1.1') {
      throw 'installed_qa: different_version_not_registered'
    }
    if (-not (Test-Path -LiteralPath $application -PathType Leaf) -or
        -not (Test-Path -LiteralPath $backendExecutable -PathType Leaf) -or
        -not (Test-Path -LiteralPath (Join-Path $install 'uninstall.exe') -PathType Leaf)) {
      throw 'installed_qa: upgraded_payload_missing'
    }
    if ((Get-FileHash -LiteralPath $backendExecutable -Algorithm SHA256).Hash -ne $originalBackendHash) {
      throw 'installed_qa: upgraded_backend_changed_unexpectedly'
    }
    python (Join-Path $repo 'scripts/backend-bundle-manifest.py') (Join-Path $install 'backend') --verify
    if ($LASTEXITCODE -ne 0) { throw 'installed_qa: upgraded_backend_manifest_failed' }
    if ([IO.File]::ReadAllText($sentinel) -ne 'synthetic preservation fixture' -or
        [IO.File]::ReadAllText($outputSentinel) -ne 'synthetic output fixture') {
      throw 'installed_qa: upgraded_user_data_changed'
    }
    Write-Output 'installed_qa: two_version_0_1_0_to_0_1_1_upgrade_preserved_backend_models_and_outputs'
  }

  Add-Type -AssemblyName UIAutomationClient
  Add-Type -AssemblyName UIAutomationTypes
  # NSIS creates its checkbox dynamically with CreateWindowEx. Its Win32 style
  # is authoritative even when the UI Automation provider omits that control.
  Add-Type @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;
public static class AiimageNsisControls {
  public delegate bool EnumProc(IntPtr window, IntPtr data);
  [DllImport("user32.dll")] static extern bool EnumChildWindows(IntPtr parent, EnumProc callback, IntPtr data);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern int GetClassName(IntPtr window, StringBuilder text, int count);
  [DllImport("user32.dll")] static extern int GetWindowLong(IntPtr window, int index);
  [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr window);
  [DllImport("user32.dll")] public static extern IntPtr GetDlgItem(IntPtr window, int id);
  [DllImport("user32.dll")] public static extern IntPtr SendMessage(IntPtr window, uint message, IntPtr w, IntPtr l);
  public static IntPtr[] Checkboxes(IntPtr parent) {
    var result = new List<IntPtr>();
    EnumChildWindows(parent, (window, _) => {
      var name = new StringBuilder(256); GetClassName(window, name, 256);
      int kind = GetWindowLong(window, -16) & 15;
      if (IsWindowVisible(window) && name.ToString() == "Button" && (kind == 2 || kind == 3)) result.Add(window);
      return true;
    }, IntPtr.Zero);
    return result.ToArray();
  }
}
'@
  foreach ($mode in @('normal_close', 'parent_crash', 'restart_after_backend_crash')) {
    $process = Start-Process -FilePath $application -WorkingDirectory $install -PassThru
    $connected = $false
    $until = [DateTime]::UtcNow.AddSeconds(40)
    while ([DateTime]::UtcNow -lt $until) {
      Start-Sleep -Milliseconds 500
      $process.Refresh()
      if ($process.HasExited) { throw 'installed_qa: app_exited' }
      $children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$($process.Id) AND Name='aiimage-backend.exe'")
      if ($children.Count -gt 1) { throw 'installed_qa: duplicate_backend' }
      if ($children.Count -eq 1 -and $process.MainWindowHandle -ne [IntPtr]::Zero) {
        $backendId = [int]$children[0].ProcessId
        $window = [System.Windows.Automation.AutomationElement]::FromHandle($process.MainWindowHandle)
        $condition = [System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::NameProperty, 'Python API 연결됨')
        $label = $window.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $condition)
        if ($null -ne $label) { $connected = $true; break }
      }
    }
    if (-not $connected) { throw 'installed_qa: authenticated_ui_status_not_observed' }
    $ports = @(Get-NetTCPConnection -OwningProcess $backendId -State Listen)
    if ($ports.Count -ne 1 -or $ports[0].LocalAddress -ne '127.0.0.1') { throw 'installed_qa: non_loopback_listener' }
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:$($ports[0].LocalPort)/api/status" -SkipHttpErrorCheck -NoProxy
    if ($response.StatusCode -ne 401) { throw 'installed_qa: unauthenticated_access' }
    if ($mode -eq 'restart_after_backend_crash') {
      # Kill only the owned disposable backend, never another PID or user data.
      # The installed GUI must show its explicit restart control after the
      # normal status-poll interval; no direct restart IPC is invoked here.
      $previousBackendId = $backendId
      Stop-Process -Id $previousBackendId -Force
      $until = [DateTime]::UtcNow.AddSeconds(15)
      while ((Get-Process -Id $previousBackendId -ErrorAction SilentlyContinue) -and [DateTime]::UtcNow -lt $until) {
        Start-Sleep -Milliseconds 100
      }
      if (Get-Process -Id $previousBackendId -ErrorAction SilentlyContinue) {
        throw 'installed_qa: killed_backend_still_running'
      }
      $restartButton = $null
      $until = [DateTime]::UtcNow.AddSeconds(45)
      while ([DateTime]::UtcNow -lt $until) {
        Start-Sleep -Milliseconds 400
        $process.Refresh()
        if ($process.HasExited) { throw 'installed_qa: app_exited_before_restart' }
        $window = [System.Windows.Automation.AutomationElement]::FromHandle($process.MainWindowHandle)
        $condition = [System.Windows.Automation.PropertyCondition]::new(
          [System.Windows.Automation.AutomationElement]::NameProperty, '백엔드 다시 시작')
        $restartButton = $window.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $condition)
        if ($null -ne $restartButton -and $restartButton.Current.IsEnabled) { break }
      }
      if ($null -eq $restartButton -or -not $restartButton.Current.IsEnabled) {
        throw 'installed_qa: restart_button_not_visible'
      }
      $pattern = $restartButton.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
      if ($null -eq $pattern) { throw 'installed_qa: restart_button_not_invokable' }
      ([System.Windows.Automation.InvokePattern]$pattern).Invoke()
      $reconnected = $false
      $until = [DateTime]::UtcNow.AddSeconds(45)
      while ([DateTime]::UtcNow -lt $until) {
        Start-Sleep -Milliseconds 400
        $process.Refresh()
        if ($process.HasExited) { throw 'installed_qa: app_exited_during_restart' }
        $children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$($process.Id) AND Name='aiimage-backend.exe'")
        if ($children.Count -gt 1) { throw 'installed_qa: duplicate_backend_after_restart' }
        if ($children.Count -ne 1) { continue }
        $candidatePid = [int]$children[0].ProcessId
        if ($candidatePid -eq $previousBackendId) { throw 'installed_qa: stale_backend_reused' }
        $window = [System.Windows.Automation.AutomationElement]::FromHandle($process.MainWindowHandle)
        $connectedCondition = [System.Windows.Automation.PropertyCondition]::new(
          [System.Windows.Automation.AutomationElement]::NameProperty, 'Python API 연결됨')
        if ($null -ne $window.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $connectedCondition)) {
          $backendId = $candidatePid
          $reconnected = $true
          break
        }
      }
      if (-not $reconnected) { throw 'installed_qa: restart_did_not_reconnect' }
      $newPorts = @(Get-NetTCPConnection -OwningProcess $backendId -State Listen)
      if ($newPorts.Count -ne 1 -or $newPorts[0].LocalAddress -ne '127.0.0.1') {
        throw 'installed_qa: restarted_backend_not_loopback'
      }
      $newResponse = Invoke-WebRequest -Uri "http://127.0.0.1:$($newPorts[0].LocalPort)/api/status" -SkipHttpErrorCheck -NoProxy
      if ($newResponse.StatusCode -ne 401) {
        throw 'installed_qa: restarted_backend_unauthenticated_access'
      }
      if (-not $process.CloseMainWindow() -or -not $process.WaitForExit(15000)) {
        throw 'installed_qa: normal_close_after_restart_failed'
      }
      Write-Output 'installed_qa: installed_gui_restart_click_reconnected_and_no_orphans'
    } elseif ($mode -eq 'normal_close') {
      if (-not $process.CloseMainWindow() -or -not $process.WaitForExit(15000)) { throw 'installed_qa: normal_close_failed' }
    } else {
      # Kill ONLY the parent. The child's disappearance must be due to Job Object cleanup.
      Stop-Process -Id $process.Id -Force
      $process.WaitForExit(15000) | Out-Null
    }
    $until = [DateTime]::UtcNow.AddSeconds(10)
    while ((Get-Process -Id $backendId -ErrorAction SilentlyContinue) -and [DateTime]::UtcNow -lt $until) { Start-Sleep -Milliseconds 100 }
    if (Get-Process -Id $backendId -ErrorAction SilentlyContinue) { throw 'installed_qa: orphan_backend' }
    Write-Output "installed_qa: $mode authenticated_gui_and_cleanup_passed"
    $process = $null
    $backendId = $null
  }
  $uninstaller = Join-Path $install 'uninstall.exe'
  if (-not (Test-Path -LiteralPath $uninstaller)) { throw 'installed_qa: uninstaller_missing' }
  # _?= keeps the uninstaller in this process instead of a temporary self-copy.
  # Select stock Tauri's destructive checkbox to prove our preservation hook wins.
  $remove = Start-Process -FilePath $uninstaller -ArgumentList "_?=$install" -PassThru
  $until = [DateTime]::UtcNow.AddSeconds(20)
  $checkbox = [IntPtr]::Zero
  while ([DateTime]::UtcNow -lt $until) {
    Start-Sleep -Milliseconds 250
    $remove.Refresh()
    if ($remove.HasExited) { throw 'installed_qa: uninstaller_exited_early' }
    if ($remove.MainWindowHandle -eq [IntPtr]::Zero) { continue }
    $checks = [AiimageNsisControls]::Checkboxes($remove.MainWindowHandle)
    if ($checks.Count -eq 1) { $checkbox = $checks[0]; break }
  }
  if ($checkbox -eq [IntPtr]::Zero) {
    Write-Output "installed_qa: uninstaller_window=$($remove.MainWindowHandle) title=$($remove.MainWindowTitle)"
    throw 'installed_qa: data_checkbox_not_observed'
  }
  [AiimageNsisControls]::SendMessage($checkbox, 0x00F5, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null # BM_CLICK
  if ([AiimageNsisControls]::SendMessage($checkbox, 0x00F0, [IntPtr]::Zero, [IntPtr]::Zero).ToInt32() -ne 1) { throw 'installed_qa: checkbox_not_selected' }
  Write-Output 'installed_qa: destructive_checkbox_visibly_selected'
  $button = [AiimageNsisControls]::GetDlgItem($remove.MainWindowHandle, 1)
  if ($button -eq [IntPtr]::Zero) { throw 'installed_qa: uninstall_button_missing' }
  [AiimageNsisControls]::SendMessage($button, 0x00F5, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null
  $until = [DateTime]::UtcNow.AddSeconds(20)
  while ((Test-Path -LiteralPath $application) -and [DateTime]::UtcNow -lt $until) { Start-Sleep -Milliseconds 250 }
  if (Test-Path -LiteralPath $application) { throw 'installed_qa: app_remained_after_uninstall' }
  if ([IO.File]::ReadAllText($sentinel) -ne 'synthetic preservation fixture') { throw 'installed_qa: user_data_changed' }
  if ([IO.File]::ReadAllText($outputSentinel) -ne 'synthetic output fixture') { throw 'installed_qa: output_data_changed' }
  # Close the completed uninstall page after verifying payload removal.
  $until = [DateTime]::UtcNow.AddSeconds(20)
  while (-not $remove.HasExited -and [DateTime]::UtcNow -lt $until) {
    try {
      $button = [AiimageNsisControls]::GetDlgItem($remove.MainWindowHandle, 1)
      if ($button -ne [IntPtr]::Zero) { [AiimageNsisControls]::SendMessage($button, 0x00F5, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null }
    } catch { }
    Start-Sleep -Milliseconds 250
    $remove.Refresh()
  }
  if (-not $remove.HasExited -or $remove.ExitCode -ne 0) { throw 'installed_qa: uninstall_failed' }
  Write-Output 'installed_qa: interactive_uninstall_with_delete_checkbox_preserved_models_and_outputs'
} finally {
  if ($null -ne $process -and -not $process.HasExited) { Stop-Process -Id $process.Id -Force }
  if ($null -ne $backendId) { Stop-Process -Id $backendId -Force -ErrorAction SilentlyContinue }
  # Runner is disposable; no recursive data deletion or installer publication.
}

# Disposable hosted CI only. Never run against an owner's existing installation.
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
$process = $null
$backendId = $null
try {
  $setup = Start-Process -FilePath $installer[0].FullName -ArgumentList "/S /D=$install" -PassThru
  if (-not $setup.WaitForExit(60000) -or $setup.ExitCode -ne 0) { throw 'installed_qa: install_failed' }
  $application = Join-Path $install 'aiimage.exe'
  if (-not (Test-Path -LiteralPath $application)) { throw 'installed_qa: app_missing' }
  python (Join-Path $repo 'scripts/backend-bundle-manifest.py') (Join-Path $install 'backend') --verify
  if ($LASTEXITCODE -ne 0) { throw 'installed_qa: payload_verification_failed' }
  Add-Type -AssemblyName UIAutomationClient
  Add-Type -AssemblyName UIAutomationTypes
  foreach ($mode in @('normal_close', 'parent_crash')) {
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
    if ($mode -eq 'normal_close') {
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
  $checkbox = $null
  while ([DateTime]::UtcNow -lt $until) {
    Start-Sleep -Milliseconds 250
    $remove.Refresh()
    if ($remove.HasExited) { throw 'installed_qa: uninstaller_exited_early' }
    if ($remove.MainWindowHandle -eq [IntPtr]::Zero) { continue }
    $dialog = [System.Windows.Automation.AutomationElement]::FromHandle($remove.MainWindowHandle)
    $checkCondition = [System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::CheckBox)
    $checkbox = $dialog.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $checkCondition)
    if ($null -ne $checkbox) { break }
  }
  if ($null -eq $checkbox) { throw 'installed_qa: data_checkbox_not_observed' }
  $toggle = $checkbox.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern)
  if ($toggle.Current.ToggleState -ne [System.Windows.Automation.ToggleState]::On) { $toggle.Toggle() }
  if ($toggle.Current.ToggleState -ne [System.Windows.Automation.ToggleState]::On) { throw 'installed_qa: checkbox_not_selected' }
  $buttonCondition = [System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::AutomationIdProperty, '1')
  $button = $dialog.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $buttonCondition)
  if ($null -eq $button) { throw 'installed_qa: uninstall_button_missing' }
  $button.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
  $until = [DateTime]::UtcNow.AddSeconds(20)
  while ((Test-Path -LiteralPath $application) -and [DateTime]::UtcNow -lt $until) { Start-Sleep -Milliseconds 250 }
  if (Test-Path -LiteralPath $application) { throw 'installed_qa: app_remained_after_uninstall' }
  if ([IO.File]::ReadAllText($sentinel) -ne 'synthetic preservation fixture') { throw 'installed_qa: user_data_changed' }
  if ([IO.File]::ReadAllText($outputSentinel) -ne 'synthetic output fixture') { throw 'installed_qa: output_data_changed' }
  # Close the completed uninstall page after verifying payload removal.
  $until = [DateTime]::UtcNow.AddSeconds(20)
  while (-not $remove.HasExited -and [DateTime]::UtcNow -lt $until) {
    try {
      $button = $dialog.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $buttonCondition)
      if ($null -ne $button -and $button.Current.IsEnabled) { $button.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke() }
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

# Windows-only deterministic smoke test. Never starts the Tauri UI or GPU.
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptPath = Join-Path $PSScriptRoot "windows-dev.ps1"
$tokens = $null
$parseErrors = $null
$null = [System.Management.Automation.Language.Parser]::ParseFile(
    $scriptPath, [ref] $tokens, [ref] $parseErrors
)
if ($parseErrors.Count -ne 0) {
    throw ("Windows readiness script has PowerShell syntax errors: " +
           ($parseErrors | ForEach-Object { $_.Message } | Out-String))
}

# Check-only must emit one machine-readable JSON report without launching npm.
$json = (& $scriptPath -AsJson | Out-String).Trim()
$report = $json | ConvertFrom-Json
if ($report.schema_version -ne 1 -or $report.milestone -ne "M3-22") {
    throw "Unexpected readiness report schema."
}
if ($report.execution -ne "check_only") {
    throw "Readiness check unexpectedly requested a process launch."
}
if ($report.status -notin @(
    "development_launch_prerequisites_observed",
    "missing_required_prerequisites"
)) {
    throw "Unexpected readiness outcome."
}
$names = @($report.checks | ForEach-Object { $_.name })
$expected = @("windows", "node", "npm", "cargo", "rust_msvc",
              "repository", "frontend_dependencies", "webview2", "msvc_cpp", "optional_python")
foreach ($name in $expected) {
    if ($names -notcontains $name) {
        throw ("Missing readiness category: " + $name)
    }
}
if ($names.Count -ne (@($names | Select-Object -Unique)).Count) {
    throw "Duplicate readiness categories."
}
if (@($report.checks | Where-Object {
    $_.status -notin @("ready", "missing", "check_manually", "not_configured")
}).Count -ne 0) {
    throw "Unrecognized readiness check status."
}
$requiredMissing = @($report.checks | Where-Object {
    $_.required_for_start -and $_.status -ne "ready"
})
if ($requiredMissing.Count -eq 0 -and $report.status -ne "development_launch_prerequisites_observed") {
    throw "All necessary prereqs are ready but report disagrees."
}
if ($requiredMissing.Count -gt 0 -and $report.status -ne "missing_required_prerequisites") {
    throw "Missing prerequisites must fail the preflight."
}

$rejected = $false
try {
    $null = & $scriptPath -Start -AsJson
} catch {
    $rejected = $true
}
if (-not $rejected) {
    throw "JSON and launch together must be rejected without starting a process."
}

# Source-level policy: no automatic dependencies, download, remote fetch,
# script execution or privilege escalation in this check-only/start wrapper.
$source = Get-Content -LiteralPath $scriptPath -Raw
foreach ($pattern in @(
    '(?im)^\s*Invoke-Expression\s',
    '(?im)^\s*Invoke-WebRequest\s',
    '(?im)^\s*Install-Module\s',
    '(?im)^\s*Start-Process\s',
    '(?im)^\s*winget\s',
    '(?im)^\s*&\s*\$npm\s+(?:install|ci)\b'
)) {
    if ($source -match $pattern) {
        throw "Launcher contains an unauthorized automatic installation/execution path."
    }
}
Write-Output ("PASS M3-22: PowerShell syntax, check-only JSON, opt-in start guard, prerequisites (" +
              $names.Count + ") and no-install policy.")

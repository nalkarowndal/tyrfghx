<#
.SYNOPSIS
  aiimage M3-22: read-only Windows Tauri development readiness checks.
.DESCRIPTION
  The DEFAULT is check-only. -Start is an explicit, separate operator action
  that launches the local Tauri development UI. It never installs packages,
  downloads models, executes CUDA, bypasses GPU consent or bundles a release.
.EXAMPLE
  .\scripts\windows-dev.ps1
.EXAMPLE
  .\scripts\windows-dev.ps1 -AsJson
.EXAMPLE
  .\scripts\windows-dev.ps1 -Start
#>
[CmdletBinding()]
param(
    [switch] $Start,
    [switch] $AsJson
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$checks = New-Object 'System.Collections.Generic.List[object]'

function Add-Check {
    param([string] $Name, [string] $Status, [string] $Explanation, [bool] $Required = $false)
    $checks.Add([pscustomobject]@{
        name = $Name
        status = $Status
        required_for_start = $Required
        explanation = $Explanation
    })
}

function Get-Executable {
    param([string] $Name)
    $found = Get-Command $Name -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($null -eq $found) { return $null }
    return [string] $found.Source
}

function Get-CommandVersion {
    param([string] $Executable, [string[]] $Arguments)
    if ([string]::IsNullOrEmpty($Executable)) { return "" }
    try {
        $lines = & $Executable @Arguments 2>$null
        if ($LASTEXITCODE -ne 0 -or $null -eq $lines) { return "" }
        return ([string] ($lines | Select-Object -First 1)).Trim()
    } catch {
        return ""
    }
}

if ($Start -and $AsJson) {
    throw "Use -Start and -AsJson separately. JSON mode is read-only."
}

$isWin = $env:OS -eq "Windows_NT"
if (-not $isWin) {
    Add-Check "windows" "missing" "Windows 10/11 desktop is required for this development launcher." $true
} else {
    Add-Check "windows" "ready" "Windows desktop detected." $true
}

$node = Get-Executable "node.exe"
$nodeVersion = Get-CommandVersion $node @("--version")
$nodeMajor = 0
if ($nodeVersion -match '^v(\d+)\.') { $nodeMajor = [int]$Matches[1] }
if ($nodeMajor -ge 20) {
    Add-Check "node" "ready" ("Node.js " + $nodeVersion + " available (20+).") $true
} else {
    Add-Check "node" "missing" "Install Node.js 20+; Node.js 22 is the CI-tested version." $true
}

$npm = Get-Executable "npm.cmd"
if (-not $npm) { $npm = Get-Executable "npm" }
$npmVersion = Get-CommandVersion $npm @("--version")
if ($npmVersion -match '^\d+\.\d+') {
    Add-Check "npm" "ready" ("npm " + $npmVersion + " available.") $true
} else {
    Add-Check "npm" "missing" "npm must be installed with Node.js." $true
}

$cargo = Get-Executable "cargo.exe"
$cargoVersion = Get-CommandVersion $cargo @("--version")
if ($cargoVersion -match '^cargo ') {
    Add-Check "cargo" "ready" "Rust Cargo command available." $true
} else {
    Add-Check "cargo" "missing" "Install Rust (stable MSVC host target) and Cargo." $true
}

$rustc = Get-Executable "rustc.exe"
$rustDetails = Get-CommandVersion $rustc @("-vV")
# -vV produces multiple lines; query the full output to verify the MSVC host.
$rustHost = ""
if ($rustc) {
    try {
        $rustHostLines = & $rustc -vV 2>$null
        $rustHost = [string] ($rustHostLines | Where-Object { $_ -match '^host: ' } | Select-Object -First 1)
    } catch { $rustHost = "" }
}
if ($rustHost -match 'host:\s+[A-Za-z0-9_-]+windows-msvc$') {
    Add-Check "rust_msvc" "ready" "Rust host toolchain targets Windows MSVC." $true
} else {
    Add-Check "rust_msvc" "missing" "Select a stable Windows MSVC Rust toolchain (not GNU)." $true
}

$package = Join-Path $repo "package.json"
$config = Join-Path $repo "src-tauri\tauri.conf.json"
if ((Test-Path -LiteralPath $package -PathType Leaf) -and
    (Test-Path -LiteralPath $config -PathType Leaf)) {
    Add-Check "repository" "ready" "Tauri config and package.json detected." $true
} else {
    Add-Check "repository" "missing" "Run from an intact aiimage repository checkout." $true
}

$tauriCli = Join-Path $repo "node_modules\.bin\tauri.cmd"
if (Test-Path -LiteralPath $tauriCli -PathType Leaf) {
    Add-Check "frontend_dependencies" "ready" "Local Tauri CLI exists in node_modules." $true
} else {
    Add-Check "frontend_dependencies" "missing" "Run npm install explicitly from repository root first (no committed package-lock.json yet)." $true
}

# WebView2 and MSVC installation can vary across Windows installations.
# These checks are advisory, not claims of a successful UI launch.
$webviewKey = "{F1D908F2-AAC5-49B4-AE85-837C47E2C0C0}"
$webviewRoots = @(
    ("HKLM:\SOFTWARE\Microsoft\EdgeUpdate\Clients\" + $webviewKey),
    ("HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\" + $webviewKey),
    ("HKCU:\SOFTWARE\Microsoft\EdgeUpdate\Clients\" + $webviewKey)
)
$webviewDetected = $false
foreach ($entry in $webviewRoots) {
    try {
        $version = (Get-ItemProperty -LiteralPath $entry -Name "pv" -ErrorAction Stop).pv
        if ($version -and $version -ne "0.0.0.0") { $webviewDetected = $true; break }
    } catch { }
}
if ($webviewDetected) {
    Add-Check "webview2" "ready" "WebView2 runtime registration detected; UI still needs manual testing."
} else {
    Add-Check "webview2" "check_manually" "WebView2 could not be verified in common registry keys; inspect Edge WebView2 Runtime."
}

$programFilesX86 = [Environment]::GetFolderPath("ProgramFilesX86")
$vswhere = if ($programFilesX86) { Join-Path $programFilesX86 "Microsoft Visual Studio\Installer\vswhere.exe" } else { "" }
$vcDetected = $false
if ($vswhere -and (Test-Path -LiteralPath $vswhere -PathType Leaf)) {
    try {
        $installation = & $vswhere -latest -products "*" -requires "Microsoft.VisualStudio.Component.VC.Tools.x86.x64" -property installationPath 2>$null
        if ($installation) { $vcDetected = $true }
    } catch { }
}
if ($vcDetected) {
    Add-Check "msvc_cpp" "ready" "Visual Studio C++ Build Tools installation detected."
} else {
    Add-Check "msvc_cpp" "check_manually" "Verify MSVC Desktop development with C++ in Visual Studio Installer."
}

$venvPython = Join-Path $repo ".venv\Scripts\python.exe"
if (Test-Path -LiteralPath $venvPython -PathType Leaf) {
    Add-Check "optional_python" "ready" "Local .venv Python exists; CUDA/inference dependencies are NOT verified."
} else {
    Add-Check "optional_python" "not_configured" "Local Python .venv absent: UI can open, but developer CUDA generation is unavailable."
}

$needed = @($checks | Where-Object { $_.required_for_start -and $_.status -ne "ready" })
$ready = $needed.Count -eq 0
$report = [pscustomobject]@{
    schema_version = 1
    milestone = "M3-22"
    status = if ($ready) { "development_launch_prerequisites_observed" } else { "missing_required_prerequisites" }
    execution = if ($Start) { "requested" } else { "check_only" }
    checks = @($checks)
    warning = "Prerequisite presence is not an actual GUI/GPU acceptance test; release GPU execution remains disabled."
}

if (-not $Start) {
    if ($AsJson) {
        $report | ConvertTo-Json -Depth 6 -Compress
    } else {
        Write-Host "aiimage | M3-22 Windows development readiness"
        foreach ($item in $checks) {
            Write-Host ("[{0}] {1}: {2}" -f $item.status, $item.name, $item.explanation)
        }
        Write-Host "Check only. No installs, downloads, GPU work or app launch performed."
        if (-not $ready) { Write-Host "Some required prerequisites are missing; see items above." }
    }
    return
}

if (-not $ready) {
    Write-Error "Tauri 개발판을 실행할 필수 환경이 준비되지 않았습니다. -AsJson으로 진단하고 필요한 항목을 직접 설치하세요."
    return
}

Write-Host "사용자가 -Start를 명시했습니다. GPU 생성이 아닌 로컬 Tauri 개발 UI만 시작합니다."
Push-Location $repo
try {
    # Fixed local package.json script. No user-selected executable or shell.
    & $npm run tauri dev
    if ($LASTEXITCODE -ne 0) {
        throw "Tauri 개발판 실행에 실패했습니다. 오류 내용을 확인하세요."
    }
} finally {
    Pop-Location
}

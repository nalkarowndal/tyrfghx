# Build only in a new, isolated environment; no CUDA/model dependencies.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if ($env:OS -ne 'Windows_NT') { throw 'backend_bundle: windows_required' }
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $repo
python -c "import sys,struct; assert sys.version_info[:2] == (3,12) and struct.calcsize('P') == 8"
if ($LASTEXITCODE -ne 0) { throw 'backend_bundle: python_312_x64_required' }
$build = Join-Path $repo '.backend-build'
if (Test-Path -LiteralPath $build) { throw 'backend_bundle: fresh_build_directory_required' }
python -m venv (Join-Path $build 'venv')
if ($LASTEXITCODE -ne 0) { throw 'backend_bundle: venv_failed' }
$python = Join-Path $build 'venv/Scripts/python.exe'
& $python -m pip install --require-hashes -r backend/requirements-bundle.lock
if ($LASTEXITCODE -ne 0) { throw 'backend_bundle: dependency_install_failed' }
& $python -m pip check
if ($LASTEXITCODE -ne 0) { throw 'backend_bundle: dependency_check_failed' }
& $python -m PyInstaller --noconfirm --clean --onedir --noupx --name aiimage-backend `
  --distpath src-tauri/backend-dist --workpath .backend-build/work --specpath .backend-build `
  --paths backend --hidden-import uvicorn.logging --hidden-import uvicorn.loops.asyncio `
  --hidden-import uvicorn.protocols.http.h11_impl --hidden-import uvicorn.lifespan.on `
  --exclude-module torch --exclude-module diffusers --exclude-module pytest backend/bundled_server.py
if ($LASTEXITCODE -ne 0) { throw 'backend_bundle: freeze_failed' }
& $python scripts/backend-bundle-manifest.py src-tauri/backend-dist/aiimage-backend
if ($LASTEXITCODE -ne 0) { throw 'backend_bundle: manifest_failed' }

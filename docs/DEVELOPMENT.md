# aiimage M1 Development

## Scope
M1 desktop UI + local API foundation. NO model inference, downloads, image saving, video rendering, canvas AI, or auto-started backend is implemented. Backend must be started separately; do not claim this is a packaged working GPU application. M10 is Krea-inspired creative workflow, excluding multi-character generation.

## Local Windows development
Install Node 22+, Python 3.11+, Rust, Windows C++ Build Tools and WebView2 for Tauri.

Terminal A:
```powershell
cd backend
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m uvicorn app:app --host 127.0.0.1 --port 8765
```
Terminal B, from repository root:
```powershell
npm install
npm run dev
```
Optionally launch native window after Rust setup: `npm run tauri dev`.

## Tests
- `cd backend && python -m pytest -q`
- `npm run build`
- `npm test`
- Real RTX 2060 SUPER GPU/VRAM testing: **not implemented**
- Windows Tauri **Rust compile/unit tests**: implemented in CI. Interactive runtime and GUI verification: **pending**

API binds exclusively to loopback. Browser CORS is restricted to local development/Tauri origins. Later backend endpoints must implement trusted-origin and request authorization checks to protect local filesystem and model operations.

## Next steps
- Confirm CI executes, fix any environment differences.
- Implement model catalog and explicit opt-in ComfyUI adapter (M2); GPU runtime remains M3.
- Add lockfiles, packaging icons, installer/signature strategy before production release.

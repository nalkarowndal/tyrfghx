"""M4-Integration: verify Tauri release CSP stays least privilege.

Static policy checks are **not** an installed-WebView security proof.
The label-gated Windows E2E workflow must also run on the exact head.
"""
from __future__ import annotations
from pathlib import Path
import json
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "src-tauri" / "tauri.conf.json"


def _policy():
    data = json.loads(CONFIG.read_text(encoding="utf-8"))
    return data["app"]["security"]["csp"], data["app"]["security"]["devCsp"]


def test_production_csp_is_configured_and_does_not_use_wildcards_or_eval():
    release, _ = _policy()
    assert release["default-src"] == "'self'"
    assert release["object-src"] == "'none'"
    assert release["frame-src"] == "'none'"
    assert release["base-uri"] == "'none'"
    assert "unsafe-eval" not in json.dumps(release)
    assert "https:" not in json.dumps(release)
    assert "*" not in json.dumps(release)


def test_native_ipc_and_only_bounded_loopback_backend_are_allowed():
    release, _ = _policy()
    sources = release["connect-src"].split()
    assert {"'self'", "ipc:", "http://ipc.localhost", "http://127.0.0.1:8765"} <= set(sources)
    remote_http = [x for x in sources if x.startswith(("http://", "https://"))]
    assert set(remote_http) == {"http://ipc.localhost", "http://127.0.0.1:8765"}
    for source in remote_http:
        parsed = urlparse(source)
        assert parsed.hostname in ("ipc.localhost", "127.0.0.1")


def test_existing_local_png_gallery_images_remain_renderable():
    release, _ = _policy()
    sources = release["img-src"].split()
    assert "'self'" in sources
    assert "data:" in sources  # Rust gallery uses data:image/png;base64
    assert "blob:" in sources
    assert "http:" not in sources
    assert "https:" not in sources


def test_development_hot_reload_allowance_does_not_leak_to_release():
    release, dev = _policy()
    assert "ws://127.0.0.1:5173" in dev["connect-src"]
    assert "http://127.0.0.1:5173" in dev["connect-src"]
    assert "unsafe-eval" in dev["script-src"]  # DEV ONLY
    assert "unsafe-eval" not in json.dumps(release)
    assert "ws:" not in json.dumps(release)


def test_csp_is_applied_to_main_capability_without_enabling_remote_access():
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    sec = config["app"]["security"]
    assert sec["capabilities"] == ["default"]
    assert "dangerousRemoteUrlIpcAccess" not in sec
    cap = json.loads((ROOT / "src-tauri" / "capabilities" / "default.json").read_text(encoding="utf-8"))
    assert cap["windows"] == ["main"]
    assert "remote" not in cap

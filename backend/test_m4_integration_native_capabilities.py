"""M4-Integration native Tauri command exposure review, static fail-closed guard.

This compares the actual production invoke handler to build-time app command
permission generation and explicitly granted main-window capability. It does
not claim the compiled installer has passed GUI end-to-end testing.
"""
from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[1]
TAURI = ROOT / "src-tauri"
APP_BUILD = TAURI / "build.rs"
APP_ENTRY = TAURI / "src" / "lib.rs"
CAPABILITY = TAURI / "capabilities" / "default.json"
CONFIG = TAURI / "tauri.conf.json"


def _native_commands():
    source = APP_ENTRY.read_text(encoding="utf-8")
    match = re.search(r"\.invoke_handler\(tauri::generate_handler!\[(.*?)\]\)", source, re.S)
    assert match, "Production handler missing or changed; audit needed"
    return set(re.findall(r"\b(?:\w+::)+(\w+)\b", match.group(1)))


def _declared_commands():
    source = APP_BUILD.read_text(encoding="utf-8")
    assert "AppManifest::new().commands(&[" in source
    match = re.search(r"AppManifest::new\(\)\.commands\(&\[(.*?)\]\)", source, re.S)
    assert match, "Explicit manifest command list missing"
    return set(re.findall(r'"([a-z_]+)"', match.group(1)))


def test_build_manifest_matches_all_registered_app_commands_exactly():
    registered = _native_commands()
    declared = _declared_commands()
    assert len(registered) == 13, "Update security review for any new native command"
    assert registered == declared


def test_only_main_local_webview_has_explicit_app_command_rights():
    cap = json.loads(CAPABILITY.read_text(encoding="utf-8"))
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    assert cfg["app"]["security"]["capabilities"] == ["default"]
    assert cap["identifier"] == "default"
    assert cap["windows"] == ["main"]
    assert "webviews" not in cap
    assert "remote" not in cap
    assert "core:default" in cap["permissions"]

    expected = {"allow-" + name.replace("_", "-") for name in _native_commands()}
    granted = {p for p in cap["permissions"] if p.startswith("allow-")}
    assert expected == granted
    assert len(cap["permissions"]) == 14


def test_privileged_app_commands_are_not_globally_granted():
    cap = json.loads(CAPABILITY.read_text(encoding="utf-8"))
    assert "*" not in cap["windows"]
    assert "allow-all" not in cap["permissions"]
    assert "default" not in cap["permissions"]
    assert "dangerousRemoteUrlIpcAccess" not in json.loads(
        CONFIG.read_text(encoding="utf-8")
    )["app"]["security"]

"""M3-Final audit: prove regression guards fail closed on unsafe changes."""
from importlib import util
from pathlib import Path
import shutil

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "m3_final_gate.py"
SPEC = util.spec_from_file_location("m3_final_gate", SCRIPT)
assert SPEC and SPEC.loader
gate = util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)

AUDITED_PATHS = (
    "src-tauri/tauri.conf.json",
    "src-tauri/tauri.backend-qa.conf.json",
    "src-tauri/tauri.upgrade-qa.conf.json",
    "src-tauri/tauri.downgrade-guard-qa.conf.json",
    "src-tauri/tauri.preinstall-fault-qa.conf.json",
    "src-tauri/Cargo.toml",
    "src-tauri/nsis/preserve-data.nsh",
    "src-tauri/nsis/m3-44-preinstall-fault.nsh",
    "scripts/windows-installed-backend-qa.ps1",
    ".github/workflows/windows-backend-bundle-qa.yml",
    "backend/app.py",
    "backend/runtime_preflight.py",
    "backend/runtime_plan.py",
    "backend/requirements-bundle.lock",
)


@pytest.fixture
def snapshot(tmp_path):
    for name in AUDITED_PATHS:
        destination = tmp_path / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / name, destination)
    return tmp_path


def test_current_source_has_all_release_boundaries(snapshot):
    result = gate.check_release_boundaries(snapshot)
    assert result["result"] == "pass", result["checks"]
    assert len(result["checks"]) == 8
    assert "explicit_merge_authorization" in result["still_requires"]
    assert "separate_gpu_validation_in_M4" in result["still_requires"]


@pytest.mark.parametrize(
    ("name", "old", "new", "failed_check"),
    [
        (
            "src-tauri/tauri.conf.json",
            '"active": false', '"active": true',
            "default_build_unbundled_with_no_test_capabilities",
        ),
        (
            "src-tauri/Cargo.toml",
            "default = []", 'default = ["e2e-webdriver"]',
            "release_rust_features_exclude_http_webdriver",
        ),
        (
            "src-tauri/tauri.backend-qa.conf.json",
            '"installerHooks": "nsis/preserve-data.nsh"',
            '"installerHooks": "nsis/unsafe.nsh"',
            "test_bundle_only_readonly_backend_and_uninstall_preservation",
        ),
        (
            "src-tauri/tauri.downgrade-guard-qa.conf.json",
            '"allowDowngrades": false',
            '"allowDowngrades": true',
            "version_downgrade_and_failure_overlays_isolated",
        ),
        (
            "backend/runtime_plan.py",
            '"gpu_probe_authorized": False',
            '"gpu_probe_authorized": True',
            "packaged_api_authenticated_and_not_inference_ready",
        ),
        (
            "backend/requirements-bundle.lock",
            "fastapi==", "torch==",
            "frozen_api_lock_excludes_inference_dependencies",
        ),
        (
            "scripts/windows-installed-backend-qa.ps1",
            "installed_qa: installed_gui_restart_click_reconnected_and_no_orphans",
            "installed_qa: restart_test_silently_skipped",
            "installed_windows_qa_retains_all_m3_regression_assertions",
        ),
        (
            ".github/workflows/windows-backend-bundle-qa.yml",
            "windows-installed-backend-qa.ps1 -VerifyTwoVersionUpgrade",
            "windows-installed-backend-qa.ps1 -StaticOnly",
            "hosted_windows_workflow_runs_installer_tests_without_publishing",
        ),
    ],
)
def test_unsafe_release_change_must_fail(snapshot, name, old, new, failed_check):
    file = snapshot / name
    original = file.read_text(encoding="utf-8")
    assert old in original
    file.write_text(original.replace(old, new, 1), encoding="utf-8")
    result = gate.check_release_boundaries(snapshot)
    assert result["result"] == "fail"
    assert {"name": failed_check, "result": "fail"} in result["checks"]


def test_missing_file_fails_closed(snapshot):
    (snapshot / "src-tauri/tauri.conf.json").unlink()
    assert gate.check_release_boundaries(snapshot)["result"] == "fail"

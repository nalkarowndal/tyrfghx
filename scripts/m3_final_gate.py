"""M3-Final static gate: fail closed if native release-safety boundaries drift.

Only reads checked-in repository source/config files. Does NOT invoke apps,
GPU, installers, subprocesses, network calls, or user-owned model files.
It is *not* a substitute for real Windows E2E or PR review/merge approval.
"""
from __future__ import annotations

import json
import re
from pathlib import Path


def check_release_boundaries(root: Path) -> dict:
    """Return stable machine-readable static checks. No external side effects."""
    checks: list[dict[str, str]] = []

    def report(name: str, passed: bool) -> None:
        checks.append({"name": name, "result": "pass" if passed else "fail"})

    def read_text(name: str) -> str:
        try:
            return (root / name).read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return ""

    def read_json(name: str) -> dict:
        try:
            value = json.loads(read_text(name))
            return value if isinstance(value, dict) else {}
        except (ValueError, TypeError):
            return {}

    def path(obj: dict, *keys: str):
        for key in keys:
            if not isinstance(obj, dict):
                return None
            obj = obj.get(key)
        return obj

    standard = read_json("src-tauri/tauri.conf.json")
    backend = read_json("src-tauri/tauri.backend-qa.conf.json")
    newer = read_json("src-tauri/tauri.upgrade-qa.conf.json")
    downgrade = read_json("src-tauri/tauri.downgrade-guard-qa.conf.json")
    fault = read_json("src-tauri/tauri.preinstall-fault-qa.conf.json")
    cargo = read_text("src-tauri/Cargo.toml")
    hook = read_text("src-tauri/nsis/preserve-data.nsh")
    fault_hook = read_text("src-tauri/nsis/m3-44-preinstall-fault.nsh")
    qa = read_text("scripts/windows-installed-backend-qa.ps1")
    real_windows_workflow = read_text(".github/workflows/windows-backend-bundle-qa.yml")
    read_only_api = read_text("backend/app.py")
    read_only_runtime = read_text("backend/runtime_preflight.py")
    isolated_runtime = read_text("backend/runtime_plan.py")
    requirements = read_text("backend/requirements-bundle.lock")

    report(
        "default_build_unbundled_with_no_test_capabilities",
        path(standard, "bundle", "active") is False
        and path(standard, "app", "security", "capabilities") == ["default"],
    )
    report(
        "release_rust_features_exclude_http_webdriver",
        bool(re.search(r"(?m)^default\s*=\s*\[\s*\]\s*$", cargo))
        and bool(re.search(r"(?m)^e2e-webdriver\s*=\s*\[", cargo))
        and bool(re.search(r"(?m)^tauri-plugin-wdio-webdriver\s*=\s*\{[^\n]*optional\s*=\s*true", cargo)),
    )
    report(
        "test_bundle_only_readonly_backend_and_uninstall_preservation",
        path(backend, "build", "features") == ["bundled-backend"]
        and path(backend, "bundle", "windows", "nsis", "installMode") == "currentUser"
        and path(backend, "bundle", "windows", "nsis", "installerHooks") == "nsis/preserve-data.nsh"
        and path(backend, "bundle", "resources") == {"backend-dist/aiimage-backend/": "backend/"}
        and "NSIS_HOOK_PREUNINSTALL" in hook
        and "StrCpy $DeleteAppDataCheckboxState 0" in hook,
    )
    report(
        "version_downgrade_and_failure_overlays_isolated",
        newer == {"version": "0.1.1"}
        and downgrade == {"bundle": {"windows": {"allowDowngrades": False}}}
        and fault == {"bundle": {"windows": {"nsis": {"installerHooks": "nsis/m3-44-preinstall-fault.nsh"}}}}
        and "!macro NSIS_HOOK_PREINSTALL" in fault_hook
        and 'AIIMAGE_M3_44_ABORT_PREINSTALL' in fault_hook
        and "SetErrorLevel 83" in fault_hook
        and "Quit" in fault_hook
        and "preserve-data.nsh" in fault_hook,
    )
    report(
        "packaged_api_authenticated_and_not_inference_ready",
        'secrets.compare_digest' in read_only_api
        and 'request.headers.get("authorization"' in read_only_api
        and 'request.client.host != "127.0.0.1"' in read_only_api
        and '"origin" in request.headers' in read_only_api
        and '"status": "unavailable"' in read_only_api
        and '"readiness": "not_verified"' in read_only_runtime
        and '"gpu_accessed": False' in read_only_runtime
        and '"models_opened": False' in read_only_runtime
        and '"inference_runtime_connection": "not_connected"' in isolated_runtime
        and '"automated_package_installation": False' in isolated_runtime
        and '"gpu_probe_authorized": False' in isolated_runtime,
    )
    report(
        "frozen_api_lock_excludes_inference_dependencies",
        bool(requirements.strip())
        and not any(
            re.match(r"(?i)^(torch|diffusers|transformers|accelerate|nvidia-[a-z0-9-]+|cuda[\w-]*)\s*(==|>=|<=|~=)", line.strip())
            for line in requirements.splitlines()
        ),
    )
    markers = (
        "same_version_update_mode_repair_preserved_app_backend_models_and_outputs",
        "two_version_0_1_0_to_0_1_1_upgrade_preserved_backend_models_and_outputs",
        "older_0_1_0_downgrade_rejected_0_1_1_payload_and_data_unchanged",
        "preinstall_failure_preserved_current_version_backend_and_data",
        "preinstall_failure_followed_by_clean_retry_and_preservation",
        "installed_gui_restart_click_reconnected_and_no_orphans",
        "interactive_uninstall_with_delete_checkbox_preserved_models_and_outputs",
    )
    report(
        "installed_windows_qa_retains_all_m3_regression_assertions",
        all("installed_qa: " + marker in qa for marker in markers),
    )
    report(
        "hosted_windows_workflow_runs_installer_tests_without_publishing",
        "windows-installed-backend-qa.ps1 -VerifyTwoVersionUpgrade" in real_windows_workflow
        and "cargo tree" in real_windows_workflow
        and not bool(re.search(r"(?i)\bactions/upload-artifact\b|\bgh release (create|upload)\b", real_windows_workflow)),
    )

    success = all(c["result"] == "pass" for c in checks)
    return {
        "schema_version": 1,
        "milestone": "M3-Final",
        "gate": "static_release_boundary_audit_only",
        "result": "pass" if success else "fail",
        "checks": checks,
        "still_requires": [
            "verified_latest_head_ci",
            "verified_real_windows_packaged_installer_qa",
            "review_of_all_stacked_pull_requests",
            "explicit_merge_authorization",
            "separate_gpu_validation_in_M4",
        ],
    }


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    outcome = check_release_boundaries(root)
    print(json.dumps(outcome, ensure_ascii=False, indent=2))
    return 0 if outcome["result"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

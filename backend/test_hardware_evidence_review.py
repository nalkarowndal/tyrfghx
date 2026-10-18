"""M3-19: mock-only offline JSON report review; no NVIDIA or CUDA usage."""
from __future__ import annotations

import hashlib
import json

import pytest

import hardware_evidence_review as qa


def acceptance(verified: bool = True):
    return {
        "schema_version": 1, "milestone": "M3-10",
        "status": "generated_png_decoded" if verified else "gpu_probe_only",
        "generation": {
            "status": "saved_png_verified",
            "file_name": "aiimage-" + "a" * 32 + ".png",
            "png_sha256": "f" * 64,
            "width": 512, "height": 512, "size_bytes": 1728,
        } if verified else {"status": "not_run"},
        "warnings": ["synthetic sample only"],
        "manual_checks": {"process_tree_cleanup": "passed"},  # Ignore false promises.
    }


def gpu_report(status: str = "system_memory_observed"):
    return {
        "schema_version": 1,
        "milestone": "M3-18",
        "status": status,
        "gpu_index": 0,
        "sample_count": 3 if status == "system_memory_observed" else 2,
        "requested_sample_count": 3,
        "sample_interval_seconds": 2,
        "evidence_scope": "nvidia_smi_system_level_snapshot_series_not_app_specific",
        "observed": {
            "total_mib_at_start": 8192,
            "used_mib_at_start": 1024,
            "used_mib_peak_sampled": 4096,
            "used_mib_at_end": 1280,
            "free_mib_at_end": 6912,
            "peak_minus_start_mib": 3072,
            "end_minus_start_mib": 256,
        },
        "manual_checks": {"app_process_cleanup": "passed"},
    }


def test_complete_reports_are_only_ready_for_manual_review_not_hardware_qualified():
    report = qa.summarize_hardware_evidence(acceptance(), gpu_report(), "a" * 64, "b" * 64)
    assert report["status"] == "evidence_available_for_manual_review"
    assert report["automatic_hardware_acceptance"] == "not_performed"
    assert set(report["manual_checks"].values()) == {"not_tested"}
    assert report["sources"]["generation"]["png_claimed_by_source"] is True
    assert report["sources"]["system_gpu_memory"]["observed_system_mib"]["used_peak_sampled"] == 4096
    assert "qualified" not in report["status"]
    assert "private" not in json.dumps(report)


@pytest.mark.parametrize("generated, memory", [
    (False, "system_memory_observed"),
    (True, "sampling_interrupted"),
    (False, "sampling_interrupted"),
])
def test_incomplete_inputs_do_not_become_automatic_success(generated, memory):
    result = qa.summarize_hardware_evidence(
        acceptance(generated), gpu_report(memory), "1" * 64, "2" * 64,
    )
    assert result["status"] == "incomplete_evidence"
    assert set(result["manual_checks"].values()) == {"not_tested"}


def test_generated_status_requires_valid_png_claim_metadata():
    fake = acceptance()
    fake["generation"]["file_name"] = "../C:/Users/private.png"
    with pytest.raises(ValueError, match="acceptance_png_claim_invalid"):
        qa.summarize_hardware_evidence(fake, gpu_report(), "a" * 64, "b" * 64)


def test_refuses_contradictory_generation_status():
    fake = acceptance()
    fake["generation"]["status"] = "not_run"
    with pytest.raises(ValueError, match="acceptance_status_inconsistent"):
        qa.summarize_hardware_evidence(fake, gpu_report(), "a" * 64, "b" * 64)


@pytest.mark.parametrize("field,new_value", [
    ("used_mib_peak_sampled", 100),
    ("free_mib_at_end", 10000),
    ("end_minus_start_mib", 99999),
    ("total_mib_at_start", True),
    ("used_mib_at_end", -1),
])
def test_rejects_inconsistent_nvidia_memory_report(field, new_value):
    sample = gpu_report()
    sample["observed"][field] = new_value
    with pytest.raises(ValueError):
        qa.summarize_hardware_evidence(acceptance(), sample, "a" * 64, "b" * 64)


def test_rejects_sample_count_false_claim():
    sample = gpu_report()
    sample["sample_count"] = 1
    with pytest.raises(ValueError, match="vram_samples_inconsistent"):
        qa.summarize_hardware_evidence(acceptance(), sample, "a" * 64, "b" * 64)


def test_rejects_unknown_evidence_sources_and_wrong_versions():
    gen = acceptance()
    gen["milestone"] = "untrusted-script"
    with pytest.raises(ValueError, match="acceptance_schema_invalid"):
        qa.summarize_hardware_evidence(gen, gpu_report(), "a" * 64, "b" * 64)
    mem = gpu_report()
    mem["schema_version"] = 999
    with pytest.raises(ValueError, match="vram_schema_invalid"):
        qa.summarize_hardware_evidence(acceptance(), mem, "a" * 64, "b" * 64)


@pytest.mark.parametrize("text", [
    '{"schema_version":1,"schema_version":1}',
    '{"v": NaN}',
    '{"v": Infinity}',
    '{"v":-Infinity}',
    "\ufeff" + '{"v":1}',
    "[1,2,3]",
])
def test_json_reader_rejects_duplicate_keys_nonstandard_values_and_arrays(tmp_path, text):
    file = tmp_path / "private.json"
    file.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError):
        qa.load_local_evidence(file)


def test_rejects_oversized_and_symlink_evidence_files(tmp_path):
    huge = tmp_path / "huge.json"
    huge.write_bytes(b"x" * (qa.MAX_INPUT_BYTES + 1))
    with pytest.raises(ValueError, match="evidence_size_invalid"):
        qa.load_local_evidence(huge)
    valid = tmp_path / "valid.json"
    valid.write_text("{}", encoding="utf-8")
    symlink = tmp_path / "link.json"
    try:
        symlink.symlink_to(valid)
    except (OSError, NotImplementedError):
        pytest.skip("Current Windows permissions disallow symlink creation")
    with pytest.raises(ValueError, match="unsafe_evidence_file"):
        qa.load_local_evidence(symlink)


def test_hash_tracks_exact_input_bytes_without_leaking_path(tmp_path):
    private = tmp_path / "C_Users_private_model_prompts.json"
    raw = json.dumps(acceptance()).encode("utf-8")
    private.write_bytes(raw)
    obj, digest = qa.load_local_evidence(private)
    assert obj["status"] == "generated_png_decoded"
    assert digest == hashlib.sha256(raw).hexdigest()
    assert "private" not in digest


def test_cli_requires_explicit_review_before_touching_source_files(monkeypatch):
    def forbidden(*args):
        raise AssertionError("Must not inspect local file without explicit consent")
    monkeypatch.setattr(qa, "load_local_evidence", forbidden)
    with pytest.raises(SystemExit) as err:
        qa.main(["--generation-json", "private.json", "--gpu-memory-json", "secret.json"])
    assert err.value.code == 2


def test_cli_returns_sanitized_report_without_echoing_raw_source_text(tmp_path, capsys):
    generation_file = tmp_path / "C_Users_personal_prompt.json"
    gpu_file = tmp_path / "User_name_gpu.json"
    generation_file.write_text(json.dumps(acceptance()), encoding="utf-8")
    gpu_file.write_text(json.dumps(gpu_report()), encoding="utf-8")
    result = qa.main([
        "--generation-json", str(generation_file),
        "--gpu-memory-json", str(gpu_file),
        "--confirm-review",
    ])
    assert result == 0
    published = capsys.readouterr().out
    obj = json.loads(published)
    assert obj["status"] == "evidence_available_for_manual_review"
    assert "C_Users_personal_prompt" not in published
    assert "User_name_gpu" not in published
    assert "synthetic sample only" not in published
    assert set(obj["manual_checks"].values()) == {"not_tested"}


def test_cli_missing_file_returns_only_allowlisted_safe_error(tmp_path, capsys):
    exit_code = qa.main([
        "--generation-json", str(tmp_path / "C_Users_abc_secret.json"),
        "--gpu-memory-json", "missing.json",
        "--confirm-review",
    ])
    assert exit_code == 2
    published = capsys.readouterr().out
    assert "C_Users_abc" not in published
    assert json.loads(published)["status"] == "invalid_evidence"

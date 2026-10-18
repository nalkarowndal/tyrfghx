"""M3-20: real byte-level stdlib PNG fixtures, no CUDA or Pillow required."""
import hashlib
import json
import struct
import zlib

import pytest

from independent_png_qa import _decode_png_scanlines, verify_local_png
from hardware_evidence_review import main as review_main


NAME = "aiimage-" + "a" * 32 + ".png"


def chunk(kind: bytes, payload: bytes) -> bytes:
    return (struct.pack(">I", len(payload)) + kind + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xffffffff))


def make_png(width=8, height=7, *, rgba=False, filters=True) -> bytes:
    channels = 4 if rgba else 3
    pitch = width * channels
    rows = b"".join(
        bytes([row % 5 if filters else 0]) +
        bytes((i * 17 + row * 13) % 256 for i in range(pitch))
        for row in range(height)
    )
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6 if rgba else 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(rows))
            + chunk(b"IEND", b""))


def claim(png: bytes, width=8, height=7):
    return {
        "file_name": NAME,
        "png_sha256": hashlib.sha256(png).hexdigest(),
        "width": width, "height": height, "size_bytes": len(png),
    }


def write_png(tmp_path, png):
    output_root = tmp_path / "output"
    output_root.mkdir()
    (output_root / NAME).write_bytes(png)
    return output_root


def test_decode_rgb_and_rgba_filters_from_genuine_png_bytes(tmp_path):
    for rgba in (False, True):
        png = make_png(rgba=rgba)
        assert _decode_png_scanlines(png, 8, 7) == (8, 7)
        if rgba:
            out = write_png(tmp_path, png)
            evidence = verify_local_png(out, claim(png))
            assert evidence["verification"] == "png_crc_zlib_filters_sha256_and_dimensions_verified"
            assert evidence["decoded_width"] == 8
            assert evidence["visual_image_quality"] == "not_tested"
            assert evidence["model_execution_attribution"] == "not_tested"
            assert "private" not in json.dumps(evidence)


def test_png_report_digest_mismatch_is_not_independent_success(tmp_path):
    png = make_png()
    out = write_png(tmp_path, png)
    expected = claim(png)
    expected["png_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="png_sha256_mismatch"):
        verify_local_png(out, expected)


@pytest.mark.parametrize("mutator", [
    lambda data: data[:-5],
    lambda data: data + b"hidden trailing payload",
    lambda data: data[:20] + bytes([data[20] ^ 1]) + data[21:],
    lambda data: data.replace(b"IDAT", b"abCD", 1),
])
def test_broken_chunks_truncation_crc_and_trailing_data_are_rejected(mutator):
    png = mutator(make_png())
    with pytest.raises(ValueError, match="png_content_invalid"):
        _decode_png_scanlines(png, 8, 7)


def test_png_dimensions_and_color_type_are_not_trusted(tmp_path):
    rgb = make_png()
    out = write_png(tmp_path, rgb)
    expected = claim(rgb)
    expected["width"] = 9
    with pytest.raises(ValueError, match="png_content_invalid"):
        verify_local_png(out, expected)
    # An attacker may change a supported RGB image's IHDR to indexed color.
    ihdr = struct.pack(">IIBBBBB", 8, 7, 8, 3, 0, 0, 0)
    bad = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
           + rgb[8 + 25:])
    with pytest.raises(ValueError, match="png_content_invalid"):
        _decode_png_scanlines(bad, 8, 7)


def test_rejects_symlinked_png(tmp_path):
    actual = tmp_path / "actual.png"
    png = make_png()
    actual.write_bytes(png)
    out = tmp_path / "output"
    out.mkdir()
    try:
        (out / NAME).symlink_to(actual)
    except (OSError, NotImplementedError):
        pytest.skip("Windows symlink permissions not granted")
    with pytest.raises(ValueError, match="png_file_missing_or_unsafe"):
        verify_local_png(out, claim(png))


def test_valid_png_is_not_trusted_if_report_contains_path_traversal(tmp_path):
    png = make_png()
    out = write_png(tmp_path, png)
    bad = claim(png)
    bad["file_name"] = "../../private.png"
    with pytest.raises(ValueError, match="png_claim_invalid"):
        verify_local_png(out, bad)


def make_reports(tmp_path):
    png = make_png()
    root = write_png(tmp_path, png)
    gen = {
        "schema_version": 1, "milestone": "M3-10",
        "status": "generated_png_decoded",
        "generation": {"status": "saved_png_verified", **claim(png)},
        "manual_checks": {"visual_prompt_adherence": "passed"},
    }
    mem = {
        "schema_version": 1, "milestone": "M3-18",
        "status": "system_memory_observed",
        "gpu_index": 0, "sample_count": 2, "requested_sample_count": 2,
        "sample_interval_seconds": 1,
        "evidence_scope": "nvidia_smi_system_level_snapshot_series_not_app_specific",
        "observed": {
            "total_mib_at_start": 8192, "used_mib_at_start": 1000,
            "used_mib_peak_sampled": 4000, "used_mib_at_end": 1300,
            "free_mib_at_end": 6892, "peak_minus_start_mib": 3000,
            "end_minus_start_mib": 300,
        },
    }
    g = tmp_path / "gen.json"
    m = tmp_path / "mem.json"
    g.write_text(json.dumps(gen), encoding="utf-8")
    m.write_text(json.dumps(mem), encoding="utf-8")
    return root, g, m


def test_explicit_optional_png_review_reads_local_bytes_and_keeps_manual_checks(tmp_path, capsys):
    root, g, m = make_reports(tmp_path)
    assert review_main([
        "--generation-json", str(g), "--gpu-memory-json", str(m),
        "--output-root", str(root), "--confirm-review",
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "evidence_available_for_manual_review"
    assert result["independent_png"]["verification"] == "png_crc_zlib_filters_sha256_and_dimensions_verified"
    assert set(result["manual_checks"].values()) == {"not_tested"}
    assert result["automatic_hardware_acceptance"] == "not_performed"


def test_png_review_is_opt_in_and_unchanged_report_still_accepted(tmp_path, capsys):
    _, g, m = make_reports(tmp_path)
    assert review_main([
        "--generation-json", str(g), "--gpu-memory-json", str(m), "--confirm-review"
    ]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["independent_png"] == {"verification": "not_requested"}


def test_corrupt_file_is_sanitized_failure_without_path_leak(tmp_path, capsys):
    root, g, m = make_reports(tmp_path)
    target = root / NAME
    target.write_bytes(b"not a real PNG")
    assert review_main([
        "--generation-json", str(g), "--gpu-memory-json", str(m),
        "--output-root", str(root), "--confirm-review",
    ]) == 2
    response = json.loads(capsys.readouterr().out)
    assert response["status"] == "invalid_evidence"
    assert response["error_code"] == "png_size_mismatch"
    assert str(root) not in json.dumps(response)
    assert "passed" not in json.dumps(response)


def test_metadata_only_report_cannot_request_png_verification(tmp_path, capsys):
    root, g, m = make_reports(tmp_path)
    src = json.loads(g.read_text())
    src["status"] = "gpu_probe_only"
    src["generation"] = {"status": "not_run"}
    g.write_text(json.dumps(src))
    assert review_main([
        "--generation-json", str(g), "--gpu-memory-json", str(m),
        "--output-root", str(root), "--confirm-review",
    ]) == 2
    response = json.loads(capsys.readouterr().out)
    assert response["error_code"] == "png_source_not_verified"

"""M4-1f: safe in-memory synthetic wheel structure regression cases."""
from __future__ import annotations

import base64
import csv
import hashlib
import io
import stat
import warnings
import zipfile
from pathlib import Path

import pytest

from synthetic_wheel_archive_preview import (
    MAX_ARCHIVE_BYTES, SyntheticWheelReject, inspect_synthetic_wheel,
)

NAME = "torch-2.6.0+cu124-cp312-cp312-win_amd64.whl"
PREFIX = "torch-2.6.0+cu124.dist-info/"
WHEEL = PREFIX + "WHEEL"
METADATA = PREFIX + "METADATA"
RECORD = PREFIX + "RECORD"


def digest(data):
    return base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode("ascii")


def fixture_wheel(*, entries=None, record_hash_valid=True, compression=zipfile.ZIP_STORED):
    if entries is None:
        entries = [
            ("torch/__init__.py", b"x = 1\n"),
            (WHEEL, b"Wheel-Version: 1.0\nRoot-Is-Purelib: false\nTag: cp312-cp312-win_amd64\n"),
            (METADATA, b"Metadata-Version: 2.1\nName: torch\nVersion: 2.6.0+cu124\n"),
        ]
    rows = []
    for path, data in entries:
        rows.append([path, "sha256=" + digest(data), str(len(data))])
    rows.append([RECORD, "", ""])
    if not record_hash_valid:
        rows[0][1] = "sha256=" + "a" * 43
    buf = io.StringIO(newline="")
    csv.writer(buf, lineterminator="\n").writerows(rows)
    payloads = entries + [(RECORD, buf.getvalue().encode("utf-8"))]
    memory = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(memory, "w", compression=compression) as writer:
            for path, data in payloads:
                writer.writestr(path, data)
    return memory.getvalue()


def accept(payload):
    result = inspect_synthetic_wheel(payload, NAME)
    assert result["status"] == "synthetic_archive_structure_verified"
    assert result["checked_entries"] == 4
    assert result["record_hashes_match"] is True
    assert result["sample_target_tag_matched"] is True
    for flag in ("production_wheel_compatible", "archive_parser_ambiguity_excluded",
                 "source_provenance_verified", "signature_verified",
                 "production_install_authorized", "downloads_performed",
                 "packages_installed", "gpu_accessed"):
        assert result[flag] is False


def deny(payload, filename=NAME):
    with pytest.raises(SyntheticWheelReject, match="^synthetic_archive_rejected$"):
        inspect_synthetic_wheel(payload, filename)


def test_small_mock_archive_has_valid_metadata_but_never_installs():
    accept(fixture_wheel())


def test_compressed_mock_archive_is_read_only():
    accept(fixture_wheel(compression=zipfile.ZIP_DEFLATED))


@pytest.mark.parametrize("invalid", [
    b"", b"not-a-zip", b"\xff", b"{}", None, "bad", bytearray(b"x"),
])
def test_untrusted_non_zip_bytes_denied(invalid):
    deny(invalid)


def test_truncated_or_oversized_zip_denied():
    small = fixture_wheel()
    deny(small[:-22])
    # Construct large input *inside* the test; do not create a long
    # parametrized pytest ID that violates Windows environment length limits.
    deny(b"x" * (MAX_ARCHIVE_BYTES + 1))


@pytest.mark.parametrize("filename", [
    "../torch.whl", "C:\\evil.whl", "torch-2.6.0+cu124-cp311-cp311-win_amd64.whl",
    "torch-2.6.0+cu124-cp312-cp312-linux_x86_64.whl",
    "torch-2.6.0+cu124-cp312-cp312-win_amd64.whl\n",
    "other-2.6.0+cu124-cp312-cp312-win_amd64.whl",
])
def test_only_narrow_declared_filename_sample_tags_accepted(filename):
    deny(fixture_wheel(), filename)


def test_missing_wheel_metadata_and_wrong_record_hash_denied():
    deny(fixture_wheel(entries=[
        ("torch/__init__.py", b"x = 1"),
        (METADATA, b"Metadata-Version: 2.1\nName: torch\nVersion: 2.6.0+cu124\n"),
    ]))
    deny(fixture_wheel(record_hash_valid=False))


@pytest.mark.parametrize("target,data", [
    (WHEEL, b"Wheel-Version: 2.0\nRoot-Is-Purelib: true\nTag: cp312-cp312-win_amd64\n"),
    (WHEEL, b"Wheel-Version: 1.0\nRoot-Is-Purelib: false\nTag: cp311-cp311-win_amd64\n"),
    (METADATA, b"Metadata-Version: 2.1\nName: evil\nVersion: 2.6.0+cu124\n"),
    (METADATA, b"Metadata-Version: 2.1\nName: torch\nVersion: 0.0.1\n"),
])
def test_wrong_metadata_or_wheel_tags_fail(target, data):
    default = [
        ("torch/__init__.py", b"x = 1"),
        (WHEEL, b"Wheel-Version: 1.0\nRoot-Is-Purelib: false\nTag: cp312-cp312-win_amd64\n"),
        (METADATA, b"Metadata-Version: 2.1\nName: torch\nVersion: 2.6.0+cu124\n"),
    ]
    deny(fixture_wheel(entries=[(p, data if p == target else b) for p, b in default]))


@pytest.mark.parametrize("attack", [
    "../outside.py", "/etc/passwd", "C:/Windows/win.ini",
    "torch\\..\\evil.py", "torch/../evil.py", "torch//evil.py",
    "torch/tail. ", "torch/file.py\nInjected",
    "torch/CON.txt", "torch/COM1.py", "torch/한글.py",
])
def test_unsafe_zip_member_names_rejected(attack):
    deny(fixture_wheel(entries=[
        ("torch/__init__.py", b"x = 1"),
        (WHEEL, b"Wheel-Version: 1.0\nRoot-Is-Purelib: false\nTag: cp312-cp312-win_amd64\n"),
        (METADATA, b"Metadata-Version: 2.1\nName: torch\nVersion: 2.6.0+cu124\n"),
        (attack, b"attack"),
    ]))


def test_duplicate_central_directory_entry_rejected():
    deny(fixture_wheel(entries=[
        ("torch/__init__.py", b"x = 1"),
        (WHEEL, b"Wheel-Version: 1.0\nRoot-Is-Purelib: false\nTag: cp312-cp312-win_amd64\n"),
        (METADATA, b"Metadata-Version: 2.1\nName: torch\nVersion: 2.6.0+cu124\n"),
        ("torch/__init__.py", b"overridden"),
    ]))


def test_case_folded_duplicate_archive_members_rejected():
    deny(fixture_wheel(entries=[
        ("torch/__init__.py", b"x=1"),
        ("TORCH/__init__.py", b"x=2"),
        (WHEEL, b"Wheel-Version: 1.0\\nRoot-Is-Purelib: false\\nTag: cp312-cp312-win_amd64\\n"),
        (METADATA, b"Metadata-Version: 2.1\\nName: torch\\nVersion: 2.6.0+cu124\\n"),
    ]))


def test_existing_synthetic_sha_gate_then_archive_structure_check(tmp_path):
    import json
    from inference_wheel_fixture_integrity import (
        FIXTURE_MARKER, MARKER_BYTES, verify_synthetic_fixture,
    )
    root = tmp_path / "qa-fixture"
    root.mkdir()
    payload = fixture_wheel()
    (root / FIXTURE_MARKER).write_bytes(MARKER_BYTES)
    (root / NAME).write_bytes(payload)
    record = json.dumps({
        "schema_version": 1, "platform": "windows_x86_64",
        "python_version": "3.12",
        "destination_kind": "user_selected_private_venv",
        "wheels": [{
            "package": "torch", "version": "2.6.0+cu124",
            "filename": NAME, "sha256": hashlib.sha256(payload).hexdigest(),
            "declared_bytes": len(payload),
        }],
    }).encode("utf-8")
    assert verify_synthetic_fixture(record, root)["status"] == "synthetic_fixture_verified"
    assert inspect_synthetic_wheel(payload, NAME)["status"] == "synthetic_archive_structure_verified"
    assert (root / NAME).read_bytes() == payload


def test_synthetic_zip_bomb_rejected_before_decompression():
    entries = [
        ("torch/__init__.py", b"x" * 500_000),
        (WHEEL, b"Wheel-Version: 1.0\nRoot-Is-Purelib: false\nTag: cp312-cp312-win_amd64\n"),
        (METADATA, b"Metadata-Version: 2.1\nName: torch\nVersion: 2.6.0+cu124\n"),
    ]
    deny(fixture_wheel(entries=entries, compression=zipfile.ZIP_DEFLATED))


def test_symlink_mode_entry_denied_without_extraction():
    archive = io.BytesIO()
    file = zipfile.ZipInfo("torch/link")
    file.create_system = 3
    file.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr(file, b"../outside")
    deny(archive.getvalue())


def test_cancel_does_not_parse_untrusted_blob():
    assert inspect_synthetic_wheel(b"bad-archive", NAME, cancelled=True) == {
        "status": "cancelled", "side_effects_performed": False
    }
    with pytest.raises(SyntheticWheelReject, match="^invalid_preview_options$"):
        inspect_synthetic_wheel(fixture_wheel(), NAME, cancelled=1)


def test_no_filesystem_or_inference_process_entry_points():
    from app import create_app
    assert not any("wheel" in name or "install" in name
                   for name in create_app().openapi()["paths"])
    source = (Path(__file__).parent / "synthetic_wheel_archive_preview.py").read_text("utf-8")
    for denied in ("import torch", "import diffusers", "import subprocess",
                   "import socket", "import requests", "Popen(", "extractall(", "pip install",
                   "os.system(", "open("):
        assert denied not in source
    assert inspect_synthetic_wheel(fixture_wheel(), NAME)["production_install_authorized"] is False

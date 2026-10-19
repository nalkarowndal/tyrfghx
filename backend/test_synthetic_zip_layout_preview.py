"""M4-1g: hostile ZIP framing tests for tiny synthetic Wheel data ONLY."""
from __future__ import annotations

import io
import struct
import zipfile
from pathlib import Path

import pytest

from synthetic_zip_layout_preview import (
    SyntheticLayoutReject, inspect_synthetic_layout,
)
from synthetic_wheel_archive_preview import (
    SyntheticWheelReject, inspect_synthetic_wheel,
)
from test_synthetic_wheel_archive_preview import NAME, fixture_wheel

CENTRAL = b"PK\x01\x02"
EOCD = b"PK\x05\x06"


def bad_layout(data):
    with pytest.raises(SyntheticLayoutReject, match="^synthetic_zip_layout_rejected$"):
        inspect_synthetic_layout(data)
    with pytest.raises(SyntheticWheelReject, match="^synthetic_archive_rejected$"):
        inspect_synthetic_wheel(data, NAME)


def test_stored_and_deflated_fixtures_have_exact_local_central_agreement():
    for compression in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
        sample = fixture_wheel(compression=compression)
        layout = inspect_synthetic_layout(sample)
        assert layout["status"] == "synthetic_layout_consistent"
        assert layout["checked_members"] == 4
        assert layout["local_central_headers_match"] is True
        assert layout["single_terminal_eocd"] is True
        assert layout["installation_authorized"] is False
        wheel = inspect_synthetic_wheel(sample, NAME)
        assert wheel["synthetic_local_central_framing_match"] is True
        assert wheel["archive_parser_ambiguity_excluded"] is False


def test_rejects_local_filename_different_from_central():
    sample = bytearray(fixture_wheel())
    # Local header is 30 bytes; change the first local filename only.
    assert sample[:4] == b"PK\x03\x04"
    sample[30] ^= 0x20
    bad_layout(bytes(sample))


def test_rejects_central_filename_different_from_local():
    sample = bytearray(fixture_wheel())
    central = sample.index(CENTRAL)
    sample[central + 46] ^= 0x20
    bad_layout(bytes(sample))


def test_rejects_local_crc_or_size_mismatch():
    sample = bytearray(fixture_wheel())
    sample[14] ^= 0x01  # local CRC32 begins at byte 14
    bad_layout(bytes(sample))
    sample = bytearray(fixture_wheel())
    sample[18] ^= 0x01  # local compressed size begins at byte 18
    bad_layout(bytes(sample))


def test_rejects_local_and_central_extra_fields():
    sample = bytearray(fixture_wheel())
    sample[28] = 1  # local extra length (originally zero)
    bad_layout(bytes(sample))
    sample = bytearray(fixture_wheel())
    central = sample.index(CENTRAL)
    sample[central + 30] = 1  # central extra length (originally zero)
    bad_layout(bytes(sample))


def test_rejects_prefix_suffix_overlay_or_multiple_eocd():
    payload = fixture_wheel()
    bad_layout(b"PREFIX" + payload)
    bad_layout(payload + b"TRAIL")
    bad_layout(payload + payload[-22:])
    bad_layout(payload[:-22] + payload[-22:] + b"EVIL")


def test_rejects_wrong_eocd_offsets_and_disk_splits():
    sample = bytearray(fixture_wheel())
    struct.pack_into("<L", sample, len(sample) - 22 + 16, 0)
    bad_layout(bytes(sample))
    sample = bytearray(fixture_wheel())
    struct.pack_into("<H", sample, len(sample) - 22 + 4, 1)
    bad_layout(bytes(sample))


def test_rejects_archive_comment_and_unsupported_descriptor_flags():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("example.txt", b"x")
        archive.comment = b"comment"
    bad_layout(buffer.getvalue())
    sample = bytearray(fixture_wheel())
    # Changing any local flags is disallowed even if the central version
    # agrees: only classic synthetic ZIP with flags=0 is supported.
    sample[6] = 0x08
    bad_layout(bytes(sample))


def test_rejects_truncated_headers_bad_type_or_zip64_marker():
    sample = fixture_wheel()
    for invalid in (b"", b"no zip", sample[:-1], None, "not-bytes", bytearray(sample)):
        bad_layout(invalid)
    sample = bytearray(fixture_wheel())
    struct.pack_into("<L", sample, len(sample) - 22 + 12, 0xFFFFFFFF)
    bad_layout(bytes(sample))


def test_layout_checker_stays_in_memory_and_no_production_api():
    from app import create_app
    assert not any("wheel" in path or "install" in path for path in create_app().openapi()["paths"])
    source = (Path(__file__).parent / "synthetic_zip_layout_preview.py").read_text("utf-8")
    for forbidden in ("import subprocess", "import torch", "import requests", "import socket",
                      "os.open(", "zipfile.extract", "Popen(", "pip install", "CreateFileW"):
        assert forbidden not in source
    assert inspect_synthetic_layout(fixture_wheel())["files_opened"] is False

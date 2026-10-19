"""M4-1g: strict ZIP framing check for *tiny in-memory synthetic fixtures*.

This deliberately accepts a narrow, unambiguous subset of classic single-disk
ZIP, before the M4-1f zipfile + RECORD preview. It rejects ZIP64, extras,
comments, data descriptors, prepended bytes and trailing data. NOT a
production-safe ZIP parser or authorization to install Python wheels.
"""
from __future__ import annotations

import struct

_EOCD = b"PK\x05\x06"
_CENTRAL = b"PK\x01\x02"
_LOCAL = b"PK\x03\x04"
_MAX_ARCHIVE_BYTES = 1024 * 1024
_MAX_ENTRIES = 32


class SyntheticLayoutReject(ValueError):
    """Fixed safe error, no untrusted byte contents."""


def _deny() -> None:
    raise SyntheticLayoutReject("synthetic_zip_layout_rejected")


def inspect_synthetic_layout(data: bytes) -> dict:
    """Verify central/local agreement and exactly contiguous ZIP framing."""
    if type(data) is not bytes or not 22 <= len(data) <= _MAX_ARCHIVE_BYTES:
        _deny()
    # Synthetic fixtures do not use archive comments. Require one terminal
    # EOCD and reject both prefixes and any appended overlays.
    if data[-22:-18] != _EOCD or data.count(_EOCD) != 1:
        _deny()
    try:
        end = struct.unpack_from("<4s4H2LH", data, len(data) - 22)
        _, disk, cd_disk, on_disk, total, cd_size, cd_start, comment_size = end
        if (disk or cd_disk or on_disk != total or not 3 <= total <= _MAX_ENTRIES
                or comment_size or cd_start == 0
                or cd_start + cd_size != len(data) - 22):
            _deny()
        ptr = cd_start
        central_end = cd_start + cd_size
        offsets = []
        seen = set()
        for _ in range(total):
            if ptr + 46 > central_end:
                _deny()
            row = struct.unpack_from("<4s6H3L5H2L", data, ptr)
            (sig, made, needed, flags, method, clock, day, crc, packed, unpacked,
             name_len, extra_len, comment_len, disk_start, internal, external,
             local_offset) = row
            if (sig != _CENTRAL or flags != 0 or method not in (0, 8)
                    or needed > 20 or disk_start != 0 or extra_len != 0
                    or comment_len != 0 or not 1 <= name_len <= 220
                    or packed > _MAX_ARCHIVE_BYTES or unpacked > 4 * _MAX_ARCHIVE_BYTES):
                _deny()
            next_ptr = ptr + 46 + name_len
            if next_ptr > central_end:
                _deny()
            name = data[ptr + 46:next_ptr]
            if name in seen:
                _deny()
            seen.add(name)
            try:
                name.decode("ascii")
            except UnicodeError:
                _deny()
            if not 0 <= local_offset < cd_start:
                _deny()
            offsets.append((local_offset, name, needed, flags, method, clock,
                            day, crc, packed, unpacked))
            ptr = next_ptr
        if ptr != central_end:
            _deny()

        next_local = 0
        local_names = set()
        for (offset, expected_name, needed, flags, method, clock,
             day, crc, packed, unpacked) in sorted(offsets):
            if offset != next_local or offset + 30 > cd_start:
                _deny()
            lf = struct.unpack_from("<4s5H3L2H", data, offset)
            (sig, v_need, lflags, lmethod, lclock, lday, lcrc, lpacked,
             lunpacked, name_len, extra_len) = lf
            if (sig != _LOCAL or extra_len != 0 or name_len != len(expected_name)
                    or (v_need, lflags, lmethod, lclock, lday, lcrc, lpacked,
                        lunpacked) !=
                       (needed, flags, method, clock, day, crc, packed, unpacked)):
                _deny()
            data_start = offset + 30 + name_len
            end_data = data_start + packed
            name = data[offset + 30:data_start]
            if name != expected_name or name in local_names or end_data > cd_start:
                _deny()
            local_names.add(name)
            next_local = end_data
        if next_local != cd_start or local_names != seen:
            _deny()
    except (struct.error, OverflowError, IndexError):
        _deny()
    return {
        "status": "synthetic_layout_consistent",
        "checked_members": total,
        "local_central_headers_match": True,
        "single_terminal_eocd": True,
        "contiguous_synthetic_records": True,
        "zip64_or_extended_zip_supported": False,
        "real_archive_parser_security_verified": False,
        "installation_authorized": False,
        "files_opened": False,
        "gpu_accessed": False,
    }

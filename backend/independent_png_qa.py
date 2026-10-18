"""M3-20: stdlib-only independent PNG byte/pixel scanline check.

An explicitly selected LOCAL output directory is checked against the M3-10
generation claim. Nothing runs inference or contacts the network. This
validates PNG mechanics and hash, NOT prompt adherence or image aesthetics.
"""
from __future__ import annotations

import hashlib
import re
import struct
import zlib
from pathlib import Path
from typing import Any

MAX_PNG_BYTES = 8 * 1024 * 1024
MAX_SIDE = 1024
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
FILE_NAME = re.compile(r"aiimage-[0-9a-f]{32}\.png\Z")


def _png_error() -> ValueError:
    return ValueError("png_content_invalid")


def _decode_png_scanlines(data: bytes, width: int, height: int) -> tuple[int, int]:
    """Parse and validate all chunks, CRC, bounded zlib and PNG reverse filters.

    Only 8-bit noninterlaced RGB/RGBA files from the known SDXL export
    pipeline are supported. Fail closed on palette, APNG and unknown critical
    chunks. Reconstruction of every scanline proves the filters are usable,
    not that any visual semantics are correct.
    """
    if not (45 <= len(data) <= MAX_PNG_BYTES and data.startswith(PNG_MAGIC)):
        raise _png_error()
    cursor = len(PNG_MAGIC)
    saw_ihdr = saw_idat = saw_iend = False
    idat_closed = False
    channels = 0
    compressed = bytearray()
    chunks = 0
    while cursor < len(data):
        chunks += 1
        if chunks > 16_384 or cursor + 12 > len(data):
            raise _png_error()
        length = struct.unpack_from(">I", data, cursor)[0]
        chunk_kind = data[cursor + 4: cursor + 8]
        start = cursor + 8
        end = start + length
        if end + 4 > len(data) or not all((65 <= b <= 90) or (97 <= b <= 122) for b in chunk_kind):
            raise _png_error()
        payload = data[start:end]
        expected_crc = struct.unpack_from(">I", data, end)[0]
        if zlib.crc32(chunk_kind + payload) & 0xffffffff != expected_crc:
            raise _png_error()
        cursor = end + 4

        if chunks == 1:
            if chunk_kind != b"IHDR" or length != 13:
                raise _png_error()
            w, h, bit_depth, color_type, compression, filter_method, interlace = struct.unpack(
                ">IIBBBBB", payload
            )
            if ((w, h) != (width, height)
                    or not 1 <= w <= MAX_SIDE or not 1 <= h <= MAX_SIDE
                    or bit_depth != 8 or color_type not in (2, 6)
                    or compression != 0 or filter_method != 0 or interlace != 0):
                raise _png_error()
            channels = 3 if color_type == 2 else 4
            saw_ihdr = True
        elif chunk_kind == b"IDAT":
            if not saw_ihdr or idat_closed:
                raise _png_error()
            saw_idat = True
            compressed.extend(payload)
            if len(compressed) > MAX_PNG_BYTES:
                raise _png_error()
        elif chunk_kind == b"IEND":
            if not saw_idat or saw_iend or length != 0 or cursor != len(data):
                raise _png_error()
            saw_iend = True
        else:
            if chunk_kind in (b"acTL", b"fcTL", b"fdAT") or chunk_kind[0] & 0x20 == 0:
                raise _png_error()
            if saw_idat:
                idat_closed = True

    if not (saw_ihdr and saw_idat and saw_iend and channels):
        raise _png_error()
    pitch = width * channels
    expected_raw_length = (pitch + 1) * height
    try:
        decoder = zlib.decompressobj()
        scanlines = decoder.decompress(bytes(compressed), expected_raw_length + 1)
        if (len(scanlines) != expected_raw_length or not decoder.eof or
                decoder.unused_data or decoder.unconsumed_tail or
                decoder.flush()):
            raise _png_error()
    except zlib.error:
        raise _png_error() from None

    prior = bytearray(pitch)
    for row_num in range(height):
        index = row_num * (pitch + 1)
        kind = scanlines[index]
        if kind > 4:
            raise _png_error()
        source = scanlines[index + 1:index + 1 + pitch]
        current = bytearray(pitch)
        for i in range(pitch):
            left = current[i - channels] if i >= channels else 0
            up = prior[i]
            upper_left = prior[i - channels] if i >= channels else 0
            if kind == 0: predictor = 0
            elif kind == 1: predictor = left
            elif kind == 2: predictor = up
            elif kind == 3: predictor = (left + up) // 2
            else:
                p = left + up - upper_left
                distances = (abs(p - left), abs(p - up), abs(p - upper_left))
                predictor = (left, up, upper_left)[distances.index(min(distances))]
            current[i] = (source[i] + predictor) & 0xff
        prior = current
    return width, height


def verify_local_png(output_root: Path, generation_claim: dict[str, Any]) -> dict[str, Any]:
    """Match an owner-selected directory's exact bounded RGB/RGBA PNG bytes.

    Paths and errors are never returned. Generated filename is validated from
    M3-10's allowlisted schema, not accepted as user-provided relative path.
    """
    name = generation_claim.get("file_name")
    digest = generation_claim.get("png_sha256")
    size = generation_claim.get("size_bytes")
    width = generation_claim.get("width")
    height = generation_claim.get("height")
    if (type(name) is not str or not FILE_NAME.fullmatch(name)
            or type(digest) is not str or not re.fullmatch(r"[0-9a-f]{64}", digest)
            or type(size) is not int or not 45 <= size <= MAX_PNG_BYTES
            or type(width) is not int or type(height) is not int
            or not 1 <= width <= MAX_SIDE or not 1 <= height <= MAX_SIDE):
        raise ValueError("png_claim_invalid")
    try:
        if output_root.is_symlink() or not output_root.is_dir():
            raise ValueError("png_output_root_invalid")
        image_file = output_root / name
        if image_file.is_symlink() or not image_file.is_file():
            raise ValueError("png_file_missing_or_unsafe")
        if image_file.resolve(strict=True).parent != output_root.resolve(strict=True):
            raise ValueError("png_file_missing_or_unsafe")
        with image_file.open("rb") as reader:
            payload = reader.read(MAX_PNG_BYTES + 1)
    except (OSError, RuntimeError):
        raise ValueError("png_file_missing_or_unsafe") from None
    if len(payload) != size or not 45 <= len(payload) <= MAX_PNG_BYTES:
        raise ValueError("png_size_mismatch")
    if hashlib.sha256(payload).hexdigest() != digest:
        raise ValueError("png_sha256_mismatch")
    decoded_width, decoded_height = _decode_png_scanlines(payload, width, height)
    return {
        "verification": "png_crc_zlib_filters_sha256_and_dimensions_verified",
        "decoded_width": decoded_width,
        "decoded_height": decoded_height,
        "file_bytes_verified": len(payload),
        "png_sha256_verified": digest,
        "visual_prompt_adherence": "not_tested",
        "visual_image_quality": "not_tested",
        "model_execution_attribution": "not_tested",
    }

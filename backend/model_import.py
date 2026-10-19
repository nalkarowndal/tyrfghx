"""Explicit local model importer; no server upload, no network access.

When --source is omitted, Windows users can select a file with a native Tk
file dialog. This is a CLI-launched dialog, not yet a Tauri-integrated picker.
"""
from __future__ import annotations

import argparse
import json
import stat
import struct
import hashlib
import hmac
import os
import re
import tempfile
from pathlib import Path

from model_integrity import CHUNK_SIZE, IntegrityEntry, read_manifest, save_manifest_entry, verify_model

MAX_MODEL_BYTES = 64 * (1024 ** 3)
SHA256_HEX = re.compile(r"^[0-9a-fA-F]{64}$")
CATEGORIES = ("checkpoints", "loras", "vae")


def _check_header_on_open_file(src, size: int) -> None:
    """Validate header on the SAME open descriptor later copied and hashed."""
    if not stat.S_ISREG(os.fstat(src.fileno()).st_mode) or not 10 <= size <= MAX_MODEL_BYTES:
        raise ValueError("Invalid or excessive model size")
    prefix = src.read(8)
    if len(prefix) != 8:
        raise ValueError("Invalid safetensors header")
    count = struct.unpack("<Q", prefix)[0]
    if not 2 <= count <= min(1_048_576, size - 8):
        raise ValueError("Invalid safetensors header")
    payload = src.read(count)
    if len(payload) != count:
        raise ValueError("Invalid safetensors header")
    try:
        header = json.loads(payload)
    except (ValueError, UnicodeError) as exc:
        raise ValueError("Invalid safetensors header") from exc
    if not isinstance(header, dict) or not isinstance(header.get("__metadata__", {}), dict):
        raise ValueError("Invalid safetensors header")
    src.seek(0)


def import_model(
    source: Path,
    category: str,
    root: Path,
    expected_sha256: str | None = None,
) -> tuple[str, str]:
    """Cooperative safe import: one source handle, never delete rollback paths."""
    if category not in CATEGORIES:
        raise ValueError("Invalid category")
    if expected_sha256 is not None and SHA256_HEX.fullmatch(expected_sha256) is None:
        raise ValueError("Expected SHA-256 must be 64 hexadecimal characters")
    if source.is_symlink() or not source.is_file():
        raise ValueError("Selected source must be a regular, nonsymlink file")
    if source.suffix.casefold() != ".safetensors" or ":" in source.name or "\\" in source.name:
        raise ValueError("Only safe .safetensors files are accepted")
    # Checking a path and opening it later is not a fully race-free Win32
    # security boundary; that needs separately reviewed native no-follow I/O.
    with source.open("rb") as src:
        opened = os.fstat(src.fileno())
        size = opened.st_size
        _check_header_on_open_file(src, size)
        if root.is_symlink():
            raise ValueError("Unsafe model root")
        root.mkdir(parents=True, exist_ok=True)
        folder = root / category
        if folder.is_symlink():
            raise ValueError("Unsafe model category folder")
        folder.mkdir(exist_ok=True)
        if not folder.is_dir():
            raise ValueError("Category folder is invalid")
        # Fail before publishing a new model for a known corrupt registry.
        # A competing writer can still update it; save_manifest_entry
        # rechecks under the cooperative cross-language lock.
        read_manifest(root, strict=True)
        target = folder / source.name
        if target.exists() or target.is_symlink():
            raise FileExistsError(f"Refusing to overwrite {target.name}")
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=folder, prefix=".import-", suffix=".tmp", delete=False
            ) as dst:
                temp_path = Path(dst.name)
                digest = hashlib.sha256()
                copied = 0
                while block := src.read(CHUNK_SIZE):
                    copied += len(block)
                    if copied > MAX_MODEL_BYTES:
                        raise ValueError("Model grew past size limit during copy")
                    digest.update(block)
                    dst.write(block)
                dst.flush()
                os.fsync(dst.fileno())
            if copied != size:
                raise ValueError("Source file changed during copy")
            hexdigest = digest.hexdigest()
            if expected_sha256 is not None and not hmac.compare_digest(
                hexdigest, expected_sha256.lower()
            ):
                raise ValueError("SHA-256 does not match the expected value")
            # Atomic no-overwrite for the selected destination.
            os.link(temp_path, target)
            model_id = f"{category}/{source.name}"
            try:
                saved = temp_path.stat()
                save_manifest_entry(
                    root, model_id,
                    IntegrityEntry(sha256=hexdigest, size_bytes=saved.st_size, mtime_ns=saved.st_mtime_ns),
                )
            except Exception as exc:
                # A different process might have swapped the path. Deleting
                # by name on rollback can delete another actor's file.
                # Preserve the unregistered copy and report a safe repair need.
                raise RuntimeError(
                    "Model copy retained but integrity registration failed; manual repair needed"
                ) from exc
            return model_id, hexdigest
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)


def native_file_picker() -> Path | None:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError as exc:
        raise RuntimeError("Tkinter is unavailable; use --source instead") from exc
    window = tk.Tk()
    window.withdraw()
    try:
        selection = filedialog.askopenfilename(
            title="aiimage - 모델 파일 선택",
            filetypes=[("Safetensors model", "*.safetensors")],
        )
        return Path(selection) if selection else None
    finally:
        window.destroy()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import a local .safetensors file into aiimage.")
    parser.add_argument("--source", type=Path, help="If omitted, use a native local file picker")
    parser.add_argument("--category", choices=CATEGORIES, required=True)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent / "models")
    parser.add_argument("--expected-sha256", help="Optional trusted, externally obtained SHA-256")
    parser.add_argument("--verify", help="Only verify an existing model ID; no changes to file/manifest")
    args = parser.parse_args(argv)
    try:
        if args.verify is not None:
            state, digest = verify_model(args.root, args.verify)
            print(f"{state}: {args.verify} SHA256={digest}")
            return 0 if state == "match" else 2
        source = args.source if args.source is not None else native_file_picker()
        if source is None:
            print("No file selected. Nothing changed.")
            return 0
        identifier, digest = import_model(source, args.category, args.root, args.expected_sha256)
        print(f"Imported {identifier}; SHA256={digest}")
        print("No model execution or compatibility validation was performed.")
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        parser.error(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

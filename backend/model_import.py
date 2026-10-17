"""Explicit local model importer; no server upload, no network access.

When --source is omitted, Windows users can select a file with a native Tk
file dialog. This is a CLI-launched dialog, not yet a Tauri-integrated picker.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import os
import re
import tempfile
from pathlib import Path

from model_catalog import _read_safetensors_architecture
from model_integrity import CHUNK_SIZE, IntegrityEntry, hash_model, model_file, save_manifest_entry, verify_model

MAX_MODEL_BYTES = 64 * (1024 ** 3)
SHA256_HEX = re.compile(r"^[0-9a-fA-F]{64}$")
CATEGORIES = ("checkpoints", "loras", "vae")


def import_model(
    source: Path,
    category: str,
    root: Path,
    expected_sha256: str | None = None,
) -> tuple[str, str]:
    """Copy a selected safetensors model without overwriting existing data."""
    if category not in CATEGORIES:
        raise ValueError("Invalid category")
    if expected_sha256 is not None and SHA256_HEX.fullmatch(expected_sha256) is None:
        raise ValueError("Expected SHA-256 must be 64 hexadecimal characters")
    if source.is_symlink() or not source.is_file():
        raise ValueError("Selected source must be a regular, nonsymlink file")
    if source.suffix.casefold() != ".safetensors" or ":" in source.name or "\\" in source.name:
        raise ValueError("Only safe .safetensors files are accepted")
    size = source.stat().st_size
    if size <= 8 or size > MAX_MODEL_BYTES:
        raise ValueError("Invalid or excessive model size")
    _, valid_header = _read_safetensors_architecture(source, size)
    if not valid_header:
        raise ValueError("Invalid safetensors JSON header")
    # User explicitly selected this root; symlinks are never accepted.
    if root.is_symlink():
        raise ValueError("Unsafe model root")
    root.mkdir(parents=True, exist_ok=True)
    folder = root / category
    if folder.is_symlink():
        raise ValueError("Unsafe model category folder")
    folder.mkdir(exist_ok=True)
    if not folder.is_dir():
        raise ValueError("Category folder is invalid")
    target = folder / source.name
    if target.exists() or target.is_symlink():
        raise FileExistsError(f"Refusing to overwrite {target.name}")
    temp_path = None
    try:
        with source.open("rb") as src, tempfile.NamedTemporaryFile(
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
        # Hard-link staged file for atomic no-overwrite finalization on NTFS/ext4.
        # Do not replace or rename-over an existing user's file.
        os.link(temp_path, target)
        model_id = f"{category}/{source.name}"
        try:
            stat = target.stat()
            save_manifest_entry(
                root, model_id,
                IntegrityEntry(sha256=hexdigest, size_bytes=stat.st_size, mtime_ns=stat.st_mtime_ns),
            )
        except Exception:
            # No successful registration claimed; do not leave an untracked import.
            target.unlink(missing_ok=True)
            raise
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

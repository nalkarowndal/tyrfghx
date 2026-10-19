"""Cross-language cooperative lock for the app-local integrity registry.

Both Rust and Python acquire the same temporary directory name. mkdir is
atomic on the local filesystems used for this app's model root. Fail closed
after a bounded timeout; NEVER auto-remove a stale lock after a crash.
This prevents cooperative lost updates, not malicious filesystem races.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import os
import time

LOCK_NAME = ".integrity-write.lockdir"
LOCK_TIMEOUT_SEC = 10.0
LOCK_POLL_SEC = 0.025


@contextmanager
def exclusive_manifest_write(root: Path):
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Unsafe integrity root")
    lock_path = root / LOCK_NAME
    deadline = time.monotonic() + LOCK_TIMEOUT_SEC
    while True:
        try:
            lock_path.mkdir()
            break
        except FileExistsError:
            # Do not follow/recover an untrusted or abandoned lock.
            # The holder may have released the lock between mkdir and
            # this check. A missing path means we can retry immediately.
            if not lock_path.exists() and not lock_path.is_symlink():
                continue
            if lock_path.is_symlink() or not lock_path.is_dir():
                raise ValueError("Unsafe integrity lock")
            if time.monotonic() >= deadline:
                raise ValueError("Integrity manifest is busy; inspect stale lock manually")
            time.sleep(LOCK_POLL_SEC)
    try:
        yield
    finally:
        # Only release this writer's own guard; never delete user model files.
        os.rmdir(lock_path)

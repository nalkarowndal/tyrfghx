"""Private Tauri child entry point. No CLI paths, GPU imports, or downloads.

stdin: one bounded bootstrap JSON line, then an open lifetime lease.
stdout: one readiness JSON line; never use it for application logging.
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import sys
import threading

import uvicorn
from app import create_app


class InstanceLease:
    """Kernel ownership, no persistent lock file and no stale PID deletion."""
    def __init__(self, root: Path):
        self.handle = None
        if sys.platform == 'win32':
            from ctypes import wintypes
            self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            self.kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
            self.kernel.CreateMutexW.restype = wintypes.HANDLE
            self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            self.kernel.CloseHandle.restype = wintypes.BOOL
            name = hashlib.sha256(os.path.normcase(str(root)).encode('utf-8')).hexdigest()
            handle = self.kernel.CreateMutexW(None, False, 'Local\\aiimage-api-' + name)
            exists = ctypes.get_last_error() == 183
            if not handle:
                raise RuntimeError('ownership unavailable')
            if exists:
                self.kernel.CloseHandle(handle)
                raise RuntimeError('already owned')
            self.handle = handle

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def bootstrap(stream) -> Path:
    line = stream.readline(8193)
    if len(line) > 8192 or not line.endswith(b'\n'):
        raise ValueError('Invalid bootstrap')
    value = json.loads(line)
    if (not isinstance(value, dict) or set(value) != {'protocol', 'model_root'}
            or type(value['protocol']) is not int or value['protocol'] != 1
            or not isinstance(value['model_root'], str)):
        raise ValueError('Invalid bootstrap')
    root = Path(value['model_root'])
    if not root.is_absolute() or root.is_symlink():
        raise ValueError('Invalid model root')
    # resolve also normalizes absent directories; no mkdir or data migration.
    return root.resolve()


def main() -> int:
    lease = None
    listener = None
    try:
        if len(sys.argv) != 1:
            raise ValueError('No command line arguments accepted')
        root = bootstrap(sys.stdin.buffer)
        lease = InstanceLease(root)
        token = secrets.token_hex(32)
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if sys.platform == 'win32':
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        listener.bind(('127.0.0.1', 0))
        listener.listen(16)
        listener.setblocking(False)

        class ReadyServer(uvicorn.Server):
            async def startup(self, sockets=None):
                await super().startup(sockets=sockets)
                if self.started and not self.should_exit:
                    print(json.dumps({'protocol': 1, 'host': '127.0.0.1',
                                      'port': listener.getsockname()[1], 'token': token,
                                      'pid': os.getpid()}), flush=True)

        server = ReadyServer(uvicorn.Config(
            create_app(root, token), host='127.0.0.1', port=0,
            loop='asyncio', http='h11', ws='none', lifespan='on',
            proxy_headers=False, access_log=False, log_config=None,
            log_level='critical', timeout_graceful_shutdown=2,
        ))

        def watch_parent():
            # Any additional input or EOF ends the lease; no command protocol.
            sys.stdin.buffer.read(1)
            server.should_exit = True

        threading.Thread(target=watch_parent, daemon=True).start()
        server.run(sockets=[listener])
        return 0
    except Exception:
        # Never include config, paths, bearer tokens or raw framework errors.
        print('aiimage_backend_start_failed', file=sys.stderr, flush=True)
        return 1
    finally:
        if listener is not None:
            listener.close()
        if lease is not None:
            lease.close()


if __name__ == '__main__':
    raise SystemExit(main())

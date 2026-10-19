"""Real subprocess/HTTP smoke, reusable against the frozen Windows executable.

AIIMAGE_TEST_BACKEND points only to a disposable QA build. No inference imports.
"""
import json
import os
from pathlib import Path
import queue
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request


class BundledServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='aiimage QA 한글 ')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'models'
        self.root.mkdir()
        self.sentinel = self.root / 'keep.txt'
        self.sentinel.write_bytes(b'preserve me')

    def launch(self, bootstrap=None):
        command = [os.environ['AIIMAGE_TEST_BACKEND']] if os.environ.get('AIIMAGE_TEST_BACKEND') else [sys.executable, str(Path(__file__).with_name('bundled_server.py'))]
        child = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(self.cleanup, child)
        config = bootstrap if bootstrap is not None else {'protocol': 1, 'model_root': str(self.root)}
        child.stdin.write(json.dumps(config).encode() + b'\n')
        child.stdin.flush()
        return child

    @staticmethod
    def cleanup(child):
        if child.poll() is None:
            child.kill()
        child.wait(timeout=10)
        for stream in [child.stdin, child.stdout, child.stderr]:
            stream.close()

    def ready(self, child):
        result = queue.Queue()
        threading.Thread(target=lambda: result.put(child.stdout.readline(4097)), daemon=True).start()
        line = result.get(timeout=20)
        self.assertTrue(line, 'backend exited without readiness')
        self.assertLessEqual(len(line), 4096)
        data = json.loads(line)
        self.assertEqual(data['protocol'], 1)
        self.assertEqual(data['host'], '127.0.0.1')
        self.assertTrue(1024 <= data['port'] <= 65535)
        self.assertRegex(data['token'], r'^[0-9a-f]{64}$')
        self.assertEqual(data['pid'], child.pid)
        return data

    @staticmethod
    def request(data, token=None, path='/api/health', **headers):
        if token is not None:
            headers['Authorization'] = 'Bearer ' + token
        req = urllib.request.Request(f"http://127.0.0.1:{data['port']}{path}", headers=headers)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(req, timeout=3) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as error:
            return error.code, error.read()

    def test_readiness_auth_eof_restart_and_data_preservation(self):
        # An occupied conventional port cannot collide with the ephemeral bind.
        with socket.socket() as occupied:
            occupied.bind(('127.0.0.1', 0))
            occupied.listen()
            first = self.launch()
            data = self.ready(first)
            self.assertNotEqual(data['port'], occupied.getsockname()[1])
            self.assertEqual(self.request(data)[0], 401)
            self.assertEqual(self.request(data, 'wrong')[0], 401)
            self.assertEqual(self.request(data, data['token'], Origin='https://evil.example')[0], 403)
            self.assertEqual(self.request(data, data['token'])[0], 200)
            # Frozen Windows backend exposes ONLY authenticated, read-only
            # metadata inventory. It never loads torch, models or CUDA.
            self.assertEqual(self.request(data, path='/api/status')[0], 401)
            code, payload = self.request(data, data['token'], path='/api/status')
            self.assertEqual(code, 200)
            current = json.loads(payload)
            inventory = current['runtime_preflight']
            self.assertEqual(inventory['readiness'], 'not_verified')
            self.assertEqual(inventory['method'], 'distribution_metadata_only')
            self.assertFalse(inventory['cuda_tested'])
            self.assertFalse(inventory['gpu_accessed'])
            self.assertFalse(inventory['models_opened'])
            self.assertFalse(inventory['downloads_performed'])
            self.assertEqual([p['package'] for p in inventory['packages']],
                             ['torch', 'diffusers', 'transformers', 'accelerate',
                              'safetensors', 'Pillow'])
            first.stdin.close()
            self.assertEqual(first.wait(timeout=10), 0)
            second = self.launch()
            again = self.ready(second)
            self.assertNotEqual(again['token'], data['token'])
            self.assertEqual(self.request(again, data['token'])[0], 401)
            self.assertEqual(self.request(again, again['token'])[0], 200)
            second.stdin.close()
            self.assertEqual(second.wait(timeout=10), 0)
        self.assertEqual(self.sentinel.read_bytes(), b'preserve me')
        self.assertEqual(list(self.root.iterdir()), [self.sentinel])

    def test_invalid_bootstrap_fails_without_binding(self):
        for config in [{'protocol': 9, 'model_root': str(self.root)}, {'protocol': 1, 'model_root': 'relative'}, {'protocol': 1, 'model_root': str(self.root), 'host': '0.0.0.0'}]:
            child = self.launch(config)
            self.assertNotEqual(child.wait(timeout=10), 0)
            self.assertEqual(child.stdout.read(), b'')
            self.assertNotIn(str(self.root).encode(), child.stderr.read())

    @unittest.skipUnless(sys.platform == 'win32', 'Windows named mutex ownership')
    def test_duplicate_instance_blocked_and_crash_releases_mutex(self):
        first = self.launch()
        self.ready(first)
        duplicate = self.launch()
        self.assertNotEqual(duplicate.wait(timeout=10), 0)
        self.assertEqual(duplicate.stdout.read(), b'')
        first.kill()
        first.wait(timeout=10)
        recovered = self.launch()
        data = self.ready(recovered)
        self.assertEqual(self.request(data, data['token'])[0], 200)


if __name__ == '__main__':
    unittest.main()

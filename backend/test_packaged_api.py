"""Security regression tests use only synthetic paths, never user models."""
import tempfile
import unittest
from pathlib import Path
from fastapi.testclient import TestClient
import app as api


class PackagedApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.token = 'a' * 64
        self.assertTrue(hasattr(api, 'create_app'), 'packaged authenticated API factory is missing')
        self.client = TestClient(api.create_app(Path(self.tmp.name), self.token),
                                 base_url='http://127.0.0.1:45678', client=('127.0.0.1', 12345))
        self.headers = {'Authorization': f'Bearer {self.token}'}

    def test_all_routes_require_authentication(self):
        for route in ['/api/health', '/api/status', '/api/models', '/api/models/compatibility', '/docs', '/openapi.json']:
            with self.subTest(route=route):
                self.assertEqual(self.client.get(route).status_code, 401)
                self.assertEqual(self.client.get(route, headers={'Authorization': 'Bearer wrong'}).status_code, 401)
        self.assertEqual(self.client.get('/api/health', headers=self.headers).json(), {'ok': True})
        self.assertEqual(self.client.get('/docs', headers=self.headers).status_code, 404)

    def test_browser_origins_and_rebinding_hosts_are_rejected(self):
        for origin in ['https://evil.example', 'null', 'http://localhost:5173', 'tauri://localhost']:
            for method in ['GET', 'OPTIONS']:
                self.assertEqual(self.client.request(method, '/api/health', headers={**self.headers, 'Origin': origin}).status_code, 403)
        for host in ['evil.example', '127.0.0.1.evil.example', 'localhost', '[::1]', '127.0.0.1:bad']:
            self.assertEqual(self.client.get('/api/health', headers={**self.headers, 'Host': host}).status_code, 403)

    def test_non_loopback_peer_cannot_spoof_forwarded_header(self):
        client = TestClient(api.create_app(Path(self.tmp.name), self.token), base_url='http://127.0.0.1', client=('192.168.1.2', 1234))
        self.assertEqual(client.get('/api/health', headers={**self.headers, 'X-Forwarded-For': '127.0.0.1'}).status_code, 403)

    def test_catalog_uses_supplied_root_without_creating_or_modifying_files(self):
        root = Path(self.tmp.name)
        sentinel = root / 'keep.txt'
        sentinel.write_bytes(b'user data')
        self.assertEqual(self.client.get('/api/models', headers=self.headers).json(), [])
        self.assertEqual(sentinel.read_bytes(), b'user data')
        self.assertEqual(list(root.iterdir()), [sentinel])
        data = self.client.get('/api/status', headers=self.headers).json()
        self.assertTrue(all(e['status'] == 'unavailable' for e in data['engines']))
        self.assertNotIn(self.token, str(data))

    def test_invalid_tokens_fail_closed_at_construction(self):
        for token in ['', 'short', 'x' * 64, 'a' * 63, 'a' * 64 + '\n']:
            with self.assertRaises(ValueError):
                api.create_app(Path(self.tmp.name), token)


if __name__ == '__main__':
    unittest.main()

import unittest
from app import app
import json

class TestOTA(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True

    def test_ota_manifest(self):
        response = self.app.get('/api/ota/manifest')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn("files", data)
        self.assertIn("main.py", data["files"])
        self.assertIn("server.py", data["files"])
        self.assertIn("config.py", data["files"])
        print("\nManifest JSON response:\n", json.dumps(data, indent=2))

    def test_ota_download_valid(self):
        response = self.app.get('/api/ota/download/main.py')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(b"import server" in response.data or b"import config" in response.data or b"ota" in response.data)
        print("\nDownloaded file size for main.py:", len(response.data))

    def test_ota_download_invalid(self):
        response = self.app.get('/api/ota/download/../backend/app.py')
        self.assertIn(response.status_code, [403, 404])
        
        response = self.app.get('/api/ota/download/nonexistent.py')
        self.assertEqual(response.status_code, 404)

if __name__ == '__main__':
    unittest.main()

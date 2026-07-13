import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from contentgenie.web.api import app
from runContentGenie import API_PORT, WEB_PORT, main


class ContentGenieWebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_health_and_canonical_ports(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "product": "ContentGenie"})
        self.assertEqual(WEB_PORT, 31415)
        self.assertEqual(API_PORT, 31417)
        self.assertTrue(callable(main))

    def test_settings_and_assets_are_available_to_frontend(self):
        settings = self.client.get("/api/settings")
        assets = self.client.get("/api/assets")
        self.assertEqual(settings.status_code, 200)
        self.assertIn("GEMINI_API_KEY", settings.json()["values"])
        self.assertEqual(assets.status_code, 200)
        self.assertIsInstance(assets.json()["items"], list)

    def test_file_endpoint_blocks_paths_outside_media_roots(self):
        response = self.client.get("/api/files", params={"path": "setup.py"})
        self.assertEqual(response.status_code, 403)

    def test_generation_job_reports_validation_failure_as_state(self):
        response = self.client.post("/api/jobs", json={"rights_confirmed": False})
        self.assertEqual(response.status_code, 200)
        job_id = response.json()["id"]
        state = response.json()
        for _ in range(20):
            state = self.client.get(f"/api/jobs/{job_id}").json()
            if state["status"] == "failed":
                break
            time.sleep(0.02)
        self.assertEqual(state["status"], "failed")
        self.assertIn("publishing-rights review", state["error"])

    def test_production_history_and_title_named_downloads(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            video = root / "2026-07-14_12-00-00_deadbeef - fallback.mp4"
            video.write_bytes(b"contentgenie-video")
            manifest = video.with_suffix(".json")
            metadata = video.with_suffix(".txt")
            manifest.write_text(json.dumps({
                "generated_at": "2026-07-14T12:00:00+05:00",
                "content_type": "facts_shorts",
                "youtube": {"title": "My Great Short", "description": "Ready to publish."},
                "quality_report": {"score": 96, "approved": True},
                "video_quality_report": {"metrics": {"duration_seconds": 51.2, "width": 1080, "height": 1920}},
                "research_sources": [{"url": "https://example.test/source"}],
            }), encoding="utf-8")
            metadata.write_text("YouTube metadata", encoding="utf-8")

            with patch("contentgenie.web.api.PRODUCTIONS_ROOT", root):
                response = self.client.get("/api/productions")
                self.assertEqual(response.status_code, 200)
                production = response.json()["items"][0]
                self.assertEqual(production["title"], "My Great Short")
                self.assertEqual(production["height"], 1920)
                self.assertEqual(production["quality_score"], 96)
                self.assertEqual(production["sources"], 1)

                download = self.client.get(production["download_url"])
                self.assertEqual(download.status_code, 200)
                self.assertEqual(download.content, b"contentgenie-video")
                disposition = download.headers["content-disposition"]
                self.assertIn("attachment", disposition)
                self.assertIn("My%20Great%20Short.mp4", disposition)

                deleted = self.client.delete(f"/api/productions/{production['id']}")
                self.assertEqual(deleted.status_code, 200)
                self.assertEqual(deleted.json()["items"], [])
                self.assertFalse(video.exists())
                self.assertFalse(manifest.exists())
                self.assertFalse(metadata.exists())


if __name__ == "__main__":
    unittest.main()

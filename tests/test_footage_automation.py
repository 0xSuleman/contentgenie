import unittest

from contentgenie.engine.facts_short_engine import FactsShortEngine
from contentgenie.footage.analysis import classify_visual_event
from contentgenie.footage.models import FootageCandidate, is_commercial_derivative_license, normalize_license
from contentgenie.footage.montage import plan_retention_segments
from contentgenie.footage.service import FootageService
from contentgenie.footage.sources import (
    InternetArchiveSource,
    WikimediaCommonsSource,
    YouTubeCreativeCommonsSource,
)


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class _YouTubeSession:
    def __init__(self):
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        if url.endswith("/search"):
            return _Response({
                "items": [{
                    "id": {"videoId": "abc123"},
                    "snippet": {"title": "Minecraft Parkour Gameplay", "description": "No commentary"},
                }]
            })
        return _Response({
            "items": [{
                "id": "abc123",
                "status": {"license": "creativeCommon", "privacyStatus": "public"},
                "snippet": {
                    "title": "Minecraft Parkour Gameplay",
                    "description": "No commentary",
                    "channelTitle": "Creator",
                },
                "contentDetails": {"duration": "PT2M5S"},
                "statistics": {"viewCount": "1000"},
            }]
        })


class _WikimediaSession:
    def get(self, url, params=None, timeout=None):
        if params.get("list") == "categorymembers":
            return _Response({
                "query": {
                    "categorymembers": [{"ns": 6, "title": "File:Xonotic parkour gameplay.webm"}],
                }
            })
        return _Response({
            "query": {
                "pages": [{
                    "pageid": 42,
                    "title": "File:Xonotic parkour gameplay.webm",
                    "imageinfo": [{
                        "url": "https://upload.wikimedia.test/xonotic.webm",
                        "descriptionurl": "https://commons.wikimedia.test/xonotic",
                        "width": 1920,
                        "height": 1080,
                        "size": 50_000_000,
                        "extmetadata": {
                            "LicenseShortName": {"value": "CC BY 4.0"},
                            "LicenseUrl": {"value": "https://creativecommons.org/licenses/by/4.0/"},
                            "Artist": {"value": "Open Player"},
                            "ImageDescription": {"value": "Xonotic open source game parkour gameplay"},
                        },
                    }],
                }]
            }
        })


class _ArchiveSession:
    def get(self, url, params=None, timeout=None):
        if "advancedsearch" in url:
            return _Response({
                "response": {
                    "docs": [{
                        "identifier": "freedoom-gameplay",
                        "title": "Freedoom action gameplay",
                        "creator": "Open Player",
                        "description": "Free game footage",
                        "licenseurl": "https://creativecommons.org/licenses/by/4.0/",
                    }]
                }
            })
        return _Response({
            "metadata": {
                "title": "Freedoom action gameplay",
                "creator": "Open Player",
                "description": "Freedoom open game action",
                "licenseurl": "https://creativecommons.org/licenses/by/4.0/",
            },
            "files": [{"name": "freedoom.mp4", "source": "original", "size": "60000000"}],
        })


class FootageAutomationTests(unittest.TestCase):
    def test_visual_event_classifier_prioritizes_impacts_and_rejects_static_frames(self):
        event, bonus = classify_visual_event(0.22, 0.08, 0.52, 0.5, 120, 118)
        self.assertEqual(event, "impact_or_landing_peak")
        self.assertGreater(bonus, 0)
        event, bonus = classify_visual_event(0.001, 0.001, 0.5, 0.5, 120, 120)
        self.assertEqual(event, "static_or_menu_risk")
        self.assertLess(bonus, 0)

    def test_strict_license_gate_accepts_only_commercial_derivative_licenses(self):
        accepted = [
            ("CC0 1.0", ""),
            ("Public domain", ""),
            ("Creative Commons Attribution 4.0", "https://creativecommons.org/licenses/by/4.0/"),
        ]
        rejected = [
            ("CC BY-SA 4.0", "https://creativecommons.org/licenses/by-sa/4.0/"),
            ("CC BY-NC 4.0", "https://creativecommons.org/licenses/by-nc/4.0/"),
            ("CC BY-ND 4.0", "https://creativecommons.org/licenses/by-nd/4.0/"),
            ("Standard YouTube License", ""),
        ]
        self.assertTrue(all(is_commercial_derivative_license(*item) for item in accepted))
        self.assertTrue(all(not is_commercial_derivative_license(*item) for item in rejected))
        self.assertEqual(normalize_license("", "https://creativecommons.org/publicdomain/zero/1.0/"), "CC0")

    def test_youtube_api_search_requests_and_rechecks_creative_commons_license(self):
        session = _YouTubeSession()
        results = YouTubeCreativeCommonsSource("api-key", session=session).search(style="Parkour", limit=5)
        self.assertEqual(len(results), 1)
        self.assertEqual(session.calls[0][1]["videoLicense"], "creativeCommon")
        self.assertTrue(results[0].auto_eligible)
        self.assertEqual(results[0].license_name, "CC BY 3.0")

    def test_wikimedia_adapter_requires_per_file_license_and_open_game_evidence(self):
        results = WikimediaCommonsSource(session=_WikimediaSession()).search(style="Parkour", limit=5)
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].auto_eligible)
        self.assertEqual(results[0].creator, "Open Player")
        self.assertEqual(results[0].resolution, "1920x1080")

    def test_archive_adapter_requires_explicit_license_and_original_video_file(self):
        results = InternetArchiveSource(session=_ArchiveSession()).search(style="Action", limit=5)
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].auto_eligible)
        self.assertTrue(results[0].download_url.endswith("freedoom.mp4"))

    def test_retention_plan_starts_with_best_moment_and_avoids_overlap(self):
        moments = [
            {"time": 10.0, "score": 98.0, "motion": 0.3, "focus_x": 0.5, "signature": "a"},
            {"time": 11.0, "score": 97.0, "motion": 0.29, "focus_x": 0.5, "signature": "b"},
            {"time": 30.0, "score": 93.0, "motion": 0.25, "focus_x": 0.4, "signature": "c"},
            {"time": 50.0, "score": 90.0, "motion": 0.2, "focus_x": 0.6, "signature": "d"},
            {"time": 70.0, "score": 88.0, "motion": 0.18, "focus_x": 0.5, "signature": "e"},
        ]
        assets = [{
            "name": "licensed",
            "path": "source.mp4",
            "source_key": "youtube:abc",
            "analysis": {"duration": 100.0, "width": 1920, "height": 1080, "moments": moments},
            "provenance": {"attribution": "credit"},
        }]
        plan = plan_retention_segments(assets, 12.0, intensity="High", avoid_recent=False, seed="test")
        self.assertAlmostEqual(sum(item["duration"] for item in plan), 12.0, places=5)
        self.assertEqual(plan[0]["score"], 98.0)
        for index, item in enumerate(plan):
            for other in plan[index + 1 :]:
                self.assertGreaterEqual(
                    abs(item["start"] - other["start"]),
                    min(max(item["duration"], other["duration"]) + 1.0, 10.0),
                )

    def test_retention_plan_snaps_cuts_to_caption_and_sfx_beats(self):
        moments = [
            {"time": float(value), "score": 100 - value, "motion": 0.2, "focus_x": 0.5, "signature": str(value)}
            for value in (10, 30, 50, 70, 90)
        ]
        assets = [{
            "name": "licensed",
            "path": "source.mp4",
            "source_key": "youtube:beats",
            "analysis": {"duration": 120.0, "width": 1920, "height": 1080, "moments": moments},
            "provenance": {},
        }]
        plan = plan_retention_segments(
            assets,
            12.0,
            intensity="High",
            avoid_recent=False,
            seed="beats",
            preferred_cut_times=[3.0, 6.0, 9.0],
        )
        cut_times = []
        elapsed = 0.0
        for segment in plan[:-1]:
            elapsed += segment["duration"]
            cut_times.append(round(elapsed, 1))
        self.assertTrue(set(cut_times) & {3.0, 6.0, 9.0})
        self.assertAlmostEqual(sum(item["duration"] for item in plan), 12.0, places=5)

    def test_attributions_are_deduplicated_by_source(self):
        segments = [
            {"source_key": "one", "provenance": {"attribution": "Work One — CC BY"}},
            {"source_key": "one", "provenance": {"attribution": "Work One — CC BY"}},
            {"source_key": "two", "provenance": {"attribution": "Work Two — CC0"}},
        ]
        self.assertEqual(
            FootageService.attribution_lines(segments),
            ["Work One — CC BY", "Work Two — CC0"],
        )

    def test_candidate_requires_verified_underlying_game_policy(self):
        candidate = FootageCandidate(
            source="youtube",
            source_id="x",
            title="Gameplay",
            creator="Creator",
            source_url="https://example.test/watch",
            download_url="https://example.test/video",
            license_name="CC BY 4.0",
            license_url="https://creativecommons.org/licenses/by/4.0/",
            attribution="credit",
            rights_status="unverified",
        )
        self.assertFalse(candidate.auto_eligible)
        candidate.rights_status = "verified"
        self.assertTrue(candidate.auto_eligible)

    def test_engine_accepts_automatic_mode_without_manual_background(self):
        engine = FactsShortEngine(
            voiceModule=None,
            facts_type="science",
            background_video_name=None,
            background_music_name="music",
            rights_confirmed=True,
            footage_mode="Automatic licensed gameplay",
        )
        try:
            self.assertEqual(engine._db_footage_mode, "Automatic licensed gameplay")
            self.assertIsNone(engine._db_background_video_name)
        finally:
            engine.dataManager.delete()


if __name__ == "__main__":
    unittest.main()

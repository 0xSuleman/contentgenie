import unittest

from contentgenie.music.models import MusicCandidate, normalize_music_direction
from contentgenie.music.sources import OpenverseMusicSource, score_candidate


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class _Session:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return _Response(self.payload)


def _candidate(**updates):
    values = {
        "source_id": "track-1",
        "title": "Cinematic Mystery Instrumental Background",
        "creator": "Composer",
        "source_url": "https://example.org/tracks/1",
        "download_url": "https://cdn.example.org/track.mp3",
        "license_name": "CC BY 4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "attribution": "Track by Composer, CC BY 4.0",
        "duration": 90,
        "bit_rate": 192000,
        "tags": ["cinematic", "mystery", "instrumental", "background"],
    }
    values.update(updates)
    return MusicCandidate(**values)


class MusicAutomationTests(unittest.TestCase):
    def test_only_commercial_derivative_music_is_auto_eligible(self):
        self.assertTrue(_candidate().auto_eligible)
        self.assertFalse(_candidate(license_name="CC BY-NC 4.0", license_url="https://creativecommons.org/licenses/by-nc/4.0/").auto_eligible)
        self.assertFalse(_candidate(license_name="CC BY-ND 4.0", license_url="https://creativecommons.org/licenses/by-nd/4.0/").auto_eligible)
        self.assertFalse(_candidate(duration=20).auto_eligible)

    def test_music_scoring_prefers_instrumental_mood_match(self):
        direction = {"mood": "suspenseful", "energy": "medium", "style": "cinematic ambient", "search_terms": ["mystery tension"]}
        matching = _candidate()
        vocal = _candidate(title="Spoken Word Mystery", tags=["speech", "voice over"])
        self.assertGreater(score_candidate(matching, direction, 50), score_candidate(vocal, direction, 50))

    def test_openverse_search_requests_only_cc0_and_cc_by_and_filters_results(self):
        session = _Session({
            "results": [
                {
                    "id": "good",
                    "title": "Ambient Documentary Instrumental",
                    "creator": "Artist",
                    "foreign_landing_url": "https://example.org/good",
                    "url": "https://cdn.example.org/good.mp3",
                    "license": "by",
                    "license_version": "4.0",
                    "license_url": "https://creativecommons.org/licenses/by/4.0/",
                    "attribution": "Good by Artist, CC BY 4.0.",
                    "duration": 90000,
                    "filetype": "mp3",
                    "bit_rate": 192000,
                    "tags": [{"name": "ambient"}, {"name": "instrumental"}, {"name": "documentary"}],
                    "mature": False,
                    "source": "freesound",
                },
                {
                    "id": "short",
                    "title": "Short sting",
                    "creator": "Artist",
                    "foreign_landing_url": "https://example.org/short",
                    "url": "https://cdn.example.org/short.mp3",
                    "license": "by",
                    "license_version": "4.0",
                    "license_url": "https://creativecommons.org/licenses/by/4.0/",
                    "duration": 4000,
                    "filetype": "mp3",
                    "tags": [],
                },
            ]
        })
        results = OpenverseMusicSource(session).search(
            {"mood": "curious", "energy": "medium", "style": "documentary", "search_terms": []},
            target_duration=50,
        )
        self.assertEqual([item.source_id for item in results], ["good"])
        self.assertEqual(session.calls[0][1]["params"]["license"], "cc0,by")

    def test_direction_is_bounded_and_has_a_safe_fallback(self):
        direction = normalize_music_direction({"mood": "angry", "energy": "maximum", "style": "opera", "search_terms": ["  Space  Wonder  "]}, tone="Warm and reflective")
        self.assertEqual(direction["mood"], "reflective")
        self.assertEqual(direction["energy"], "medium")
        self.assertEqual(direction["style"], "cinematic ambient")
        self.assertEqual(direction["search_terms"], ["space wonder"])


if __name__ == "__main__":
    unittest.main()

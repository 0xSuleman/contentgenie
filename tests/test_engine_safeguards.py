import unittest

from contentgenie.engine.facts_short_engine import FactsShortEngine


class EngineSafeguardTests(unittest.TestCase):
    def test_backend_rejects_unconfirmed_commercial_media_rights(self):
        with self.assertRaisesRegex(ValueError, "Commercial media rights"):
            FactsShortEngine(
                voiceModule=None,
                facts_type="science",
                background_video_name="video",
                background_music_name="music",
                rights_confirmed=False,
            )


if __name__ == "__main__":
    unittest.main()

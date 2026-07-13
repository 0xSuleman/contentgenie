import unittest

from contentgenie.gpt.story_package_gpt import _normalize_package, audit_story_package


def _script_with_word_count(count=135):
    sentences = []
    words = ["specific", "human", "stakes", "change", "when", "pressure", "forces", "a", "clear", "decision"]
    for index in range(count):
        word = words[index % len(words)]
        if index % 12 == 11:
            word += "."
        sentences.append(word)
    return " ".join(sentences)


class StoryQualityTests(unittest.TestCase):
    def test_normalizer_repairs_missing_asset_anchors(self):
        script = _script_with_word_count()
        package = _normalize_package({
            "script": script,
            "youtube_title": "A Specific Choice Changed Everything",
            "youtube_description": "An original micro-story.",
            "image_prompts": [{"anchor_text": "not in narration", "prompt": "cinematic scene"}],
            "sfx_cues": [{"anchor_text": "also missing", "effect": "impact", "intensity": "high"}],
        }, num_images=2)

        self.assertEqual(len(package["image_prompts"]), 2)
        for item in package["image_prompts"]:
            self.assertIn(item["anchor_text"].lower(), script.lower())
        self.assertEqual(package["sfx_cues"], [])
        self.assertEqual(package["music_direction"]["mood"], "curious")
        self.assertIn("#Shorts", package["youtube_description"])

    def test_audit_blocks_cliffhanger_bait(self):
        package = {
            "script": _script_with_word_count() + " Follow for part two.",
            "youtube_title": "A Complete Story",
            "image_prompts": [],
            "sfx_cues": [],
        }
        report = audit_story_package(package, target_duration=50, recent_content=[])
        self.assertTrue(report["blocking"])
        self.assertFalse(report["approved"])

    def test_audit_flags_high_similarity_to_recent_content(self):
        script = _script_with_word_count()
        report = audit_story_package(
            {"script": script, "youtube_title": "Current", "image_prompts": [], "sfx_cues": []},
            target_duration=50,
            recent_content=[{"title": "Previous", "script": script}],
        )
        self.assertTrue(report["blocking"])
        self.assertGreaterEqual(report["metrics"]["recent_content_similarity"], 0.99)


if __name__ == "__main__":
    unittest.main()

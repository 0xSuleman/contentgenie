import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from contentgenie.config.performance import get_moviepy_video_kwargs
from contentgenie.editing_framework.fast_caption_renderer import split_pop_captions, write_pop_caption_ass
from contentgenie.editing_utils.editing_images import searchImageUrlsFromQuery


class RenderOptimizationTests(unittest.TestCase):
    def _schema(self):
        return {
            "visual_assets": {
                "background_video_0": {"type": "video", "z": 0, "parameters": {"url": "background.mp4"}, "actions": []},
                "caption_pop_0": {
                    "type": "text",
                    "z": 6,
                    "parameters": {
                        "text": "HOOK",
                        "font_size": 118,
                        "color": "#FFD400",
                        "stroke_width": 4,
                        "stroke_color": "black",
                    },
                    "actions": [
                        {"type": "set_time_start", "param": 0.2},
                        {"type": "set_time_end", "param": 0.6},
                        {"type": "bounce_scale", "param": {"start": 0.55, "peak": 1.18, "settle": 1, "attack": 0.08, "release": 0.16}},
                        {"type": "screen_position", "param": {"pos": ["center", 1120]}},
                    ],
                },
            },
            "audio_assets": {},
        }

    def test_pop_captions_are_split_into_one_accelerated_layer(self):
        schema = self._schema()
        base, captions = split_pop_captions(schema)
        self.assertEqual(len(captions), 1)
        self.assertIn("background_video_0", base["visual_assets"])
        self.assertNotIn("caption_pop_0", base["visual_assets"])
        self.assertIn("caption_pop_0", schema["visual_assets"])

    def test_ass_keeps_timing_color_outline_and_bounce(self):
        _, captions = split_pop_captions(self._schema())
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "captions.ass"
            write_pop_caption_ass(captions, destination)
            text = destination.read_text(encoding="utf-8-sig")
        self.assertIn("0:00:00.20,0:00:00.60", text)
        self.assertIn(r"\an8\pos(540,1160)", text)
        self.assertIn(r"\fscx55\fscy55", text)
        self.assertIn(r"\t(0,80,\fscx118\fscy118)", text)
        self.assertIn("&H0000D4FF&", text)
        self.assertIn(r"\bord4", text)

    def test_lossless_intermediate_never_uses_a_lossy_crf(self):
        settings = get_moviepy_video_kwargs(use_nvenc=False, lossless=True)
        self.assertEqual(settings["codec"], "libx264")
        self.assertIn("0", settings["ffmpeg_params"])
        self.assertIn("yuv444p", settings["ffmpeg_params"])

    def test_valid_generated_images_are_reused_on_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "generated.jpg"
            Image.new("RGB", (512, 512), "navy").save(output)
            with patch("contentgenie.editing_utils.editing_images.generateAiImage") as generator:
                result = searchImageUrlsFromQuery("cinematic hook", output_path=str(output))
            self.assertEqual(result, str(output))
            generator.assert_not_called()


if __name__ == "__main__":
    unittest.main()

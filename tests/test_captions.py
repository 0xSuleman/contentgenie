import unittest

from contentgenie.editing_utils.captions import getCaptionsWithTime


class CaptionTimingTests(unittest.TestCase):
    def test_punctuation_word_stays_with_the_sentence(self):
        transcription = {
            "segments": [{
                "words": [
                    {"text": "The", "start": 0.0, "end": 0.2},
                    {"text": "door", "start": 0.2, "end": 0.5},
                    {"text": "opened.", "start": 0.5, "end": 0.9},
                    {"text": "Nobody", "start": 1.0, "end": 1.4},
                    {"text": "moved.", "start": 1.4, "end": 1.8},
                ]
            }]
        }

        captions = getCaptionsWithTime(transcription, maxCaptionSize=30)

        self.assertEqual(captions[0], ((0.0, 0.9), "The door opened."))
        self.assertEqual(captions[1], ((1.0, 1.8), "Nobody moved."))

    def test_no_word_is_lost_when_length_limit_splits_caption(self):
        words = [
            {"text": text, "start": index * 0.2, "end": (index + 1) * 0.2}
            for index, text in enumerate(["one", "two", "three", "four", "five", "six"])
        ]
        captions = getCaptionsWithTime({"segments": [{"words": words}]}, maxCaptionSize=9)
        rendered_words = " ".join(text for _, text in captions).split()
        self.assertEqual(rendered_words, ["one", "two", "three", "four", "five", "six"])


if __name__ == "__main__":
    unittest.main()

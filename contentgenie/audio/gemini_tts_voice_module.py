import base64
import os
import re
import time
import wave
from pathlib import Path

import requests

from contentgenie.audio.voice_module import VoiceModule
from contentgenie.config.api_db import ApiKeyManager


GEMINI_TTS_MODEL = "gemini-3.1-flash-tts-preview"
GEMINI_TTS_DEFAULT_VOICE = "Aoede"


GEMINI_TTS_PERSONAS = {
    "The Energetic Co-Host": {
        "voice": "Aoede",
        "profile": "An adult female American English storytime narrator with bright, energetic, surprised podcast-style energy.",
        "scene": (
            "A clean, close-mic creator studio. The narrator is speaking directly to one "
            "viewer as if sharing a gripping story with a friend late at night."
        ),
        "style": (
            "Female US English voice. Warm, intimate, punchy, surprised, and conversational. Use "
            "the Vocal Smile throughout so the tone feels bright, inviting, and realistic "
            "without sounding artificial."
        ),
        "pace": (
            "Energetic storytime pacing: natural and emotionally responsive, with a strong hook, "
            "small suspense pauses, and clear emphasis on twists or reveals."
        ),
    },
    "The Game Show Host": {
        "voice": "Zephyr",
        "profile": "An adult female American English storytime narrator with vibrant, surprised host energy.",
        "scene": (
            "A lively story stage with a tight spotlight. The narrator is animated and "
            "charismatic, turning each fact or plot beat into a reveal."
        ),
        "style": (
            "Female US English voice. Big, colorful, and engaging, with a clear Vocal "
            "Smile. Project excitement without shouting, with crisp consonants and "
            "expressive storytime emphasis."
        ),
        "pace": (
            "Rhythmic and theatrical, but still believable. Use dramatic beats before "
            "important reveals and a clean landing on the final sentence."
        ),
    },
}


class GeminiTTSVoiceModule(VoiceModule):
    def __init__(self, api_key=None, persona="The Energetic Co-Host", model=GEMINI_TTS_MODEL):
        self.api_key = api_key or ApiKeyManager.get_api_key("GEMINI_API_KEY")
        self.persona = persona if persona in GEMINI_TTS_PERSONAS else "The Energetic Co-Host"
        self.model = model
        super().__init__()

    def update_usage(self):
        return None

    def get_remaining_characters(self):
        return 999999999999

    def generate_voice(self, text, outputfile):
        if not self.api_key:
            raise Exception("GEMINI_API_KEY is required for Gemini TTS")

        chunks = self._chunk_transcript(text)
        pcm_chunks = [self._generate_pcm(chunk) for chunk in chunks]
        self._write_wave(outputfile, b"".join(pcm_chunks))
        return outputfile

    def _chunk_transcript(self, text, max_chars=1800):
        text = re.sub(r"\s+", " ", (text or "")).strip()
        if not text:
            raise Exception("Cannot generate Gemini TTS for empty text")

        sentences = re.split(r"(?<=[.!?])\s+", text)
        chunks = []
        current = ""
        for sentence in sentences:
            if not sentence:
                continue
            if current and len(current) + len(sentence) + 1 > max_chars:
                chunks.append(current.strip())
                current = sentence
            else:
                current = f"{current} {sentence}".strip()
        if current:
            chunks.append(current.strip())
        return chunks

    def _build_prompt(self, transcript):
        persona = GEMINI_TTS_PERSONAS[self.persona]
        return f"""Synthesize natural spoken audio only. Do not read the directions, headings, or labels aloud. Read only the text under #### TRANSCRIPT.

# AUDIO PROFILE: {self.persona}
## Role
{persona["profile"]}

## THE SCENE
{persona["scene"]}

### DIRECTOR'S NOTES
Style:
* {persona["style"]}
* Always speak in American English with an adult female storyteller sound.
* For suspense or Reddit stories, sound energetic, surprised, and slightly breathless at reveals while keeping volume consistent.
* Sound like a real human creator, not a robotic announcer.
* Keep emotion aligned with the words. Do not overact sad, serious, or factual lines.

Pacing:
* {persona["pace"]}
* Use punchy consonants and clean articulation for mobile speakers.

Audio tags:
* Apply [excited], [curious], [amazed], [serious], [whispers], or [short pause] only when the transcript naturally calls for it.
* If the transcript is not English, keep these performance tags in English but speak the transcript in its own language.

#### TRANSCRIPT
[with a vocal smile, energetic and realistic] {transcript}
"""

    def _generate_pcm(self, transcript):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        payload = {
            "contents": [{"parts": [{"text": self._build_prompt(transcript)}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {
                        "prebuiltVoiceConfig": {
                            "voiceName": GEMINI_TTS_PERSONAS[self.persona].get("voice", GEMINI_TTS_DEFAULT_VOICE)
                        }
                    }
                },
            },
        }

        last_error = None
        for attempt in range(3):
            try:
                response = requests.post(
                    url,
                    headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"},
                    json=payload,
                    timeout=240,
                )
                response.raise_for_status()
                data = response.json()
                inline_data = self._extract_inline_audio(data)
                if inline_data:
                    return base64.b64decode(inline_data)
                last_error = "Gemini TTS response did not include audio data"
            except Exception as error:
                last_error = str(error).replace(str(self.api_key), "[REDACTED]")
            time.sleep(1 + attempt)
        raise Exception(f"Gemini TTS failed: {last_error}")

    def _extract_inline_audio(self, response_data):
        candidates = response_data.get("candidates") or []
        for candidate in candidates:
            parts = ((candidate.get("content") or {}).get("parts")) or []
            for part in parts:
                inline_data = part.get("inlineData") or part.get("inline_data") or {}
                if inline_data.get("data"):
                    return inline_data["data"]
        return None

    def _write_wave(self, outputfile, pcm, channels=1, rate=24000, sample_width=2):
        Path(outputfile).parent.mkdir(parents=True, exist_ok=True)
        with wave.open(outputfile, "wb") as wav_file:
            wav_file.setnchannels(channels)
            wav_file.setsampwidth(sample_width)
            wav_file.setframerate(rate)
            wav_file.writeframes(pcm)
        if not os.path.exists(outputfile):
            raise Exception("Gemini TTS did not write an output audio file")

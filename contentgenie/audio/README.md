# Audio Module

The audio module provides utilities for audio processing, duration detection, transcription, and voice synthesis.

## audio_utils.py

Contains audio processing helpers such as YouTube audio download, speed adjustment, transcription, and words-per-second calculations.

## audio_duration.py

Contains helpers for probing audio/video duration through yt-dlp and ffprobe.

## voice_module.py

Defines the abstract `VoiceModule` interface used by content engines.

## edge_voice_module.py

Implements free Microsoft EdgeTTS voice synthesis for the app.

## gemini_tts_voice_module.py

Implements Gemini 3.1 Flash TTS Preview voice synthesis through the Gemini API.

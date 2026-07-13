# Module: api_utils

The `api_utils` module contains helpers for free or configured media providers.

## File: image_api.py

Provides image search and AI image generation helpers:

- Bing image search for legacy search-based image sourcing.
- Pollinations.ai image generation with no API key.
- HuggingFace Z-Image generation when `HUGGINGFACE_TOKEN` is configured.

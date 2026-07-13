# Module: gpt

The `gpt` module contains prompt helpers for script generation, translation, metadata generation, and editing decisions.

`gpt_utils.py` sends LLM requests to Gemini using `GEMINI_API_KEY`.

Main helper modules:

- `facts_gpt.py`: generates fact scripts and subjects.
- `reddit_gpt.py`: generates Reddit-style story content.
- `gpt_editing.py`: generates image and video search prompts.
- `gpt_translate.py`: translates content.
- `gpt_yt.py`: generates YouTube titles and descriptions.

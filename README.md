# ContentGenie

ContentGenie is a production-focused workspace for creating original YouTube Shorts with researched scripts, editorial review, voiceover, word-timed captions, generated visuals, sound design, licensed gameplay automation, and encoded-file quality checks.

## Run Locally

```bash
python runContentGenie.py
```

The Next.js studio runs at:

```text
http://localhost:31415
```

The launcher starts the private FastAPI service automatically and rebuilds the frontend when its source changes. Node.js 20 or newer is required.

For frontend-only development:

```bash
cd frontend
npm install
npm run dev
```

## Main Features

- Schema-constrained story packages with Gemini.
- Grounded research for facts and history content through Gemini Search, with Wikimedia and date-specific "On this day" sources as a resilient fallback. If both are unavailable, factual generation stops instead of publishing unverified claims.
- Production mode with a second editorial pass that scores the hook, retention, originality, clarity, payoff, and advertiser safety.
- Similarity checks against recent channel output to reduce repetitive, mass-produced results.
- Creative direction controls for the episode brief, audience, tone, editorial angle, and target duration.
- EdgeTTS or Gemini Flash TTS voiceover.
- Whisper-timed captions, including traditional and color-bounce styles.
- Generated Z-Image overlays with configurable size, screen position, pacing, and subtle motion.
- Timed sound effects from the local `assets/sfx` library.
- Automatic licensed-gameplay discovery from Wikimedia Commons, YouTube Creative Commons, and Internet Archive, with a key-free YouTube fallback.
- Strict CC0/public-domain/CC BY commercial-use gates, publisher-policy checks, source checksums, saved license evidence, and automatic description attribution.
- Motion, clarity, exposure, and vertical-crop analysis that assembles several high-retention gameplay moments, snapping cuts to caption pauses and SFX beats instead of selecting one random continuous clip.
- Mixed, parkour, racing, satisfying, and action footage styles with balanced/high/extreme pacing and recent-segment reuse prevention.
- Manual background video, background music, captions, image layout, and normalized audio mix remain available.
- Post-render checks for vertical aspect ratio, resolution, duration, audio, frame rate, and file integrity.
- A JSON production manifest next to every video with the script, research sources, prompts, quality reports, media-rights confirmation, and human review checklist.

## Production workflow

1. Add commercially licensed music in **Media Library**. Use **Discover free licensed gameplay** to inspect or pre-download automatic footage if desired.
2. Add your Gemini key in **Settings**. A YouTube Data API key is optional because the slower key-free CC metadata search remains available.
3. In **Create**, leave **Automatic licensed gameplay** enabled, choose a footage style and cut intensity, and provide the episode's creative direction.
4. Review the media-rights acknowledgement and create the Short. The automatic library replenishes itself when eligible footage is low.
5. Watch the entire export and inspect its `.json` manifest and generated gameplay credits before uploading.

The tool does not promise views, monetization, or income. You are responsible for factual accuracy, originality, advertiser suitability, copyright, synthetic-content disclosure, and compliance with YouTube policies.

## Output files

Each successful render creates three files in `videos/`:

- `.mp4` — the finished vertical Short.
- `.txt` — upload title and description.
- `.json` — production manifest and review checklist.

## Tests

```bash
python -m unittest discover -s tests -v
```

## Requirements

Install dependencies from `requirements.txt`, configure API keys in ContentGenie's **Settings** tab, and make sure FFmpeg is available.

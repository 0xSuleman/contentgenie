from pathlib import Path

from contentgenie.audio.audio_duration import get_asset_duration
from contentgenie.config.render_settings import (
    get_sfx_max_cues,
    get_sfx_max_duration,
    get_sfx_min_gap,
    get_sfx_volume,
    sfx_enabled,
)
from contentgenie.gpt.gpt_editing import find_anchor_time


SFX_DIR = Path("assets/sfx/library")

SFX_LIBRARY = {
    "riser": ["riser_air_01.ogg"],
    "whoosh": ["whoosh_air_02.ogg"],
    "impact": ["impact_hit_01.ogg", "pop_light_01.ogg"],
    "hit": ["impact_hit_01.ogg", "pop_light_01.ogg"],
    "reveal": ["reveal_bell_01.ogg", "pop_light_01.ogg"],
    "suspense": ["suspense_ambient_02.ogg"],
    "door": ["door_01.ogg"],
    "lock": ["lock_open_01.ogg"],
    "glass": ["glass_01.ogg"],
    "metal": ["metal_hit_01.ogg"],
    "thunder": ["thunder_01.ogg"],
    "footstep": ["footstep_wood_01.ogg"],
}

EFFECT_ALIASES = {
    "rise": "riser",
    "riser": "riser",
    "swell": "riser",
    "whoosh": "whoosh",
    "woosh": "whoosh",
    "swoosh": "whoosh",
    "impact": "impact",
    "hit": "hit",
    "pop": "impact",
    "sting": "reveal",
    "reveal": "reveal",
    "bell": "reveal",
    "suspense": "suspense",
    "tension": "suspense",
    "ambient": "suspense",
    "door": "door",
    "lock": "lock",
    "glass": "glass",
    "metal": "metal",
    "thunder": "thunder",
    "storm": "thunder",
    "footstep": "footstep",
    "steps": "footstep",
}

EFFECT_LEAD_SECONDS = {
    "riser": 0.35,
    "suspense": 0.15,
}

INTENSITY_VOLUME = {
    "low": 0.7,
    "medium": 1.0,
    "high": 1.2,
}

_DURATION_CACHE = {}


def _normalize_effect(effect):
    effect = str(effect or "").strip().lower().replace("_", " ").replace("-", " ")
    for token in effect.split():
        if token in EFFECT_ALIASES:
            return EFFECT_ALIASES[token]
    return EFFECT_ALIASES.get(effect, "impact")


def _variant_for(effect, cue):
    variants = SFX_LIBRARY.get(effect) or SFX_LIBRARY["impact"]
    seed = f"{cue.get('anchor_text', '')}:{cue.get('intensity', '')}:{effect}"
    return variants[abs(hash(seed)) % len(variants)]


def _duration(path):
    cache_key = str(path)
    if cache_key not in _DURATION_CACHE:
        _, duration = get_asset_duration(cache_key, isVideo=False)
        _DURATION_CACHE[cache_key] = float(duration)
    return _DURATION_CACHE[cache_key]


def resolve_sfx_cues(cues, timed_words, voiceover_duration):
    if not sfx_enabled() or not cues or not timed_words:
        return []

    max_cues = get_sfx_max_cues()
    max_duration = get_sfx_max_duration()
    min_gap = get_sfx_min_gap()
    base_volume = get_sfx_volume()
    resolved = []
    last_start = -999.0

    for cue in cues:
        if len(resolved) >= max_cues:
            break
        if not isinstance(cue, dict):
            continue

        anchor_text = str(cue.get("anchor_text") or cue.get("anchor") or "").strip()
        anchor_time = find_anchor_time(anchor_text, timed_words, allow_first_word_fallback=False)
        if anchor_time is None:
            continue

        effect = _normalize_effect(cue.get("effect") or cue.get("sound") or cue.get("type"))
        file_name = _variant_for(effect, cue)
        path = SFX_DIR / file_name
        if not path.exists():
            continue

        start = max(0.0, anchor_time - EFFECT_LEAD_SECONDS.get(effect, 0.0))
        if start - last_start < min_gap:
            continue

        duration = min(max_duration, _duration(path), max(0.0, float(voiceover_duration) - start))
        if duration <= 0:
            continue

        intensity = str(cue.get("intensity") or "medium").lower()
        volume = min(1.0, base_volume * INTENSITY_VOLUME.get(intensity, 1.0))
        resolved.append({
            "url": str(path),
            "set_time_start": start,
            "set_time_end": start + duration,
            "volume_percentage": volume,
        })
        last_start = start

    return resolved

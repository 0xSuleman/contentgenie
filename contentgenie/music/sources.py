from __future__ import annotations

import re

import requests

from contentgenie.music.models import MusicCandidate, normalized_music_license, normalize_music_direction


OPENVERSE_AUDIO_API = "https://api.openverse.org/v1/audio/"
REJECT_TERMS = {
    "a cappella", "acapella", "dialogue", "interview", "lyrics", "narration",
    "podcast", "rap vocal", "speech", "spoken word", "voice over", "vocal stem",
}
MUSIC_TERMS = {
    "ambient", "background", "beat", "cinematic", "documentary", "instrumental",
    "melody", "music", "orchestral", "piano", "score", "soundtrack", "synth",
}
MOOD_TERMS = {
    "curious": {"curious", "discovery", "documentary", "intrigue", "wonder"},
    "suspenseful": {"dark", "dramatic", "mystery", "suspense", "tension"},
    "uplifting": {"bright", "hopeful", "inspiring", "positive", "uplifting"},
    "reflective": {"ambient", "calm", "emotional", "piano", "reflective", "warm"},
    "playful": {"bouncy", "fun", "playful", "quirky", "whimsical"},
    "urgent": {"action", "driving", "energetic", "pulse", "urgent"},
    "wonder": {"atmospheric", "awe", "ethereal", "space", "wonder"},
    "neutral": {"ambient", "background", "documentary", "minimal"},
}


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", str(value or "").lower()))


def score_candidate(candidate: MusicCandidate, direction: dict, target_duration: float = 50, recently_used: set[str] | None = None) -> float:
    profile = normalize_music_direction(direction)
    title = candidate.title.lower()
    text = " ".join([candidate.title, *candidate.tags]).lower()
    tokens = _tokens(text)
    score = 0.0

    if any(term in text for term in REJECT_TERMS):
        score -= 100
    score += min(len(tokens & MUSIC_TERMS) * 3.0, 12.0)
    score += len(tokens & MOOD_TERMS[profile["mood"]]) * 4.0
    score += len(tokens & _tokens(profile["style"])) * 3.0
    for term in profile["search_terms"]:
        term_tokens = _tokens(term)
        score += len(tokens & term_tokens) * 2.5
        if term in text:
            score += 2.0

    if "instrumental" in text or "background" in text or "ambient" in text:
        score += 8
    if candidate.duration >= target_duration + 10:
        score += 8
    elif candidate.duration >= target_duration:
        score += 3
    else:
        score -= 15
    if 60 <= candidate.duration <= 360:
        score += 4
    if candidate.bit_rate >= 192000:
        score += 3
    elif candidate.bit_rate >= 128000:
        score += 1
    if candidate.provider.lower() == "jamendo":
        score += 2
    if candidate.license_name in {"CC0", "PUBLIC DOMAIN"}:
        score += 1
    if recently_used and candidate.key in recently_used:
        score -= 18
    if any(term in title for term in ("loop", "sting", "logo", "jingle")):
        score -= 8
    return round(score, 3)


class OpenverseMusicSource:
    def __init__(self, session=None):
        self.session = session or requests.Session()

    def search(self, direction: dict, target_duration: float = 50, limit: int = 40, recently_used: set[str] | None = None) -> list[MusicCandidate]:
        profile = normalize_music_direction(direction)
        query_parts = [profile["mood"], profile["style"], *profile["search_terms"][:2], "instrumental background music"]
        queries = [
            " ".join(dict.fromkeys(part for part in query_parts if part)),
            f"{profile['style']} instrumental",
            f"{profile['mood']} cinematic instrumental",
        ]
        raw_results = []
        seen_ids = set()
        for query in dict.fromkeys(queries):
            response = self.session.get(
                OPENVERSE_AUDIO_API,
                # Anonymous Openverse clients are capped at 20 results per request.
                # Staying inside that documented response keeps this feature key-free.
                params={"q": query, "license": "cc0,by", "page_size": min(max(limit, 1), 20)},
                timeout=(10, 35),
            )
            response.raise_for_status()
            for item in response.json().get("results") or []:
                identity = str(item.get("id") or "")
                if identity and identity not in seen_ids:
                    seen_ids.add(identity)
                    raw_results.append(item)
            if len(raw_results) >= limit:
                break
        candidates = []
        for item in raw_results:
            duration_ms = float(item.get("duration") or 0)
            tags = [str(tag.get("name") or "").lower() for tag in item.get("tags") or [] if isinstance(tag, dict)]
            license_name = normalized_music_license(
                str(item.get("license") or ""),
                str(item.get("license_url") or ""),
                str(item.get("license_version") or ""),
            )
            source_url = str(item.get("foreign_landing_url") or "")
            attribution = str(item.get("attribution") or "").strip()
            if source_url and source_url not in attribution:
                attribution = f"{attribution.rstrip('.')} — {source_url}"
            candidate = MusicCandidate(
                source_id=str(item.get("id") or ""),
                title=str(item.get("title") or "Untitled music").strip(),
                creator=str(item.get("creator") or "Unknown creator").strip(),
                source_url=source_url,
                download_url=str(item.get("url") or ""),
                license_name=license_name,
                license_url=str(item.get("license_url") or ""),
                attribution=attribution,
                provider=str(item.get("source") or item.get("provider") or "Openverse"),
                duration=duration_ms / 1000.0,
                file_size=int(item.get("filesize") or 0),
                file_type=str(item.get("filetype") or "mp3").lower(),
                bit_rate=int(item.get("bit_rate") or 0),
                tags=tags,
                mature=bool(item.get("mature")),
                raw_metadata={
                    "openverse_detail_url": item.get("detail_url"),
                    "indexed_on": item.get("indexed_on"),
                    "audio_set": item.get("audio_set"),
                },
            )
            candidate.match_score = score_candidate(candidate, profile, target_duration, recently_used)
            if candidate.auto_eligible and candidate.duration >= target_duration:
                candidates.append(candidate)
        return sorted(candidates, key=lambda item: (item.match_score, item.bit_rate, item.duration), reverse=True)

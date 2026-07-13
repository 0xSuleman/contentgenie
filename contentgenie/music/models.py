from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from contentgenie.footage.models import is_commercial_derivative_license, normalize_license


@dataclass
class MusicCandidate:
    source_id: str
    title: str
    creator: str
    source_url: str
    download_url: str
    license_name: str
    license_url: str
    attribution: str
    provider: str = "Openverse"
    duration: float = 0.0
    file_size: int = 0
    file_type: str = "mp3"
    bit_rate: int = 0
    tags: list[str] = field(default_factory=list)
    mature: bool = False
    match_score: float = 0.0
    raw_metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"openverse:{self.source_id}"

    @property
    def auto_eligible(self) -> bool:
        return (
            not self.mature
            and self.duration >= 30
            and self.download_url.startswith("https://")
            and self.source_url.startswith("https://")
            and is_commercial_derivative_license(self.license_name, self.license_url)
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["key"] = self.key
        data["auto_eligible"] = self.auto_eligible
        return data


def normalized_music_license(name: str, url: str, version: str = "") -> str:
    normalized = normalize_license(name, url)
    if normalized in {"CC0", "PUBLIC DOMAIN"}:
        return normalized
    if normalized == "CC BY":
        return f"CC BY {version}".strip()
    return normalized


def normalize_music_direction(direction: dict | None, tone: str = "") -> dict:
    direction = direction if isinstance(direction, dict) else {}
    tone_text = str(tone or "").lower()
    mood = str(direction.get("mood") or "").lower().strip()
    if mood not in {"curious", "suspenseful", "uplifting", "reflective", "playful", "urgent", "wonder", "neutral"}:
        if any(word in tone_text for word in ("suspense", "tense", "mystery")):
            mood = "suspenseful"
        elif any(word in tone_text for word in ("warm", "reflect")):
            mood = "reflective"
        elif any(word in tone_text for word in ("witty", "playful", "fun")):
            mood = "playful"
        else:
            mood = "curious"

    energy = str(direction.get("energy") or "medium").lower().strip()
    if energy not in {"low", "medium", "high"}:
        energy = "medium"

    style = str(direction.get("style") or "cinematic ambient").lower().strip()
    allowed_styles = {
        "cinematic ambient", "documentary", "electronic pulse", "acoustic",
        "orchestral", "lo-fi", "playful percussion", "minimal piano",
    }
    if style not in allowed_styles:
        style = "cinematic ambient"

    terms = []
    for value in direction.get("search_terms") or []:
        cleaned = " ".join(str(value).lower().split())
        if cleaned and cleaned not in terms:
            terms.append(cleaned[:40])
    return {
        "mood": mood,
        "energy": energy,
        "style": style,
        "search_terms": terms[:5],
    }

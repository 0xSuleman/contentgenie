from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class FootageCandidate:
    source: str
    source_id: str
    title: str
    creator: str
    source_url: str
    download_url: str
    license_name: str
    license_url: str
    attribution: str
    width: int = 0
    height: int = 0
    duration: float = 0.0
    file_size: int = 0
    style: str = "Mixed"
    rights_status: str = "unverified"
    policy_url: str = ""
    description: str = ""
    preliminary_score: float = 0.0
    raw_metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.source}:{self.source_id}"

    @property
    def resolution(self) -> str:
        if self.width and self.height:
            return f"{self.width}x{self.height}"
        return "unknown"

    @property
    def auto_eligible(self) -> bool:
        return self.rights_status == "verified" and is_commercial_derivative_license(
            self.license_name,
            self.license_url,
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["key"] = self.key
        data["resolution"] = self.resolution
        data["auto_eligible"] = self.auto_eligible
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FootageCandidate":
        fields = cls.__dataclass_fields__
        return cls(**{key: value for key, value in data.items() if key in fields})


def normalize_license(license_name: str = "", license_url: str = "") -> str:
    value = f"{license_name} {license_url}".lower().replace("_", " ")
    value = " ".join(value.split())
    if "creativecommons.org/publicdomain/zero" in value or "cc0" in value or "cc zero" in value:
        return "CC0"
    if "public domain" in value or "publicdomain" in value:
        return "PUBLIC DOMAIN"
    if "by-nc-nd" in value or "by nc nd" in value:
        return "CC BY-NC-ND"
    if "by-nc-sa" in value or "by nc sa" in value:
        return "CC BY-NC-SA"
    if "by-nc" in value or "by nc" in value:
        return "CC BY-NC"
    if "by-nd" in value or "by nd" in value:
        return "CC BY-ND"
    if "by-sa" in value or "by sa" in value:
        return "CC BY-SA"
    if "creativecommons.org/licenses/by/" in value or "cc by" in value or "creative commons attribution" in value:
        return "CC BY"
    return "UNKNOWN"


def is_commercial_derivative_license(license_name: str = "", license_url: str = "") -> bool:
    """Return true only for licenses safe for commercial edited output in strict mode."""
    return normalize_license(license_name, license_url) in {"CC0", "PUBLIC DOMAIN", "CC BY"}

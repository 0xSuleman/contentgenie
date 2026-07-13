from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

from contentgenie.audio.audio_duration import get_asset_duration
from contentgenie.config.asset_db import AssetDatabase, AssetType, AUDIO_EXTENSIONS
from contentgenie.music.models import MusicCandidate, normalize_music_direction
from contentgenie.music.sources import OpenverseMusicSource, score_candidate


MUSIC_DIR = Path("public/licensed_music")
EVIDENCE_DIR = Path(".editing_assets/licensed_music_evidence")
MAX_DOWNLOAD_BYTES = 80 * 1024 * 1024


def _safe_stem(value: str, maximum: int = 72) -> str:
    value = re.sub(r"[^a-zA-Z0-9 _-]+", "", value).strip()
    return (re.sub(r"\s+", "_", value) or "licensed_music")[:maximum].strip("_-")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class MusicService:
    def __init__(self, session=None):
        self.session = session or requests.Session()
        self.session.headers.setdefault(
            "User-Agent",
            "ContentGenie/1.0 (licensed-music discovery; local desktop application)",
        )
        self.source = OpenverseMusicSource(self.session)

    @staticmethod
    def _recent_source_keys(limit: int = 12) -> set[str]:
        keys = set()
        manifests = sorted(Path("videos").glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
        for path in manifests[:limit]:
            try:
                music = (json.loads(path.read_text(encoding="utf-8")).get("assets") or {}).get("licensed_music") or {}
                if music.get("source_key"):
                    keys.add(str(music["source_key"]))
            except (OSError, ValueError, TypeError):
                continue
        return keys

    def discover(self, direction: dict, target_duration: float = 50, limit: int = 40) -> list[MusicCandidate]:
        return self.source.search(
            direction=direction,
            target_duration=target_duration,
            limit=limit,
            recently_used=self._recent_source_keys(),
        )

    @staticmethod
    def _existing(candidate: MusicCandidate) -> dict | None:
        for asset in AssetDatabase.get_licensed_music_assets():
            if (asset.get("metadata") or {}).get("source_key") == candidate.key:
                return asset
        return None

    def _download(self, candidate: MusicCandidate, destination: Path):
        parsed = urlparse(candidate.download_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("Music download URL is not a secure public URL")
        temporary = destination.with_suffix(destination.suffix + ".download")
        try:
            with self.session.get(candidate.download_url, stream=True, timeout=(15, 120), allow_redirects=True) as response:
                response.raise_for_status()
                declared = int(response.headers.get("content-length") or 0)
                if declared and declared > MAX_DOWNLOAD_BYTES:
                    raise ValueError("Music file exceeds the automatic 80 MB download limit")
                content_type = str(response.headers.get("content-type") or "").lower()
                if content_type and "audio" not in content_type and "octet-stream" not in content_type:
                    raise ValueError(f"Music source returned an unexpected content type: {content_type}")
                written = 0
                with temporary.open("wb") as target:
                    for chunk in response.iter_content(chunk_size=256 * 1024):
                        if not chunk:
                            continue
                        written += len(chunk)
                        if written > MAX_DOWNLOAD_BYTES:
                            raise ValueError("Music file exceeded the automatic 80 MB download limit")
                        target.write(chunk)
            if written < 32 * 1024:
                raise ValueError("Downloaded music file is unexpectedly small")
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)

    def acquire(self, candidate: MusicCandidate, direction: dict, target_duration: float, logger=None) -> dict:
        if not candidate.auto_eligible:
            raise ValueError("Music did not pass the strict commercial-use and remix license gate")
        existing = self._existing(candidate)
        if existing:
            return existing

        MUSIC_DIR.mkdir(parents=True, exist_ok=True)
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        identity = hashlib.sha1(candidate.key.encode("utf-8")).hexdigest()[:10]
        extension = "." + re.sub(r"[^a-z0-9]", "", candidate.file_type.lower())
        if extension not in AUDIO_EXTENSIONS:
            extension = Path(urlparse(candidate.download_url).path).suffix.lower()
        if extension not in AUDIO_EXTENSIONS:
            extension = ".mp3"
        destination = MUSIC_DIR / f"{_safe_stem(candidate.title)}_{identity}{extension}"
        if logger:
            logger(f"Downloading script-matched CC music: {candidate.title}")
        try:
            self._download(candidate, destination)
            _, measured_duration = get_asset_duration(str(destination), isVideo=False)
            measured_duration = float(measured_duration or 0)
            if measured_duration < float(target_duration):
                raise ValueError("Downloaded music is shorter than the production")
            checksum = _sha256(destination)
            profile = normalize_music_direction(direction)
            evidence = {
                "schema_version": 1,
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "candidate": candidate.to_dict(),
                "music_direction": profile,
                "downloaded_file": str(destination),
                "checksum_sha256": checksum,
                "measured_duration_seconds": measured_duration,
            }
            evidence_path = EVIDENCE_DIR / f"{identity}.json"
            evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
            asset_name = f"Licensed Music · {candidate.title[:55]} · {identity}"
            metadata = {
                "licensed_music": True,
                "auto_eligible": True,
                "source": f"Openverse · {candidate.provider}",
                "source_key": candidate.key,
                "source_url": candidate.source_url,
                "creator": candidate.creator,
                "title": candidate.title,
                "license_name": candidate.license_name,
                "license_url": candidate.license_url,
                "attribution": candidate.attribution,
                "music_direction": profile,
                "tags": candidate.tags,
                "match_score": candidate.match_score,
                "duration": measured_duration,
                "checksum_sha256": checksum,
                "evidence_path": str(evidence_path),
            }
            AssetDatabase.add_local_asset(asset_name, AssetType.BACKGROUND_MUSIC, str(destination), metadata=metadata)
            return AssetDatabase.get_asset_record(asset_name) | {"name": asset_name}
        except Exception:
            destination.unlink(missing_ok=True)
            raise

    def _library_fallback(self, direction: dict, target_duration: float) -> dict | None:
        best = None
        best_score = float("-inf")
        recent = self._recent_source_keys()
        for asset in AssetDatabase.get_licensed_music_assets():
            metadata = asset.get("metadata") or {}
            candidate = MusicCandidate(
                source_id=str(metadata.get("source_key") or asset.get("name")),
                title=str(metadata.get("title") or asset.get("name") or "Licensed music"),
                creator=str(metadata.get("creator") or "Unknown creator"),
                source_url=str(metadata.get("source_url") or "https://openverse.org/"),
                download_url="https://cached.local/asset",
                license_name=str(metadata.get("license_name") or ""),
                license_url=str(metadata.get("license_url") or ""),
                attribution=str(metadata.get("attribution") or ""),
                duration=float(metadata.get("duration") or 0),
                tags=list(metadata.get("tags") or []),
            )
            score = score_candidate(candidate, direction, target_duration, recent)
            if score > best_score and candidate.duration >= target_duration:
                best, best_score = asset, score
        return best

    def select_for_script(self, script: str, direction: dict, target_duration: float = 50, logger=None) -> dict:
        profile = normalize_music_direction(direction)
        if logger:
            logger(f"Matching {profile['mood']} {profile['style']} music to the script...")
        try:
            candidates = self.discover(profile, target_duration=target_duration)
            if candidates:
                return self.acquire(candidates[0], profile, target_duration, logger=logger)
        except (requests.RequestException, ValueError, OSError) as error:
            if logger:
                logger(f"Online music discovery was unavailable; checking the licensed cache ({error})")
        fallback = self._library_fallback(profile, target_duration)
        if fallback:
            return fallback
        raise ValueError("No suitable CC0 or CC BY background track was found. Check the connection or add licensed music to the library.")

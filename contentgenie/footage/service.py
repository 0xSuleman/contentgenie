from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import requests
import yt_dlp

from contentgenie.config.api_db import ApiKeyManager
from contentgenie.config.asset_db import AssetDatabase, AssetType
from contentgenie.config.performance import get_ffmpeg_binary
from contentgenie.footage.analysis import analyze_video
from contentgenie.footage.models import FootageCandidate
from contentgenie.footage.montage import build_retention_montage
from contentgenie.footage.sources import (
    InternetArchiveSource,
    SOURCE_LABELS,
    WikimediaCommonsSource,
    YouTubeCreativeCommonsSource,
    source_names,
)


FOOTAGE_DIR = Path("public/licensed_footage")
EVIDENCE_DIR = Path(".editing_assets/licensed_footage_evidence")
MAX_DOWNLOAD_BYTES = 2 * 1024 * 1024 * 1024


def _safe_stem(value: str, maximum: int = 80) -> str:
    value = re.sub(r"[^a-zA-Z0-9 _-]+", "", value).strip()
    value = re.sub(r"\s+", "_", value)
    return (value or "licensed_gameplay")[:maximum].strip("_-")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class FootageService:
    def __init__(self, session=None, youtube_api_key: str | None = None):
        self.session = session or requests.Session()
        self.session.headers.setdefault(
            "User-Agent",
            "ContentGenie/1.0 (licensed-footage discovery; local desktop application)",
        )
        self.youtube_api_key = youtube_api_key if youtube_api_key is not None else ApiKeyManager.get_api_key("YOUTUBE_API_KEY")
        self.last_warnings: list[str] = []

    def _source(self, name: str):
        if name == "wikimedia":
            return WikimediaCommonsSource(self.session)
        if name == "youtube":
            return YouTubeCreativeCommonsSource(self.youtube_api_key, self.session)
        if name == "archive":
            return InternetArchiveSource(self.session)
        raise ValueError(f"Unknown footage source: {name}")

    def discover(
        self,
        style: str = "Mixed",
        sources: list[str] | None = None,
        query: str = "",
        limit: int = 40,
    ) -> list[FootageCandidate]:
        names = source_names(sources or ["wikimedia", "youtube"])
        self.last_warnings = []
        results = []
        for name in names:
            if name == "youtube" and not self.youtube_api_key:
                self.last_warnings.append("YouTube CC search is using the slower key-free metadata fallback; an API key improves discovery speed.")
            try:
                results.extend(self._source(name).search(style=style, query=query, limit=limit))
            except Exception as error:
                self.last_warnings.append(f"{SOURCE_LABELS[name]} search failed: {error}")
        unique = {}
        for candidate in results:
            existing = unique.get(candidate.key)
            if existing is None or candidate.preliminary_score > existing.preliminary_score:
                unique[candidate.key] = candidate
        return sorted(
            unique.values(),
            key=lambda item: (
                item.auto_eligible,
                item.preliminary_score,
                1 if 45 <= item.duration <= 900 else 0,
                -item.duration if item.duration else 0,
                item.width * item.height,
            ),
            reverse=True,
        )[:limit]

    def _download_direct(self, candidate: FootageCandidate, destination: Path) -> Path:
        with self.session.get(candidate.download_url, stream=True, timeout=(15, 180), allow_redirects=True) as response:
            response.raise_for_status()
            declared_size = int(response.headers.get("content-length") or 0)
            if declared_size and declared_size > MAX_DOWNLOAD_BYTES:
                raise ValueError(f"Source is too large to download automatically ({declared_size / 1024**3:.1f} GB)")
            written = 0
            with destination.open("wb") as target:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    written += len(chunk)
                    if written > MAX_DOWNLOAD_BYTES:
                        raise ValueError("Source exceeded the automatic 2 GB download limit")
                    target.write(chunk)
        return destination

    def _download_youtube(self, candidate: FootageCandidate, destination_stem: Path) -> Path:
        ffmpeg_path = Path(get_ffmpeg_binary())
        options = {
            "quiet": True,
            "no_warnings": True,
            "no_color": True,
            "noprogress": True,
            "no_call_home": True,
            "noplaylist": True,
            "format": "bestvideo[width<=1920][height<=1920]/best[width<=1920][height<=1920]",
            "merge_output_format": "mp4",
            "outtmpl": str(destination_stem) + ".%(ext)s",
            "ffmpeg_location": str(ffmpeg_path.parent),
        }
        with yt_dlp.YoutubeDL(options) as downloader:
            downloader.extract_info(candidate.download_url, download=True)
        matches = sorted(destination_stem.parent.glob(destination_stem.name + ".*"), key=lambda item: item.stat().st_mtime, reverse=True)
        video_matches = [item for item in matches if item.suffix.lower() in {".mp4", ".webm", ".mkv", ".mov"}]
        if not video_matches:
            raise ValueError("YouTube CC download did not produce a readable video file")
        return video_matches[0]

    def _existing_candidate_asset(self, candidate: FootageCandidate) -> dict | None:
        for asset in AssetDatabase.get_licensed_footage_assets():
            metadata = asset.get("metadata") or {}
            if metadata.get("source_key") == candidate.key:
                return asset
        return None

    def acquire(self, candidate: FootageCandidate, logger=None) -> dict:
        if not candidate.auto_eligible:
            raise ValueError("This result did not pass the strict commercial license and game-rights gate")
        existing = self._existing_candidate_asset(candidate)
        if existing:
            return existing
        FOOTAGE_DIR.mkdir(parents=True, exist_ok=True)
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        stem = _safe_stem(candidate.title)
        identity = hashlib.sha1(candidate.key.encode("utf-8")).hexdigest()[:10]
        destination_stem = FOOTAGE_DIR / f"{stem}_{identity}"
        temporary = destination_stem.with_suffix(".download")
        if logger:
            logger(f"Downloading licensed gameplay: {candidate.title}")
        try:
            if candidate.source == "youtube":
                downloaded = self._download_youtube(candidate, destination_stem)
            else:
                extension = Path(candidate.download_url.split("?", 1)[0]).suffix.lower()
                if extension not in {".mp4", ".webm", ".ogv", ".mkv", ".mov"}:
                    extension = ".mp4"
                temporary = destination_stem.with_suffix(extension + ".download")
                self._download_direct(candidate, temporary)
                downloaded = destination_stem.with_suffix(extension)
                if downloaded.exists():
                    downloaded.unlink()
                os.replace(temporary, downloaded)

            if logger:
                logger(f"Analyzing motion and visual quality: {candidate.title}")
            analysis = analyze_video(str(downloaded))
            if analysis["width"] < 960 or analysis["height"] < 540:
                raise ValueError(f"Downloaded footage is below the 960x540 quality floor: {analysis['width']}x{analysis['height']}")
            if analysis["duration"] < 15:
                raise ValueError("Downloaded footage is too short for the automatic library")
            checksum = analysis.get("checksum_sha256") or _sha256(downloaded)
            candidate.width = analysis["width"]
            candidate.height = analysis["height"]
            candidate.duration = analysis["duration"]
            evidence = {
                "schema_version": 1,
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "candidate": candidate.to_dict(),
                "downloaded_file": str(downloaded),
                "checksum_sha256": checksum,
                "analysis_summary": analysis.get("quality") or {},
                "analysis_version": analysis.get("analysis_version"),
                "score_model_version": analysis.get("score_model_version"),
            }
            evidence_path = EVIDENCE_DIR / f"{identity}.json"
            evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")

            asset_name = f"Licensed {candidate.style} {identity}"
            metadata = {
                "licensed_footage": True,
                "auto_eligible": True,
                "source": candidate.source,
                "source_key": candidate.key,
                "source_url": candidate.source_url,
                "creator": candidate.creator,
                "title": candidate.title,
                "license_name": candidate.license_name,
                "license_url": candidate.license_url,
                "attribution": candidate.attribution,
                "policy_url": candidate.policy_url,
                "rights_status": candidate.rights_status,
                "style": candidate.style,
                "checksum_sha256": checksum,
                "evidence_path": str(evidence_path),
                "analysis_quality": analysis.get("quality") or {},
                "analysis_version": analysis.get("analysis_version"),
                "score_model_version": analysis.get("score_model_version"),
                "duration": analysis["duration"],
                "width": analysis["width"],
                "height": analysis["height"],
            }
            AssetDatabase.add_local_asset(asset_name, AssetType.BACKGROUND_VIDEO, str(downloaded), metadata=metadata)
            return AssetDatabase.get_asset_record(asset_name) | {"name": asset_name}
        except Exception:
            for path in [temporary, *destination_stem.parent.glob(destination_stem.name + ".*")]:
                try:
                    if path.exists() and path.suffix not in {".json"}:
                        path.unlink()
                except OSError:
                    pass
            raise

    def library_assets(self, style: str = "Mixed", allowed_sources: set[str] | None = None) -> list[dict]:
        results = []
        for asset in AssetDatabase.get_licensed_footage_assets():
            metadata = asset.get("metadata") or {}
            if allowed_sources is not None and metadata.get("source") not in allowed_sources:
                continue
            if style != "Mixed" and metadata.get("style") != style:
                continue
            try:
                analysis = analyze_video(asset["path"])
            except Exception:
                continue
            if (
                metadata.get("analysis_version") != analysis.get("analysis_version")
                or metadata.get("score_model_version") != analysis.get("score_model_version")
            ):
                metadata.update({
                    "analysis_quality": analysis.get("quality") or {},
                    "analysis_version": analysis.get("analysis_version"),
                    "score_model_version": analysis.get("score_model_version"),
                    "duration": analysis.get("duration"),
                    "width": analysis.get("width"),
                    "height": analysis.get("height"),
                })
                evidence_path = Path(metadata.get("evidence_path") or "")
                if evidence_path.exists():
                    try:
                        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
                        evidence["analysis_summary"] = analysis.get("quality") or {}
                        evidence["analysis_version"] = analysis.get("analysis_version")
                        evidence["score_model_version"] = analysis.get("score_model_version")
                        evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
                    except (OSError, ValueError):
                        pass
                AssetDatabase.add_local_asset(
                    asset["name"],
                    AssetType.BACKGROUND_VIDEO,
                    asset["path"],
                    metadata=metadata,
                )
            results.append({
                "name": asset["name"],
                "path": asset["path"],
                "duration": analysis.get("duration"),
                "analysis": analysis,
                "source_key": metadata.get("source_key") or asset["name"],
                "provenance": metadata,
            })
        return sorted(
            results,
            key=lambda item: float((item["analysis"].get("quality") or {}).get("retention_score") or 0),
            reverse=True,
        )

    def ensure_library(
        self,
        style: str = "Mixed",
        allow_youtube: bool = True,
        allow_archive: bool = False,
        minimum_assets: int = 2,
        logger=None,
    ) -> list[dict]:
        sources = ["wikimedia"]
        if allow_youtube:
            sources.append("youtube")
        if allow_archive:
            sources.append("archive")
        # Previously reviewed Archive assets remain eligible even when slow live
        # Archive discovery is not enabled for this generation run.
        allowed_sources = set(sources) | {"archive"}
        assets = self.library_assets(style, allowed_sources=allowed_sources)
        if len(assets) >= minimum_assets:
            return assets
        candidates = self.discover(style=style, sources=sources, limit=40)
        errors = []
        for candidate in candidates:
            if len(assets) >= minimum_assets:
                break
            try:
                self.acquire(candidate, logger=logger)
                assets = self.library_assets(style, allowed_sources=allowed_sources)
            except Exception as error:
                errors.append(f"{candidate.title}: {error}")
        if not assets and style != "Mixed":
            return self.ensure_library(
                style="Mixed",
                allow_youtube=allow_youtube,
                allow_archive=allow_archive,
                minimum_assets=minimum_assets,
                logger=logger,
            )
        if not assets:
            details = "; ".join([*self.last_warnings, *errors[:4]])
            raise ValueError(
                "No automatically eligible gameplay could be acquired. "
                "Add a free YouTube Data API key or download an approved result in the Asset Library."
                + (f" Details: {details}" if details else "")
            )
        return assets

    def create_background(
        self,
        target_duration: float,
        output_path: str,
        style: str = "Mixed",
        intensity: str = "High",
        allow_youtube: bool = True,
        avoid_recent: bool = True,
        content_id: str = "",
        logger=None,
        preferred_cut_times: list[float] | None = None,
    ) -> tuple[str, list[dict]]:
        assets = self.ensure_library(style, allow_youtube, minimum_assets=2, logger=logger)
        return build_retention_montage(
            assets,
            target_duration=target_duration,
            output_path=output_path,
            intensity=intensity,
            avoid_recent=avoid_recent,
            content_id=content_id,
            logger=logger,
            preferred_cut_times=preferred_cut_times,
        )

    @staticmethod
    def attribution_lines(segments: list[dict]) -> list[str]:
        unique = {}
        for segment in segments or []:
            provenance = segment.get("provenance") or {}
            source_key = segment.get("source_key") or provenance.get("source_key")
            attribution = provenance.get("attribution")
            if source_key and attribution:
                unique[source_key] = attribution
        return list(unique.values())

    @staticmethod
    def candidate_rows(candidates: list[FootageCandidate]) -> list[dict]:
        return [
            {
                "title": item.title,
                "source": SOURCE_LABELS.get(item.source, item.source),
                "license": item.license_name,
                "resolution": item.resolution,
                "duration_seconds": round(item.duration, 1) if item.duration else "unknown",
                "style": item.style,
                "rights": item.rights_status,
                "eligible": "yes" if item.auto_eligible else "no",
                "quality_score": round(item.preliminary_score, 1),
            }
            for item in candidates
        ]

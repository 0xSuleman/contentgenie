from __future__ import annotations

import html
import math
import re
from datetime import datetime, timezone
from typing import Iterable
from urllib.parse import quote

import requests
import yt_dlp

from contentgenie.footage.models import (
    FootageCandidate,
    is_commercial_derivative_license,
    normalize_license,
)

WIKIMEDIA_API = "https://commons.wikimedia.org/w/api.php"
YOUTUBE_API = "https://www.googleapis.com/youtube/v3"
ARCHIVE_SEARCH_API = "https://archive.org/advancedsearch.php"
ARCHIVE_METADATA_API = "https://archive.org/metadata"

MINECRAFT_POLICY_URL = "https://www.minecraft.net/en-us/usage-guidelines"
UBISOFT_POLICY_URL = "https://www.ubisoft.com/legal/documents/videopolicy/en-INTL"
CAPCOM_POLICY_URL = "https://www.capcomusa.com/video-policy/"

SOURCE_LABELS = {
    "wikimedia": "Wikimedia Commons",
    "youtube": "YouTube Creative Commons",
    "archive": "Internet Archive",
}

STYLE_QUERIES = {
    "Mixed": [
        "minecraft parkour gameplay no commentary",
        "minecraft satisfying gameplay no commentary",
        "minecraft obstacle course gameplay no commentary",
    ],
    "Parkour": ["minecraft parkour gameplay no commentary", "minecraft obstacle course gameplay"],
    "Racing": ["minecraft racing gameplay no commentary", "minecraft boat racing gameplay"],
    "Satisfying": ["minecraft satisfying building gameplay", "minecraft parkour satisfying gameplay"],
    "Action": ["minecraft action parkour gameplay", "minecraft speedrun movement gameplay"],
}

REJECT_TITLE_TERMS = {
    "trailer",
    "soundtrack",
    "music video",
    "cutscene",
    "cinematic",
    "reaction",
    "facecam",
    "review",
}


class _SilentYtdlpLogger:
    def debug(self, _message):
        pass

    def warning(self, _message):
        pass

    def error(self, _message):
        pass


def _text(value) -> str:
    if isinstance(value, dict):
        value = value.get("value", "")
    value = html.unescape(str(value or ""))
    return re.sub(r"<[^>]+>", " ", value).replace("\n", " ").strip()


def _duration_seconds(value: str) -> float:
    match = re.fullmatch(r"P(?:(\d+)D)?T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?", value or "")
    if not match:
        return 0.0
    days, hours, minutes, seconds = match.groups()
    return (
        float(days or 0) * 86400
        + float(hours or 0) * 3600
        + float(minutes or 0) * 60
        + float(seconds or 0)
    )


def _infer_style(text: str) -> str:
    text = text.lower()
    if any(term in text for term in ("parkour", "obstacle", "jump", "runner")):
        return "Parkour"
    if any(term in text for term in ("race", "racing", "drift", "kart", "car", "driving")):
        return "Racing"
    if any(term in text for term in ("build", "satisf", "restore", "craft", "construction")):
        return "Satisfying"
    if any(term in text for term in ("fight", "action", "shooter", "combat", "speedrun")):
        return "Action"
    return "Mixed"


def _publisher_policy(text: str) -> tuple[str, str]:
    lowered = text.lower()
    if "minecraft" in lowered or "mojang" in lowered:
        return "verified", MINECRAFT_POLICY_URL
    if any(game in lowered for game in ("0 a.d.", "0 ad ", "xonotic", "freedoom", "supertux", "tux racer")):
        return "verified", "open-game repository metadata"
    if any(game in lowered for game in ("assassin's creed", "trackmania", "far cry", "watch dogs")):
        return "verified", UBISOFT_POLICY_URL
    if any(game in lowered for game in ("resident evil", "street fighter", "monster hunter", "devil may cry")):
        return "verified", CAPCOM_POLICY_URL
    return "unverified", ""


def _preliminary_score(width: int, height: int, duration: float, title: str, file_size: int = 0) -> float:
    score = 0.0
    if width >= 1920 and height >= 1080:
        score += 30
    elif width >= 1280 and height >= 720:
        score += 20
    elif width >= 960 and height >= 540:
        score += 10
    if duration >= 120:
        score += 25
    elif duration >= 45:
        score += 18
    elif duration >= 15:
        score += 8
    if 60 <= duration <= 1200:
        score += 10
    elif duration > 7200:
        score -= 12
    style = _infer_style(title)
    score += {"Parkour": 25, "Racing": 22, "Satisfying": 20, "Action": 18}.get(style, 10)
    if file_size and file_size <= 500 * 1024 * 1024:
        score += 8
    return min(score, 100.0)


class WikimediaCommonsSource:
    name = "wikimedia"

    def __init__(self, session=None):
        self.session = session or requests.Session()

    def _category_files(self, category: str, max_depth: int = 2, limit: int = 300) -> list[str]:
        queue = [(category, 0)]
        seen_categories = set()
        files = []
        while queue and len(files) < limit:
            current, depth = queue.pop(0)
            if current in seen_categories:
                continue
            seen_categories.add(current)
            continuation = None
            while len(files) < limit:
                params = {
                    "action": "query",
                    "format": "json",
                    "formatversion": 2,
                    "list": "categorymembers",
                    "cmtitle": current,
                    "cmtype": "file|subcat",
                    "cmlimit": 100,
                }
                if continuation:
                    params["cmcontinue"] = continuation
                response = self.session.get(WIKIMEDIA_API, params=params, timeout=(10, 45))
                response.raise_for_status()
                payload = response.json()
                for member in payload.get("query", {}).get("categorymembers", []):
                    title = member.get("title", "")
                    if member.get("ns") == 14 and depth < max_depth:
                        queue.append((title, depth + 1))
                    elif member.get("ns") == 6 and title.lower().endswith((".webm", ".ogv", ".mp4")):
                        files.append(title)
                continuation = payload.get("continue", {}).get("cmcontinue")
                if not continuation:
                    break
        return files[:limit]

    def search(self, style: str = "Mixed", query: str = "", limit: int = 40) -> list[FootageCandidate]:
        titles = self._category_files("Category:Videos of video game gameplay", limit=max(limit * 5, 120))
        candidates = []
        for offset in range(0, len(titles), 40):
            params = {
                "action": "query",
                "format": "json",
                "formatversion": 2,
                "prop": "imageinfo",
                "titles": "|".join(titles[offset : offset + 40]),
                "iiprop": "url|mime|size|extmetadata",
            }
            response = self.session.get(WIKIMEDIA_API, params=params, timeout=(10, 60))
            response.raise_for_status()
            for page in response.json().get("query", {}).get("pages", []):
                info = (page.get("imageinfo") or [{}])[0]
                meta = info.get("extmetadata") or {}
                license_name = _text(meta.get("LicenseShortName"))
                license_url = _text(meta.get("LicenseUrl"))
                if not is_commercial_derivative_license(license_name, license_url):
                    continue
                title = page.get("title", "").removeprefix("File:")
                searchable = f"{title} {_text(meta.get('ImageDescription'))}"
                if query and query.lower() not in searchable.lower():
                    continue
                inferred_style = _infer_style(searchable)
                if style != "Mixed" and inferred_style != style:
                    continue
                rights_status, policy_url = _publisher_policy(searchable)
                creator = _text(meta.get("Artist")) or "Wikimedia Commons contributor"
                source_url = info.get("descriptionurl") or f"https://commons.wikimedia.org/wiki/{quote(page.get('title', ''))}"
                width = int(info.get("width") or 0)
                height = int(info.get("height") or 0)
                file_size = int(info.get("size") or 0)
                candidate = FootageCandidate(
                    source=self.name,
                    source_id=str(page.get("pageid") or title),
                    title=title,
                    creator=creator,
                    source_url=source_url,
                    download_url=info.get("url", ""),
                    license_name=normalize_license(license_name, license_url),
                    license_url=license_url,
                    attribution=f'"{title}" by {creator}, {normalize_license(license_name, license_url)}, {source_url}',
                    width=width,
                    height=height,
                    file_size=file_size,
                    style=inferred_style,
                    rights_status=rights_status,
                    policy_url=policy_url,
                    description=_text(meta.get("ImageDescription")),
                    preliminary_score=_preliminary_score(width, height, 0, searchable, file_size),
                    raw_metadata={
                        "retrieved_at": datetime.now(timezone.utc).isoformat(),
                        "page": page,
                    },
                )
                if candidate.download_url and width >= 960 and height >= 540:
                    candidates.append(candidate)
        return sorted(candidates, key=lambda item: (item.auto_eligible, item.preliminary_score), reverse=True)[:limit]


class YouTubeCreativeCommonsSource:
    name = "youtube"

    def __init__(self, api_key: str, session=None):
        self.api_key = api_key
        self.session = session or requests.Session()

    def search(self, style: str = "Mixed", query: str = "", limit: int = 30) -> list[FootageCandidate]:
        if not self.api_key:
            return self._search_without_api(style=style, query=query, limit=limit)
        queries = [query] if query else STYLE_QUERIES.get(style, STYLE_QUERIES["Mixed"])
        ids = []
        snippets = {}
        for search_query in queries:
            params = {
                "key": self.api_key,
                "part": "snippet",
                "type": "video",
                "q": search_query,
                "maxResults": min(max(limit, 10), 50),
                "videoLicense": "creativeCommon",
                "videoDefinition": "high",
                "safeSearch": "strict",
                "relevanceLanguage": "en",
                "order": "relevance",
            }
            response = self.session.get(f"{YOUTUBE_API}/search", params=params, timeout=(10, 45))
            response.raise_for_status()
            for item in response.json().get("items", []):
                video_id = item.get("id", {}).get("videoId")
                if video_id and video_id not in snippets:
                    ids.append(video_id)
                    snippets[video_id] = item.get("snippet") or {}
            if len(ids) >= limit * 2:
                break
        candidates = []
        for offset in range(0, len(ids), 50):
            params = {
                "key": self.api_key,
                "part": "snippet,contentDetails,status,statistics",
                "id": ",".join(ids[offset : offset + 50]),
                "maxResults": 50,
            }
            response = self.session.get(f"{YOUTUBE_API}/videos", params=params, timeout=(10, 45))
            response.raise_for_status()
            for item in response.json().get("items", []):
                status = item.get("status") or {}
                snippet = item.get("snippet") or snippets.get(item.get("id"), {})
                title = _text(snippet.get("title"))
                description = _text(snippet.get("description"))
                if status.get("license") != "creativeCommon" or status.get("privacyStatus") != "public":
                    continue
                if any(term in title.lower() for term in REJECT_TITLE_TERMS):
                    continue
                searchable = f"{title} {description}"
                rights_status, policy_url = _publisher_policy(searchable)
                if rights_status != "verified":
                    continue
                duration = _duration_seconds((item.get("contentDetails") or {}).get("duration", ""))
                if duration < 20:
                    continue
                video_id = item.get("id", "")
                source_url = f"https://www.youtube.com/watch?v={video_id}"
                inferred_style = _infer_style(searchable)
                if style != "Mixed" and inferred_style != style:
                    continue
                candidate = FootageCandidate(
                    source=self.name,
                    source_id=video_id,
                    title=title,
                    creator=_text(snippet.get("channelTitle")) or "YouTube creator",
                    source_url=source_url,
                    download_url=source_url,
                    license_name="CC BY 3.0",
                    license_url="https://creativecommons.org/licenses/by/3.0/",
                    attribution=f'"{title}" by {_text(snippet.get("channelTitle")) or "YouTube creator"}, CC BY 3.0, {source_url}',
                    duration=duration,
                    style=inferred_style,
                    rights_status=rights_status,
                    policy_url=policy_url,
                    description=description,
                    preliminary_score=_preliminary_score(1920, 1080, duration, searchable),
                    raw_metadata={
                        "retrieved_at": datetime.now(timezone.utc).isoformat(),
                        "video_resource": item,
                    },
                )
                candidates.append(candidate)
        return sorted(candidates, key=lambda item: item.preliminary_score, reverse=True)[:limit]

    def _search_without_api(self, style: str = "Mixed", query: str = "", limit: int = 30) -> list[FootageCandidate]:
        """Key-free fallback that still verifies the per-video CC license metadata."""
        queries = [query] if query else STYLE_QUERIES.get(style, STYLE_QUERIES["Mixed"])
        candidates = []
        options = {
            "quiet": True,
            "no_warnings": True,
            "no_color": True,
            "skip_download": True,
            "socket_timeout": 30,
            "noplaylist": True,
            "ignoreerrors": True,
            "logger": _SilentYtdlpLogger(),
        }
        with yt_dlp.YoutubeDL(options) as downloader:
            for search_query in queries:
                per_query_limit = min(12, max(6, math.ceil(limit / max(len(queries), 1)) + 2))
                payload = downloader.extract_info(
                    f"ytsearch{per_query_limit}:{search_query}",
                    download=False,
                )
                for item in payload.get("entries", []) if payload else []:
                    if not item:
                        continue
                    license_text = _text(item.get("license"))
                    if "creative commons attribution" not in license_text.lower():
                        continue
                    title = _text(item.get("title"))
                    description = _text(item.get("description"))
                    if any(term in title.lower() for term in REJECT_TITLE_TERMS):
                        continue
                    searchable = f"{title} {description}"
                    rights_status, policy_url = _publisher_policy(searchable)
                    if rights_status != "verified":
                        continue
                    inferred_style = _infer_style(searchable)
                    if style != "Mixed" and inferred_style != style:
                        continue
                    formats = [fmt for fmt in (item.get("formats") or []) if fmt.get("vcodec") not in {None, "none"}]
                    width = max((int(fmt.get("width") or 0) for fmt in formats), default=int(item.get("width") or 0))
                    height = max((int(fmt.get("height") or 0) for fmt in formats), default=int(item.get("height") or 0))
                    if width < 960 or height < 540:
                        continue
                    duration = float(item.get("duration") or 0)
                    if duration < 20:
                        continue
                    video_id = _text(item.get("id"))
                    source_url = item.get("webpage_url") or f"https://www.youtube.com/watch?v={video_id}"
                    creator = _text(item.get("channel") or item.get("uploader")) or "YouTube creator"
                    candidates.append(FootageCandidate(
                        source=self.name,
                        source_id=video_id,
                        title=title,
                        creator=creator,
                        source_url=source_url,
                        download_url=source_url,
                        license_name="CC BY 3.0",
                        license_url="https://creativecommons.org/licenses/by/3.0/",
                        attribution=f'"{title}" by {creator}, CC BY 3.0, {source_url}',
                        width=width,
                        height=height,
                        duration=duration,
                        style=inferred_style,
                        rights_status=rights_status,
                        policy_url=policy_url,
                        description=description,
                        preliminary_score=_preliminary_score(width, height, duration, searchable),
                        raw_metadata={
                            "retrieved_at": datetime.now(timezone.utc).isoformat(),
                            "extractor": "yt-dlp key-free metadata fallback",
                            "license_reported": license_text,
                            "channel_id": item.get("channel_id"),
                            "upload_date": item.get("upload_date"),
                        },
                    ))
                if len(candidates) >= limit:
                    break
        unique = {item.key: item for item in candidates}
        return sorted(unique.values(), key=lambda item: item.preliminary_score, reverse=True)[:limit]


class InternetArchiveSource:
    name = "archive"

    def __init__(self, session=None):
        self.session = session or requests.Session()

    def search(self, style: str = "Mixed", query: str = "", limit: int = 20) -> list[FootageCandidate]:
        keywords = query or "gameplay open source game"
        search_query = (
            f'mediatype:movies AND ({keywords}) AND '
            '(licenseurl:*creativecommons.org/licenses/by/* OR licenseurl:*publicdomain*)'
        )
        params = {
            "q": search_query,
            "fl[]": ["identifier", "title", "creator", "description", "licenseurl"],
            "rows": min(max(limit * 3, 20), 100),
            "page": 1,
            "output": "json",
        }
        response = self.session.get(ARCHIVE_SEARCH_API, params=params, timeout=(10, 60))
        response.raise_for_status()
        candidates = []
        for doc in response.json().get("response", {}).get("docs", []):
            identifier = _text(doc.get("identifier"))
            if not identifier:
                continue
            metadata_response = self.session.get(f"{ARCHIVE_METADATA_API}/{quote(identifier)}", timeout=(10, 60))
            metadata_response.raise_for_status()
            payload = metadata_response.json()
            metadata = payload.get("metadata") or {}
            license_url = _text(metadata.get("licenseurl") or doc.get("licenseurl"))
            license_name = normalize_license(_text(metadata.get("rights")), license_url)
            if not is_commercial_derivative_license(license_name, license_url):
                continue
            title = _text(metadata.get("title") or doc.get("title") or identifier)
            description = _text(metadata.get("description") or doc.get("description"))
            searchable = f"{title} {description}"
            rights_status, policy_url = _publisher_policy(searchable)
            if rights_status != "verified":
                continue
            files = payload.get("files") or []
            video_files = [
                item for item in files
                if str(item.get("name", "")).lower().endswith((".mp4", ".webm", ".ogv"))
                and item.get("source", "original") == "original"
            ]
            if not video_files:
                continue
            video_file = sorted(video_files, key=lambda item: int(item.get("size") or 0), reverse=True)[0]
            filename = video_file.get("name", "")
            creator = _text(metadata.get("creator") or doc.get("creator")) or "Internet Archive contributor"
            source_url = f"https://archive.org/details/{quote(identifier)}"
            candidate = FootageCandidate(
                source=self.name,
                source_id=identifier,
                title=title,
                creator=creator,
                source_url=source_url,
                download_url=f"https://archive.org/download/{quote(identifier)}/{quote(filename)}",
                license_name=license_name,
                license_url=license_url,
                attribution=f'"{title}" by {creator}, {license_name}, {source_url}',
                file_size=int(video_file.get("size") or 0),
                style=_infer_style(searchable),
                rights_status=rights_status,
                policy_url=policy_url,
                description=description,
                preliminary_score=_preliminary_score(0, 0, 0, searchable, int(video_file.get("size") or 0)),
                raw_metadata={
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    "metadata": metadata,
                    "file": video_file,
                },
            )
            if style == "Mixed" or candidate.style == style:
                candidates.append(candidate)
        return sorted(candidates, key=lambda item: item.preliminary_score, reverse=True)[:limit]


def source_names(values: Iterable[str]) -> list[str]:
    normalized = []
    for value in values or []:
        lowered = str(value).lower()
        for key, label in SOURCE_LABELS.items():
            if lowered in {key, label.lower()} and key not in normalized:
                normalized.append(key)
    return normalized

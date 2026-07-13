from __future__ import annotations

import datetime
import hashlib
import json
import re
import shutil
import threading
import time
import traceback
import uuid
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from contentgenie.config.api_db import ApiKeyManager
from contentgenie.config.asset_db import AssetDatabase, AssetType
from contentgenie.footage.models import FootageCandidate
from contentgenie.footage.service import FootageService


app = FastAPI(title="ContentGenie API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:3000", "http://localhost:3000", "http://127.0.0.1:31415"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ALLOWED_FILE_ROOTS = tuple(Path(name).resolve() for name in ("public", "videos", ".editing_assets"))
PRODUCTIONS_ROOT = Path("videos").resolve()
SETTINGS_KEYS = (
    "GEMINI_API_KEY", "HUGGINGFACE_TOKEN", "YOUTUBE_API_KEY", "IMAGE_PROVIDER",
    "SHORT_VISUAL_STYLE_PROMPT", "SHORT_CAPTION_STYLE", "SHORT_CAPTION_POSITION",
    "SHORT_CAPTION_FONT_SIZE", "SHORT_BACKGROUND_MUSIC_VOLUME", "SHORT_SFX_ENABLED",
    "SHORT_SFX_VOLUME", "SHORT_SFX_MAX_CUES",
)


class SettingsPayload(BaseModel):
    values: dict[str, str | int | float | bool]


class DiscoveryPayload(BaseModel):
    style: str = "Mixed"
    sources: list[str] = Field(default_factory=lambda: ["wikimedia", "youtube"])
    query: str = ""


class AcquirePayload(BaseModel):
    candidate: dict


class CreatePayload(BaseModel):
    quantity: int = Field(default=1, ge=1, le=10)
    content_format: Literal["reddit", "history", "science", "custom"] = "reddit"
    subject: str = ""
    creative_brief: str = ""
    target_duration: int = Field(default=50, ge=30, le=58)
    audience: str = "General audience"
    tone: str = "Cinematic and curious"
    creator_angle: str = "Explain why this matters to viewers today with a clear original takeaway."
    quality_mode: Literal["production", "draft"] = "production"
    voice_persona: str = "The Energetic Co-Host"
    use_images: bool = True
    image_count: int = Field(default=10, ge=0, le=25)
    watermark: str = ""
    footage_mode: Literal["automatic", "manual"] = "automatic"
    footage_style: str = "Mixed"
    footage_intensity: str = "High"
    allow_youtube_cc: bool = True
    avoid_recent_footage: bool = True
    background_video: str = ""
    music_mode: Literal["automatic", "manual"] = "automatic"
    background_music: str = ""
    rights_confirmed: bool = False


class JobStore:
    def __init__(self):
        self.jobs: dict[str, dict] = {}
        self.lock = threading.RLock()

    def create(self, payload: CreatePayload) -> dict:
        job_id = uuid.uuid4().hex
        now = time.time()
        job = {
            "id": job_id,
            "status": "queued",
            "progress": 0,
            "stage": "Queued for production",
            "current_short": 0,
            "quantity": payload.quantity,
            "started_at": now,
            "updated_at": now,
            "outputs": [],
            "error": None,
            "cancel_requested": False,
        }
        with self.lock:
            self.jobs[job_id] = job
        return dict(job)

    def update(self, job_id: str, **values):
        with self.lock:
            if job_id not in self.jobs:
                return
            self.jobs[job_id].update(values, updated_at=time.time())

    def get(self, job_id: str) -> dict | None:
        with self.lock:
            job = self.jobs.get(job_id)
            return dict(job) if job else None


JOBS = JobStore()


def _production_id(video_path: Path) -> str:
    return hashlib.sha256(video_path.name.encode("utf-8")).hexdigest()[:16]


def _legacy_title(video_path: Path) -> str:
    title = re.sub(
        r"^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}(?:_[0-9a-fA-F]{8})?\s*-\s*",
        "",
        video_path.stem,
    )
    return title.strip(" ._-") or "ContentGenie Short"


def _read_manifest(video_path: Path) -> tuple[Path | None, dict]:
    manifest_path = video_path.with_suffix(".json")
    if not manifest_path.is_file():
        return None, {}
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        return manifest_path, data if isinstance(data, dict) else {}
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return manifest_path, {}


def _production_record(video_path: Path) -> dict:
    manifest_path, manifest = _read_manifest(video_path)
    youtube = manifest.get("youtube") or {}
    quality = manifest.get("quality_report") or {}
    video_quality = manifest.get("video_quality_report") or {}
    metrics = video_quality.get("metrics") or {}
    sources = manifest.get("research_sources") or []
    stat = video_path.stat()
    production_id = _production_id(video_path)
    created_at = manifest.get("generated_at") or datetime.datetime.fromtimestamp(
        stat.st_mtime, tz=datetime.timezone.utc
    ).isoformat()
    return {
        "id": production_id,
        "title": str(youtube.get("title") or _legacy_title(video_path)),
        "description": str(youtube.get("description") or ""),
        "content_type": str(manifest.get("content_type") or "short"),
        "created_at": created_at,
        "size_bytes": stat.st_size,
        "duration_seconds": metrics.get("duration_seconds"),
        "width": metrics.get("width"),
        "height": metrics.get("height"),
        "quality_score": quality.get("score"),
        "approved": quality.get("approved"),
        "sources": len(sources),
        "video_path": str(video_path),
        "video_url": f"/api/files?path={video_path}",
        "download_url": f"/api/productions/{production_id}/download",
        "manifest_url": f"/api/files?path={manifest_path}" if manifest_path and manifest_path.is_file() else None,
        "manifest_download_url": f"/api/productions/{production_id}/manifest" if manifest_path and manifest_path.is_file() else None,
        "quality": quality,
        "video_quality": video_quality,
    }


def _production_rows() -> list[dict]:
    if not PRODUCTIONS_ROOT.is_dir():
        return []
    rows = [_production_record(path) for path in PRODUCTIONS_ROOT.glob("*.mp4") if path.is_file()]
    return sorted(rows, key=lambda item: item["created_at"], reverse=True)


def _find_production(production_id: str) -> tuple[Path, dict]:
    for video_path in PRODUCTIONS_ROOT.glob("*.mp4") if PRODUCTIONS_ROOT.is_dir() else []:
        if video_path.is_file() and _production_id(video_path) == production_id:
            return video_path, _production_record(video_path)
    raise HTTPException(404, "Production not found.")


def _download_filename(title: str, suffix: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", title).strip(" .")[:120]
    return f"{cleaned or 'ContentGenie Short'}{suffix}"


def _asset_rows() -> list[dict]:
    frame = AssetDatabase.get_df()
    if frame is None or frame.empty:
        return []
    return frame.fillna("").to_dict(orient="records")


def _find_default_asset(asset_type: str) -> str:
    for item in _asset_rows():
        if item.get("type") == asset_type:
            return str(item.get("name") or "")
    return ""


def _friendly_stage(step: int, message: str = "") -> str:
    raw = str(message or "").lower()
    if "music" in raw and ("match" in raw or "download" in raw or "discover" in raw):
        return "Matching licensed music to the story"
    if "download" in raw:
        return "Downloading rights-verified gameplay"
    if "analy" in raw or "scor" in raw:
        return "Scoring footage for motion and clarity"
    if "render" in raw:
        return "Rendering the final edit"
    return {
        1: "Researching and writing the story",
        2: "Creating the voiceover",
        3: "Polishing voice timing",
        4: "Timing captions word by word",
        5: "Planning visual moments",
        6: "Generating visual overlays",
        7: "Preparing the music mix",
        8: "Selecting background footage",
        9: "Building the gameplay montage",
        10: "Preparing visual layers",
        11: "Rendering the final edit",
        12: "Running quality checks",
        13: "Writing metadata and credits",
    }.get(step, "Preparing your Short")


def _run_generation(job_id: str, payload: CreatePayload):
    try:
        from contentgenie.audio.gemini_tts_voice_module import GeminiTTSVoiceModule
        from contentgenie.config.languages import Language
        from contentgenie.engine.facts_short_engine import FactsShortEngine
        from contentgenie.engine.reddit_short_engine import RedditShortEngine

        if not payload.rights_confirmed:
            raise ValueError("Confirm the publishing-rights review before starting production.")
        if not ApiKeyManager.get_api_key("GEMINI_API_KEY"):
            raise ValueError("Add a Gemini API key in Settings before starting production.")
        music = payload.background_music
        if payload.music_mode == "manual":
            music = music or _find_default_asset(AssetType.BACKGROUND_MUSIC.value)
            if not music:
                raise ValueError("Choose a background-music track or use automatic script matching.")
        if payload.footage_mode == "manual" and not payload.background_video:
            raise ValueError("Select a background video or use automatic licensed gameplay.")

        JOBS.update(job_id, status="running", stage="Starting production")
        voice = GeminiTTSVoiceModule(persona=payload.voice_persona)
        total_steps = payload.quantity * 13
        for index in range(payload.quantity):
            current = JOBS.get(job_id)
            if current and current.get("cancel_requested"):
                JOBS.update(job_id, status="cancelled", stage="Production cancelled")
                return
            common = dict(
                voiceModule=voice,
                background_video_name=None if payload.footage_mode == "automatic" else payload.background_video,
                background_music_name=music,
                num_images=payload.image_count if payload.use_images else None,
                watermark=payload.watermark or None,
                language=Language.ENGLISH,
                creative_brief=payload.creative_brief,
                audience=payload.audience,
                tone=payload.tone,
                creator_angle=payload.creator_angle,
                target_duration=payload.target_duration,
                quality_mode="Production (researched + reviewed)" if payload.quality_mode == "production" else "Draft (single pass)",
                rights_confirmed=True,
                footage_mode="Automatic licensed gameplay" if payload.footage_mode == "automatic" else "Manual library selection",
                footage_style=payload.footage_style,
                footage_intensity=payload.footage_intensity,
                allow_youtube_cc=payload.allow_youtube_cc,
                avoid_recent_footage=payload.avoid_recent_footage,
                music_mode="Automatic script match" if payload.music_mode == "automatic" else "Manual library selection",
            )
            if payload.content_format == "reddit":
                engine = RedditShortEngine(**common)
            else:
                facts_type = payload.subject.strip() if payload.content_format == "custom" else {
                    "history": "Today in History shorts",
                    "science": "Scientific Facts shorts",
                }[payload.content_format]
                if not facts_type:
                    raise ValueError("Write a subject for the custom facts Short.")
                engine = FactsShortEngine(facts_type=facts_type, **common)

            state = {"step": 1}

            def logger(message):
                step = state["step"]
                completed = (index * 13) + max(step - 1, 0)
                JOBS.update(
                    job_id,
                    progress=round(completed / total_steps * 100),
                    stage=_friendly_stage(step, str(message)),
                    current_short=index + 1,
                )

            engine.set_logger(logger)
            for step, message in engine.makeContent():
                state["step"] = step
                logger(message)
                current = JOBS.get(job_id)
                if current and current.get("cancel_requested"):
                    JOBS.update(job_id, status="cancelled", stage="Production cancelled")
                    return

            video_path = engine.get_video_output_path()
            summary = engine.get_output_summary()
            production = _production_record(Path(video_path).resolve())
            output = {
                "id": production["id"],
                "title": summary.get("title") or Path(video_path).stem,
                "video_path": video_path,
                "video_url": f"/api/files?path={video_path}",
                "download_url": production["download_url"],
                "manifest_url": production["manifest_url"],
                "manifest_download_url": production["manifest_download_url"],
                "quality": summary.get("quality_report") or {},
                "video_quality": summary.get("video_quality_report") or {},
                "sources": len(summary.get("research_sources") or []),
            }
            existing = (JOBS.get(job_id) or {}).get("outputs", [])
            JOBS.update(job_id, outputs=[*existing, output])

        JOBS.update(job_id, status="complete", progress=100, stage="Your Shorts are ready")
    except ValueError as error:
        JOBS.update(job_id, status="failed", error=str(error) or type(error).__name__, stage="Production stopped")
    except Exception as error:
        traceback.print_exc()
        JOBS.update(job_id, status="failed", error=str(error) or type(error).__name__, stage="Production stopped")


@app.get("/api/health")
def health():
    return {"status": "ok", "product": "ContentGenie"}


@app.get("/api/settings")
def get_settings():
    return {"values": {key: ApiKeyManager.get_api_key(key) for key in SETTINGS_KEYS}}


@app.put("/api/settings")
def save_settings(payload: SettingsPayload):
    allowed = set(SETTINGS_KEYS)
    for key, value in payload.values.items():
        if key in allowed:
            ApiKeyManager.set_api_key(key, str(value))
    return get_settings()


@app.get("/api/assets")
def list_assets():
    return {"items": _asset_rows()}


@app.post("/api/assets/remote")
def add_remote_asset(name: str = Form(...), asset_type: str = Form(...), url: str = Form(...)):
    if not name.strip() or AssetDatabase.asset_exists(name.strip()):
        raise HTTPException(400, "Use a unique asset name.")
    try:
        AssetDatabase.add_remote_asset(name.strip(), AssetType(asset_type), url.strip())
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    return {"items": _asset_rows()}


@app.post("/api/assets/upload")
def upload_asset(name: str = Form(...), asset_type: str = Form(...), file: UploadFile = File(...)):
    if not name.strip() or AssetDatabase.asset_exists(name.strip()):
        raise HTTPException(400, "Use a unique asset name.")
    extension = Path(file.filename or "upload.bin").suffix.lower()
    destination = Path("public/uploads") / f"{uuid.uuid4().hex}{extension}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as target:
        shutil.copyfileobj(file.file, target)
    try:
        AssetDatabase.add_local_asset(name.strip(), AssetType(asset_type), str(destination))
    except ValueError as error:
        destination.unlink(missing_ok=True)
        raise HTTPException(400, str(error)) from error
    return {"items": _asset_rows()}


@app.delete("/api/assets/{name}")
def delete_asset(name: str):
    try:
        AssetDatabase.remove_asset(name)
    except ValueError as error:
        raise HTTPException(404, str(error)) from error
    return {"items": _asset_rows()}


@app.post("/api/footage/discover")
def discover_footage(payload: DiscoveryPayload):
    service = FootageService()
    candidates = service.discover(style=payload.style, sources=payload.sources, query=payload.query.strip(), limit=25)
    return {"items": [candidate.to_dict() for candidate in candidates], "warnings": service.last_warnings}


@app.post("/api/footage/acquire")
def acquire_footage(payload: AcquirePayload):
    try:
        asset = FootageService().acquire(FootageCandidate.from_dict(payload.candidate))
    except (ValueError, OSError) as error:
        raise HTTPException(400, str(error)) from error
    return {"asset": asset, "items": _asset_rows()}


@app.post("/api/jobs")
def create_job(payload: CreatePayload):
    job = JOBS.create(payload)
    threading.Thread(target=_run_generation, args=(job["id"], payload), daemon=True, name=f"contentgenie-{job['id'][:8]}").start()
    return job


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "Generation job not found.")
    job["elapsed_seconds"] = max(0, int(time.time() - job["started_at"]))
    return job


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str):
    if not JOBS.get(job_id):
        raise HTTPException(404, "Generation job not found.")
    JOBS.update(job_id, cancel_requested=True, stage="Cancelling after the current step")
    return JOBS.get(job_id)


@app.get("/api/productions")
def list_productions():
    return {"items": _production_rows()}


@app.get("/api/productions/{production_id}/download")
def download_production(production_id: str):
    video_path, production = _find_production(production_id)
    return FileResponse(
        video_path,
        media_type="video/mp4",
        filename=_download_filename(production["title"], ".mp4"),
        content_disposition_type="attachment",
    )


@app.get("/api/productions/{production_id}/manifest")
def download_production_manifest(production_id: str):
    video_path, production = _find_production(production_id)
    manifest_path = video_path.with_suffix(".json")
    if not manifest_path.is_file():
        raise HTTPException(404, "This legacy production has no manifest.")
    return FileResponse(
        manifest_path,
        media_type="application/json",
        filename=_download_filename(production["title"], " - manifest.json"),
        content_disposition_type="attachment",
    )


@app.delete("/api/productions/{production_id}")
def delete_production(production_id: str):
    video_path, production = _find_production(production_id)
    companions = [video_path, video_path.with_suffix(".json"), video_path.with_suffix(".txt")]
    try:
        for path in companions:
            path.unlink(missing_ok=True)
    except OSError as error:
        raise HTTPException(500, f"Could not delete '{production['title']}'.") from error
    return {"deleted": production_id, "items": _production_rows()}


@app.get("/api/files")
def get_file(path: str):
    candidate = Path(path).resolve()
    if not any(candidate == root or root in candidate.parents for root in ALLOWED_FILE_ROOTS):
        raise HTTPException(403, "That file is outside ContentGenie's media directories.")
    if not candidate.is_file():
        raise HTTPException(404, "File not found.")
    return FileResponse(candidate)

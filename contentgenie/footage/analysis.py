from __future__ import annotations

import contextlib
import hashlib
import io
import json
import math
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image
from moviepy import VideoFileClip
from contentgenie.config.performance import get_ffmpeg_binary


ANALYSIS_VERSION = 4
SCORE_MODEL_VERSION = 2
ANALYSIS_CACHE_DIR = Path(".editing_assets/footage_analysis")


def _cache_path(video_path: str) -> Path:
    path = Path(video_path)
    stat = path.stat()
    identity = f"{path.resolve()}:{stat.st_size}:{stat.st_mtime_ns}:{ANALYSIS_VERSION}"
    return ANALYSIS_CACHE_DIR / f"{hashlib.sha256(identity.encode('utf-8')).hexdigest()}.json"


def _small_gray(frame: np.ndarray, width: int = 192, height: int = 108) -> np.ndarray:
    image = Image.fromarray(frame).resize((width, height), Image.Resampling.BILINEAR).convert("L")
    return np.asarray(image, dtype=np.float32)


def _perceptual_signature(gray: np.ndarray) -> str:
    image = Image.fromarray(np.clip(gray, 0, 255).astype(np.uint8)).resize((16, 16), Image.Resampling.BILINEAR)
    values = np.asarray(image, dtype=np.float32)
    bits = values >= values.mean()
    packed = np.packbits(bits.flatten()).tobytes()
    return packed.hex()


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def classify_visual_event(
    motion: float,
    previous_motion: float,
    focus_x: float,
    previous_focus_x: float,
    brightness: float,
    previous_brightness: float,
) -> tuple[str, float]:
    """Classify event-like visual peaks without requiring game-specific semantics."""
    motion_delta = motion - previous_motion
    focus_shift = abs(focus_x - previous_focus_x)
    exposure_shift = abs(brightness - previous_brightness)
    if motion >= 0.18 and motion_delta >= 0.04:
        return "impact_or_landing_peak", 8.0
    if motion >= 0.075 and focus_shift >= 0.10:
        return "turn_or_near_miss_peak", 6.0
    if motion >= 0.055 and exposure_shift >= 35:
        return "visual_reveal_peak", 5.0
    if motion >= 0.11:
        return "high_action", 3.0
    if motion < 0.004:
        return "static_or_menu_risk", -20.0
    return "continuous_traversal", 0.0


def _rescore_moments(result: dict) -> dict:
    moments = result.get("moments") or []
    if not moments:
        result["score_model_version"] = SCORE_MODEL_VERSION
        return result
    motion_values = sorted(float(item.get("motion", 0)) for item in moments)
    sharpness_values = sorted(float(item.get("sharpness", 0)) for item in moments)
    count = max(len(moments) - 1, 1)
    event_weights = {
        "impact_or_landing_peak": 1.0,
        "turn_or_near_miss_peak": 0.85,
        "visual_reveal_peak": 0.75,
        "high_action": 0.6,
        "continuous_traversal": 0.35,
        "static_or_menu_risk": 0.0,
    }
    for item in moments:
        motion = float(item.get("motion", 0))
        sharpness = float(item.get("sharpness", 0))
        brightness = float(item.get("brightness", 0))
        motion_rank = np.searchsorted(motion_values, motion, side="right") / count
        sharpness_rank = np.searchsorted(sharpness_values, sharpness, side="right") / count
        exposure = 1.0 - min(abs(brightness - 125.0) / 125.0, 1.0)
        event_weight = event_weights.get(item.get("event_type"), 0.25)
        score = 100.0 * (
            0.55 * min(motion_rank, 1.0)
            + 0.20 * min(sharpness_rank, 1.0)
            + 0.15 * exposure
            + 0.10 * event_weight
        )
        if item.get("event_type") == "static_or_menu_risk":
            score = min(score, 12.0)
        item["score"] = round(min(max(score, 0.0), 100.0), 3)
    moments.sort(key=lambda item: item["score"], reverse=True)
    quality = result.setdefault("quality", {})
    quality["retention_score"] = float(np.mean([item["score"] for item in moments[: min(30, len(moments))]]))
    result["score_model_version"] = SCORE_MODEL_VERSION
    return result


def _sample_gray_frames(video_path: str, duration: float, max_samples: int) -> tuple[np.ndarray, float, float]:
    # A four-minute window supplies dozens of unique Shorts segments while keeping
    # first-time VP9/AV1 analysis practical on consumer hardware.
    analysis_duration = min(duration, 4 * 60.0)
    interval = max(0.75, analysis_duration / max(max_samples, 1))
    sample_fps = 1.0 / interval
    command = [
        get_ffmpeg_binary(),
        "-hide_banner",
        "-loglevel",
        "error",
        "-t",
        str(analysis_duration),
        "-i",
        video_path,
        "-map",
        "0:v:0",
        "-an",
        "-vf",
        f"fps={sample_fps:.8f},scale=192:108:flags=fast_bilinear,format=gray",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "gray",
        "pipe:1",
    ]
    process = subprocess.run(command, capture_output=True, timeout=max(120, int(analysis_duration / 2)))
    if process.returncode != 0:
        error = process.stderr.decode("utf-8", errors="ignore")[-800:]
        raise ValueError(f"FFmpeg could not sample gameplay frames: {error}")
    frame_size = 192 * 108
    values = np.frombuffer(process.stdout, dtype=np.uint8)
    usable = len(values) - (len(values) % frame_size)
    if usable < frame_size:
        raise ValueError("Gameplay analysis produced no readable frames")
    return values[:usable].reshape((-1, 108, 192)), interval, analysis_duration


def analyze_video(video_path: str, force: bool = False, max_samples: int = 180) -> dict:
    """Sample a video and rank moments by motion, clarity, exposure, and crop focus."""
    cache_path = _cache_path(video_path)
    if cache_path.exists() and not force:
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if cached.get("score_model_version") != SCORE_MODEL_VERSION:
                cached = _rescore_moments(cached)
                cache_path.write_text(json.dumps(cached, indent=2), encoding="utf-8")
            return cached
        except (OSError, ValueError):
            pass

    with contextlib.redirect_stdout(io.StringIO()):
        clip = VideoFileClip(video_path, audio=False)
    try:
        duration = float(clip.duration or 0)
        width, height = [int(value) for value in clip.size]
        fps = float(clip.fps or 0)
    finally:
        clip.close()
    if duration <= 0 or width <= 0 or height <= 0:
        raise ValueError(f"Unreadable gameplay video: {video_path}")

    gray_frames, interval, analyzed_duration = _sample_gray_frames(video_path, duration, max_samples)
    moments = []
    previous = None
    sharpness_values = []
    motion_values = []
    brightness_values = []
    signatures = []
    previous_motion = 0.0
    previous_focus_x = 0.5
    previous_brightness = 125.0
    for index, frame in enumerate(gray_frames):
        sample_time = min(float(index) * interval, analyzed_duration)
        gray = frame.astype(np.float32)
        brightness = float(gray.mean())
        gx = np.diff(gray, axis=1)
        gy = np.diff(gray, axis=0)
        sharpness = float((np.var(gx) + np.var(gy)) / 2.0)
        if previous is None:
            difference = np.zeros_like(gray)
            motion = 0.0
        else:
            difference = np.abs(gray - previous)
            motion = float(difference.mean() / 255.0)

        column_motion = difference.mean(axis=0)
        if float(column_motion.sum()) > 0.01:
            focus_x = float(np.average(np.arange(len(column_motion)), weights=column_motion) / max(len(column_motion) - 1, 1))
        else:
            focus_x = 0.5
        focus_x = min(max(focus_x, 0.18), 0.82)

        event_type, event_bonus = classify_visual_event(
            motion,
            previous_motion,
            focus_x,
            previous_focus_x,
            brightness,
            previous_brightness,
        )

        exposure = 1.0 - min(abs(brightness - 125.0) / 125.0, 1.0)
        motion_score = min(motion / 0.095, 1.0)
        sharpness_score = min(math.log1p(max(sharpness, 0.0)) / math.log1p(900.0), 1.0)
        score = min(100.0, 100.0 * (0.66 * motion_score + 0.22 * sharpness_score + 0.12 * exposure) + event_bonus)
        if brightness < 18 or brightness > 242:
            score *= 0.2
        if motion < 0.004:
            score *= 0.35

        signature = _perceptual_signature(gray)
        moments.append({
            "time": round(float(sample_time), 3),
            "score": round(float(score), 3),
            "motion": round(motion, 5),
            "sharpness": round(sharpness, 3),
            "brightness": round(brightness, 3),
            "focus_x": round(focus_x, 4),
            "signature": signature,
            "event_type": event_type,
        })
        sharpness_values.append(sharpness)
        motion_values.append(motion)
        brightness_values.append(brightness)
        signatures.append(signature)
        previous = gray
        previous_motion = motion
        previous_focus_x = focus_x
        previous_brightness = brightness

    moments.sort(key=lambda item: item["score"], reverse=True)
    checksum = _sha256_file(video_path)
    result = {
            "analysis_version": ANALYSIS_VERSION,
            "path": str(video_path),
            "checksum_sha256": checksum,
            "duration": duration,
            "width": width,
            "height": height,
            "fps": fps,
            "sample_interval": interval,
            "analyzed_duration": analyzed_duration,
            "quality": {
                "mean_motion": float(np.mean(motion_values)) if motion_values else 0.0,
                "mean_sharpness": float(np.mean(sharpness_values)) if sharpness_values else 0.0,
                "mean_brightness": float(np.mean(brightness_values)) if brightness_values else 0.0,
                "retention_score": float(np.mean([item["score"] for item in moments[: min(30, len(moments))]])) if moments else 0.0,
            },
            "moments": moments,
            "content_signatures": sorted(set(signatures)),
        }
    result = _rescore_moments(result)

    ANALYSIS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    temporary = cache_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(result, indent=2), encoding="utf-8")
    temporary.replace(cache_path)
    return result

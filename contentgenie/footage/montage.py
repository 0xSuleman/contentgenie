from __future__ import annotations

import json
import math
import os
import random
import shutil
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path

from contentgenie.config.performance import (
    get_background_clip_encode_args,
    get_ffmpeg_binary,
    nvenc_runtime_available,
)
from contentgenie.editing_utils.handle_videos import _validate_video_clip


USAGE_LEDGER_PATH = Path(".database/footage_usage.json")
_USAGE_LOCK = threading.Lock()

INTENSITY_LENGTHS = {
    "Balanced": (4.2, 6.8),
    "High": (2.8, 4.8),
    "Extreme": (1.8, 3.2),
}


def _load_usage() -> list[dict]:
    with _USAGE_LOCK:
        if not USAGE_LEDGER_PATH.exists():
            return []
        try:
            data = json.loads(USAGE_LEDGER_PATH.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (OSError, ValueError):
            return []


def record_usage(content_id: str, segments: list[dict]) -> None:
    rows = [
        {
            "content_id": content_id,
            "source_key": item["source_key"],
            "start": round(float(item["start"]), 3),
            "duration": round(float(item["duration"]), 3),
            "signature": item.get("signature", ""),
            "used_at": datetime.now(timezone.utc).isoformat(),
        }
        for item in segments
    ]
    with _USAGE_LOCK:
        existing = []
        if USAGE_LEDGER_PATH.exists():
            try:
                existing = json.loads(USAGE_LEDGER_PATH.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                existing = []
        existing = (existing if isinstance(existing, list) else [])[-5000:] + rows
        temporary = USAGE_LEDGER_PATH.with_suffix(".tmp")
        temporary.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        temporary.replace(USAGE_LEDGER_PATH)


def _recently_used(source_key: str, start: float, signature: str, usage: list[dict]) -> bool:
    for item in usage:
        if signature and item.get("signature") == signature:
            return True
        if item.get("source_key") == source_key and abs(float(item.get("start", -9999)) - start) < 4.0:
            return True
    return False


def _align_plan_to_cut_points(
    plan: list[dict],
    target_duration: float,
    intensity: str,
    preferred_cut_times: list[float] | None,
) -> list[dict]:
    if not plan or not preferred_cut_times:
        return plan
    minimum, maximum = INTENSITY_LENGTHS.get(intensity, INTENSITY_LENGTHS["High"])
    anchors = sorted({
        min(max(float(value), 0.0), target_duration)
        for value in preferred_cut_times
        if 0.0 < float(value) < target_duration
    })
    timeline = 0.0
    for index, segment in enumerate(plan):
        remaining_segments = len(plan) - index - 1
        if not remaining_segments:
            duration = target_duration - timeline
        else:
            desired_end = timeline + float(segment["duration"])
            lower = timeline + minimum
            upper = min(timeline + maximum, target_duration - remaining_segments * 0.35)
            choices = [anchor for anchor in anchors if lower <= anchor <= upper]
            cut_at = min(choices, key=lambda value: abs(value - desired_end)) if choices else min(desired_end, upper)
            duration = cut_at - timeline
        segment["timeline_start"] = timeline
        segment["duration"] = max(duration, 0.35)
        source_duration = float(segment.get("source_duration") or 0)
        moment_time = float(segment.get("moment_time") or segment.get("start") or 0)
        segment["start"] = min(
            max(moment_time - segment["duration"] * 0.35, 0.0),
            max(source_duration - segment["duration"] - 0.1, 0.0),
        )
        timeline += segment["duration"]
    if plan:
        correction = target_duration - timeline
        plan[-1]["duration"] = max(plan[-1]["duration"] + correction, 0.35)
    return plan


def plan_retention_segments(
    assets: list[dict],
    target_duration: float,
    intensity: str = "High",
    avoid_recent: bool = True,
    seed: str = "",
    preferred_cut_times: list[float] | None = None,
) -> list[dict]:
    if not assets:
        raise ValueError("No licensed gameplay assets are available")
    minimum, maximum = INTENSITY_LENGTHS.get(intensity, INTENSITY_LENGTHS["High"])
    rng = random.Random(seed or "licensed-footage")
    usage = _load_usage() if avoid_recent else []
    pool = []
    for asset in assets:
        analysis = asset.get("analysis") or {}
        source_key = asset.get("source_key") or asset.get("name") or asset.get("path")
        source_duration = float(analysis.get("duration") or asset.get("duration") or 0)
        for moment in (analysis.get("moments") or [])[:120]:
            clip_length = rng.uniform(minimum, maximum)
            start = min(max(float(moment.get("time", 0)) - clip_length * 0.35, 0.0), max(source_duration - clip_length - 0.1, 0.0))
            signature = moment.get("signature", "")
            if avoid_recent and _recently_used(source_key, start, signature, usage):
                continue
            pool.append({
                "asset_name": asset.get("name", "licensed gameplay"),
                "path": asset["path"],
                "source_key": source_key,
                "start": start,
                "duration": clip_length,
                "score": float(moment.get("score", 0)),
                "motion": float(moment.get("motion", 0)),
                "focus_x": float(moment.get("focus_x", 0.5)),
                "signature": signature,
                "source_width": int(analysis.get("width") or 0),
                "source_height": int(analysis.get("height") or 0),
                "source_duration": source_duration,
                "moment_time": float(moment.get("time", 0)),
                "provenance": asset.get("provenance") or {},
            })
    if not pool:
        for asset in assets:
            analysis = asset.get("analysis") or {}
            source_duration = float(analysis.get("duration") or 0)
            if source_duration <= minimum:
                continue
            for fraction in (0.12, 0.32, 0.52, 0.72):
                clip_length = rng.uniform(minimum, maximum)
                pool.append({
                    "asset_name": asset.get("name", "licensed gameplay"),
                    "path": asset["path"],
                    "source_key": asset.get("source_key") or asset.get("name") or asset["path"],
                    "start": min(source_duration * fraction, max(source_duration - clip_length - 0.1, 0.0)),
                    "duration": clip_length,
                    "score": 1.0,
                    "focus_x": 0.5,
                    "signature": "",
                    "source_width": int(analysis.get("width") or 0),
                    "source_height": int(analysis.get("height") or 0),
                    "source_duration": source_duration,
                    "moment_time": source_duration * fraction,
                    "provenance": asset.get("provenance") or {},
                })
    if not pool:
        raise ValueError("Licensed gameplay files are too short to assemble a background")

    pool.sort(key=lambda item: item["score"], reverse=True)
    plan = []
    elapsed = 0.0
    used_signatures = set()
    last_source = None
    while elapsed < target_duration - 0.05:
        def non_overlapping(item):
            return all(
                item["source_key"] != prior["source_key"]
                or abs(float(item["start"]) - float(prior["start"]))
                >= max(float(item["duration"]), float(prior["duration"])) + 1.0
                for prior in plan
            )

        candidates = [
            item for item in pool
            if item.get("signature") not in used_signatures
            and non_overlapping(item)
            and (len(assets) == 1 or item["source_key"] != last_source)
        ]
        if not candidates:
            candidates = [
                item for item in pool
                if item.get("signature") not in used_signatures and non_overlapping(item)
            ] or pool
        top_window = candidates[: min(12, len(candidates))]
        if not plan:
            selected = dict(max(top_window, key=lambda item: (item["score"], item.get("motion", 0))))
        else:
            weights = [max(item["score"], 1.0) ** 2 for item in top_window]
            selected = dict(rng.choices(top_window, weights=weights, k=1)[0])
        selected["duration"] = min(float(selected["duration"]), target_duration - elapsed)
        if selected["duration"] < 0.35:
            if plan:
                plan[-1]["duration"] += selected["duration"]
            break
        selected["timeline_start"] = elapsed
        plan.append(selected)
        elapsed += selected["duration"]
        last_source = selected["source_key"]
        if selected.get("signature"):
            used_signatures.add(selected["signature"])
    return _align_plan_to_cut_points(plan, target_duration, intensity, preferred_cut_times)


def _vertical_filter(segment: dict) -> str:
    width = max(int(segment.get("source_width") or 1920), 1)
    height = max(int(segment.get("source_height") or 1080), 1)
    scale = max(1080.0 / width, 1920.0 / height)
    scaled_width = int(math.ceil(width * scale / 2.0) * 2)
    scaled_height = int(math.ceil(height * scale / 2.0) * 2)
    focus_x = min(max(float(segment.get("focus_x", 0.5)), 0.18), 0.82)
    crop_x = int(min(max(scaled_width * focus_x - 540, 0), max(scaled_width - 1080, 0)))
    crop_y = int(max((scaled_height - 1920) / 2, 0))
    return (
        f"scale={scaled_width}:{scaled_height},"
        f"crop=1080:1920:{crop_x}:{crop_y},"
        "setsar=1,fps=30,eq=contrast=1.035:saturation=1.07"
    )


def _render_segment(segment: dict, output_path: Path, use_nvenc: bool) -> None:
    command = [
        get_ffmpeg_binary(),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        str(segment["start"]),
        "-i",
        segment["path"],
        "-t",
        str(float(segment["duration"]) + 0.08),
        "-map",
        "0:v:0",
        "-an",
        "-sn",
        "-dn",
        "-vf",
        _vertical_filter(segment),
        *get_background_clip_encode_args(use_nvenc),
        "-g",
        "30",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    subprocess.run(command, check=True, capture_output=True)


def build_retention_montage(
    assets: list[dict],
    target_duration: float,
    output_path: str,
    intensity: str = "High",
    avoid_recent: bool = True,
    content_id: str = "",
    logger=None,
    preferred_cut_times: list[float] | None = None,
) -> tuple[str, list[dict]]:
    plan = plan_retention_segments(
        assets,
        target_duration,
        intensity,
        avoid_recent,
        seed=content_id,
        preferred_cut_times=preferred_cut_times,
    )
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    work_dir = output.parent / f"footage_montage_{content_id[:8] or 'work'}"
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True)
    use_nvenc = nvenc_runtime_available()
    try:
        rendered = []
        for index, segment in enumerate(plan):
            if logger:
                logger(f"Preparing licensed gameplay clip {index + 1}/{len(plan)}")
            segment_path = work_dir / f"segment_{index:03d}.mp4"
            try:
                _render_segment(segment, segment_path, use_nvenc)
            except subprocess.CalledProcessError:
                if not use_nvenc:
                    raise
                _render_segment(segment, segment_path, False)
            rendered.append(segment_path)

        concat_file = work_dir / "segments.txt"
        concat_file.write_text(
            "\n".join(f"file '{str(path.resolve()).replace(chr(39), chr(39) + chr(92) + chr(39) + chr(39))}'" for path in rendered),
            encoding="utf-8",
        )
        temporary_output = output.with_suffix(".tmp.mp4")
        if temporary_output.exists():
            temporary_output.unlink()
        command = [
            get_ffmpeg_binary(),
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-t",
            str(target_duration + 0.05),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(temporary_output),
        ]
        subprocess.run(command, check=True, capture_output=True)
        _validate_video_clip(str(temporary_output), expected_duration=target_duration)
        if output.exists():
            output.unlink()
        os.replace(temporary_output, output)
        record_usage(content_id, plan)
        return str(output), plan
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

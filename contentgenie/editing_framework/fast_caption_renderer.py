from __future__ import annotations

import copy
import os
import subprocess
from pathlib import Path

from PIL import ImageColor

from contentgenie.config.performance import (
    get_background_clip_encode_args,
    get_bool_setting,
    get_ffmpeg_binary,
    get_float_setting,
    nvenc_runtime_available,
)


def split_pop_captions(schema: dict) -> tuple[dict, list[dict]]:
    visual_assets = schema.get("visual_assets") or {}
    captions = []
    remaining = {}
    for key, asset in visual_assets.items():
        actions = asset.get("actions") or []
        is_pop_caption = key.startswith("caption_pop_") and any(
            action.get("type") == "bounce_scale" for action in actions
        )
        if is_pop_caption:
            captions.append(asset)
        else:
            remaining[key] = asset
    if not captions or not get_bool_setting("FAST_CAPTION_RENDER", True):
        return schema, []
    base_schema = copy.deepcopy(schema)
    base_schema["visual_assets"] = remaining
    return base_schema, captions


def _action(asset: dict, name: str, default=None):
    for action in asset.get("actions") or []:
        if action.get("type") == name:
            return action.get("param")
    return default


def _ass_time(seconds: float) -> str:
    seconds = max(float(seconds or 0), 0)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    remaining = seconds % 60
    return f"{hours}:{minutes:02d}:{remaining:05.2f}"


def _ass_color(value: str) -> str:
    try:
        red, green, blue = ImageColor.getrgb(str(value or "white"))[:3]
    except ValueError:
        red, green, blue = 255, 255, 255
    return f"&H00{blue:02X}{green:02X}{red:02X}&"


def _escape_text(value: str) -> str:
    return str(value or "").replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}").replace("\n", r"\N")


def _position(asset: dict) -> tuple[int, int, int]:
    position = (_action(asset, "screen_position", {}) or {}).get("pos", "center")
    if position == "center":
        return 540, 960, 5
    if isinstance(position, (list, tuple)) and len(position) >= 2:
        centered_x = position[0] == "center"
        centered_y = position[1] == "center"
        x = 540 if centered_x else int(float(position[0]))
        y = 960 if centered_y else int(float(position[1])) + round(get_float_setting("FAST_CAPTION_TOP_OFFSET", 40.0, 0.0, 160.0))
        alignment = 5 if centered_x and centered_y else 8 if centered_x else 4 if centered_y else 7
        return x, y, alignment
    return 540, 960, 5


def write_pop_caption_ass(captions: list[dict], destination: Path) -> Path:
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Pop,Luckiest Guy,118,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,4,0,5,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for asset in captions:
        start = float(_action(asset, "set_time_start", 0) or 0)
        end = float(_action(asset, "set_time_end", start + 0.08) or (start + 0.08))
        if end <= start:
            continue
        params = asset.get("parameters") or {}
        bounce = _action(asset, "bounce_scale", {}) or {}
        start_scale = round(float(bounce.get("start", 0.55)) * 100)
        peak_scale = round(float(bounce.get("peak", 1.18)) * 100)
        settle_scale = round(float(bounce.get("settle", 1.0)) * 100)
        attack_ms = max(round(float(bounce.get("attack", 0.08)) * 1000), 1)
        release_end_ms = attack_ms + max(round(float(bounce.get("release", 0.16)) * 1000), 1)
        x, y, alignment = _position(asset)
        # libass font units render smaller than MoviePy/Pillow pixels at this
        # portrait script resolution. This calibrated scale preserves the
        # existing on-screen glyph dimensions without changing user settings.
        font_size = round(float(params.get("font_size") or 118) * get_float_setting("FAST_CAPTION_FONT_SCALE", 1.15, 1.0, 1.6))
        outline = float(params.get("stroke_width") or 0)
        primary = _ass_color(params.get("color") or "white")
        stroke = _ass_color(params.get("stroke_color") or "black")
        text = _escape_text(params.get("text") or "")
        overrides = (
            rf"\an{alignment}\pos({x},{y})\fnLuckiest Guy\fs{font_size}\bord{outline:g}\shad0"
            rf"\1c{primary}\3c{stroke}\fscx{start_scale}\fscy{start_scale}"
            rf"\t(0,{attack_ms},\fscx{peak_scale}\fscy{peak_scale})"
            rf"\t({attack_ms},{release_end_ms},\fscx{settle_scale}\fscy{settle_scale})"
        )
        events.append(
            f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Pop,,0,0,0,,{{{overrides}}}{text}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(header + "\n".join(events) + "\n", encoding="utf-8-sig")
    return destination


def _filter_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


def _burn_command(input_path: Path, output_path: Path, ass_path: Path, use_nvenc: bool) -> list[str]:
    fonts_dir = Path("fonts").resolve()
    subtitle_filter = f"ass=filename='{_filter_path(ass_path)}':fontsdir='{_filter_path(fonts_dir)}'"
    encode_args = get_background_clip_encode_args(use_nvenc)
    if not use_nvenc:
        encode_args = ["-c:v", "libx264", "-preset", os.getenv("X264_PRESET", "veryfast"), "-crf", "23", "-pix_fmt", "yuv420p"]
    return [
        get_ffmpeg_binary(), "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(input_path), "-vf", subtitle_filter,
        "-map", "0:v:0", "-map", "0:a?", *encode_args,
        "-c:a", "copy", "-movflags", "+faststart", str(output_path),
    ]


def burn_pop_captions(input_path: Path, output_path: Path, captions: list[dict]) -> None:
    ass_path = output_path.with_suffix(".captions.ass")
    write_pop_caption_ass(captions, ass_path)
    use_nvenc = nvenc_runtime_available()
    try:
        result = subprocess.run(_burn_command(input_path, output_path, ass_path, use_nvenc), capture_output=True, text=True)
        if result.returncode and use_nvenc:
            result = subprocess.run(_burn_command(input_path, output_path, ass_path, False), capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or "FFmpeg caption render failed")
    finally:
        ass_path.unlink(missing_ok=True)

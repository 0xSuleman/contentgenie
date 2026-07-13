import os
import contextlib
import io

from moviepy import VideoFileClip


def inspect_rendered_short(video_path, maximum_duration=60.0):
    """Inspect a render and return a publish-readiness report.

    This deliberately validates the encoded file rather than trusting the editing
    schema. A successful render can still be missing audio, have the wrong aspect
    ratio, or be truncated by FFmpeg.
    """
    issues = []
    warnings = []
    if not os.path.isfile(video_path):
        raise Exception(f"Rendered video was not created: {video_path}")

    size_bytes = os.path.getsize(video_path)
    if size_bytes < 256 * 1024:
        issues.append(f"Rendered file is unexpectedly small ({size_bytes} bytes).")

    with contextlib.redirect_stdout(io.StringIO()):
        clip = VideoFileClip(video_path)
    try:
        width, height = clip.size
        duration = float(clip.duration or 0)
        fps = float(clip.fps or 0)
        has_audio = clip.audio is not None
    finally:
        clip.close()

    aspect_ratio = width / height if height else 0
    if duration <= 0:
        issues.append("Rendered video has no readable duration.")
    elif duration > maximum_duration + 0.25:
        issues.append(f"Rendered video is {duration:.2f}s; the configured limit is {maximum_duration:.2f}s.")
    elif duration < 20:
        warnings.append(f"Rendered video is only {duration:.2f}s; confirm the story feels complete.")
    if not has_audio:
        issues.append("Rendered video has no audio track.")
    if height < 1280 or width < 720:
        issues.append(f"Rendered resolution {width}x{height} is below the vertical HD quality floor.")
    if abs(aspect_ratio - (9 / 16)) > 0.02:
        issues.append(f"Rendered aspect ratio is {aspect_ratio:.4f}, not vertical 9:16.")
    if fps < 24:
        warnings.append(f"Rendered frame rate is {fps:.2f} fps; 25 fps or higher is recommended.")

    return {
        "approved": not issues,
        "issues": issues,
        "warnings": warnings,
        "metrics": {
            "duration_seconds": round(duration, 3),
            "width": int(width),
            "height": int(height),
            "aspect_ratio": round(aspect_ratio, 5),
            "fps": round(fps, 3),
            "has_audio": has_audio,
            "file_size_bytes": size_bytes,
        },
    }


def validate_rendered_short(video_path, maximum_duration=60.0):
    report = inspect_rendered_short(video_path, maximum_duration=maximum_duration)
    if not report["approved"]:
        raise Exception("Rendered short failed publish-readiness checks: " + " ".join(report["issues"]))
    return report

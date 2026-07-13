import os
import subprocess
from functools import lru_cache
from pathlib import Path

import imageio_ffmpeg
from dotenv import load_dotenv

load_dotenv("./.env")


def get_bool_setting(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def get_int_setting(name: str, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        value = int(os.getenv(name, default))
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def get_float_setting(name: str, default: float, minimum: float | None = None, maximum: float | None = None) -> float:
    try:
        value = float(os.getenv(name, default))
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def get_ffmpeg_binary() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


@lru_cache(maxsize=1)
def has_h264_nvenc() -> bool:
    if not get_bool_setting("USE_NVIDIA_FFMPEG", True):
        return False
    try:
        result = subprocess.run(
            [get_ffmpeg_binary(), "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            errors="ignore",
            timeout=15,
        )
        return result.returncode == 0 and "h264_nvenc" in result.stdout
    except Exception:
        return False


@lru_cache(maxsize=1)
def nvenc_runtime_available() -> bool:
    if not has_h264_nvenc():
        return False

    test_output = Path(".editing_assets") / "nvenc_probe.mp4"
    test_output.parent.mkdir(parents=True, exist_ok=True)
    if test_output.exists():
        try:
            test_output.unlink()
        except OSError:
            pass

    command = [
        get_ffmpeg_binary(),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        "color=size=256x256:rate=25:duration=0.2",
        "-c:v",
        "h264_nvenc",
        "-preset",
        os.getenv("NVENC_PRESET", "p4"),
        "-pix_fmt",
        "yuv420p",
        str(test_output),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=20)
        ok = result.returncode == 0 and test_output.exists() and test_output.stat().st_size > 0
        return ok
    except Exception:
        return False
    finally:
        try:
            if test_output.exists():
                test_output.unlink()
        except OSError:
            pass


def get_background_clip_encode_args(use_nvenc: bool | None = None) -> list[str]:
    if use_nvenc is None:
        use_nvenc = nvenc_runtime_available()
    if use_nvenc:
        return [
            "-c:v",
            "h264_nvenc",
            "-preset",
            os.getenv("NVENC_PRESET", "p4"),
            "-rc",
            os.getenv("NVENC_RC", "vbr"),
            "-cq",
            os.getenv("NVENC_CQ", "23"),
            "-b:v",
            os.getenv("NVENC_BITRATE", "0"),
            "-pix_fmt",
            "yuv420p",
        ]
    return ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"]


def get_moviepy_video_kwargs(threads=None, logger=None, use_nvenc: bool | None = None, lossless: bool = False) -> dict:
    if use_nvenc is None:
        use_nvenc = nvenc_runtime_available()

    worker_threads = threads or get_int_setting("VIDEO_RENDER_THREADS", max((os.cpu_count() or 4) - 1, 1), 1, 32)
    kwargs = {
        "threads": worker_threads,
        "audio_codec": "aac",
        "fps": 25,
    }
    if logger is not None:
        kwargs["logger"] = logger

    if use_nvenc and lossless:
        kwargs.update(
            {
                "codec": "h264_nvenc",
                "preset": "p1",
                "ffmpeg_params": [
                    "-tune", "lossless", "-rc", "constqp", "-qp", "0", "-pix_fmt", "yuv444p",
                ],
            }
        )
    elif use_nvenc:
        kwargs.update(
            {
                "codec": "h264_nvenc",
                "preset": os.getenv("NVENC_PRESET", "p4"),
                "ffmpeg_params": [
                    "-pix_fmt",
                    "yuv420p",
                    "-rc",
                    os.getenv("NVENC_RC", "vbr"),
                    "-cq",
                    os.getenv("NVENC_CQ", "23"),
                    "-b:v",
                    os.getenv("NVENC_BITRATE", "0"),
                ],
            }
        )
    elif lossless:
        kwargs.update({"codec": "libx264", "preset": "ultrafast", "ffmpeg_params": ["-crf", "0", "-pix_fmt", "yuv444p"]})
    else:
        kwargs.update({"codec": "libx264", "preset": os.getenv("X264_PRESET", "veryfast")})

    return kwargs

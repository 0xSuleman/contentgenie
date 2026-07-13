import argparse
import json
import os
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from dotenv import load_dotenv


PIPE = None
PIPE_LOCK = None


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off", ""}


def _clean_prompt(prompt: str) -> str:
    return re.sub(r"\s+", " ", (prompt or "").replace("\n", " ")).strip()


def _dimension(value, default=720) -> int:
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = default
    value = max(512, min(1536, value))
    return max(512, (value // 16) * 16)


def _path_from_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        return ""
    path = Path(value)
    if not path.is_absolute():
        path = Path.cwd() / path
    return str(path)


def _windows_path_to_wsl(path: str) -> str:
    if not path:
        return path
    normalized = path.replace("\\", "/")
    if len(normalized) >= 3 and normalized[1:3] == ":/":
        return f"/mnt/{normalized[0].lower()}/{normalized[3:]}"
    return normalized


def _output_path(path: str, index: int) -> tuple[str, str]:
    original = path or f".editing_assets/generated_images/wsl_zimage_{index}_{int(time.time() * 1000)}.jpg"
    writable = _windows_path_to_wsl(original)
    writable_path = Path(writable)
    if not writable_path.is_absolute():
        writable_path = Path.cwd() / writable_path
    writable_path.parent.mkdir(parents=True, exist_ok=True)
    return original, str(writable_path)


def _model_source() -> str:
    source = os.getenv("ZIMAGE_LOCAL_MODEL_PATH") or os.getenv("ZIMAGE_MODEL_ID") or "Tongyi-MAI/Z-Image-Turbo"
    path = Path(source)
    if path.exists():
        return str(path.resolve())
    if not path.is_absolute() and (Path.cwd() / path).exists():
        return str((Path.cwd() / path).resolve())
    return source


def _load_gguf_transformer(torch_module, dtype):
    gguf_path = _path_from_env("ZIMAGE_GGUF_TRANSFORMER_PATH")
    if not gguf_path or not Path(gguf_path).exists():
        return None

    from diffusers import GGUFQuantizationConfig, ZImageTransformer2DModel

    quantization_config = GGUFQuantizationConfig(compute_dtype=dtype)
    try:
        return ZImageTransformer2DModel.from_single_file(
            gguf_path,
            quantization_config=quantization_config,
            torch_dtype=dtype,
        )
    except TypeError:
        return ZImageTransformer2DModel.from_single_file(
            gguf_path,
            quantization_config=quantization_config,
            dtype=dtype,
        )


def _load_gguf_text_encoder(dtype):
    gguf_path = _path_from_env("ZIMAGE_TEXT_ENCODER_GGUF_PATH")
    if not gguf_path or not Path(gguf_path).exists():
        return None

    from transformers import Qwen3Model

    text_encoder_dir = Path(_model_source()) / "text_encoder"
    try:
        return Qwen3Model.from_pretrained(
            str(text_encoder_dir),
            gguf_file=gguf_path,
            torch_dtype=dtype,
        )
    except TypeError:
        return Qwen3Model.from_pretrained(
            str(text_encoder_dir),
            gguf_file=gguf_path,
            dtype=dtype,
        )


def _load_pipe():
    global PIPE, PIPE_LOCK
    if PIPE is not None:
        return PIPE

    import threading

    if PIPE_LOCK is None:
        PIPE_LOCK = threading.Lock()

    with PIPE_LOCK:
        if PIPE is not None:
            return PIPE

        import flash_attn  # noqa: F401
        import torch
        from diffusers import ZImagePipeline

        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is not available inside WSL.")

        configured_dtype = os.getenv("ZIMAGE_TORCH_DTYPE", "auto").strip().lower()
        if configured_dtype in {"bf16", "bfloat16"}:
            dtype = torch.bfloat16
        elif configured_dtype in {"fp16", "float16", "half"}:
            dtype = torch.float16
        else:
            dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16

        load_kwargs = {
            "torch_dtype": dtype,
            "low_cpu_mem_usage": _bool_env("ZIMAGE_LOW_CPU_MEM_USAGE", False),
            "use_safetensors": True,
        }
        transformer = _load_gguf_transformer(torch, dtype)
        text_encoder = _load_gguf_text_encoder(dtype)
        if transformer is not None:
            load_kwargs["transformer"] = transformer
        if text_encoder is not None:
            load_kwargs["text_encoder"] = text_encoder

        device_map = os.getenv("ZIMAGE_DEVICE_MAP", "").strip()
        if device_map:
            load_kwargs["device_map"] = device_map
            if device_map in {"auto", "balanced", "balanced_low_0"}:
                load_kwargs["max_memory"] = {
                    0: os.getenv("ZIMAGE_MAX_GPU_MEMORY", "14GiB"),
                    "cpu": os.getenv("ZIMAGE_MAX_CPU_MEMORY", "24GiB"),
                }

        try:
            pipe = ZImagePipeline.from_pretrained(_model_source(), **load_kwargs)
        except TypeError:
            load_kwargs["dtype"] = load_kwargs.pop("torch_dtype")
            pipe = ZImagePipeline.from_pretrained(_model_source(), **load_kwargs)

        if not hasattr(pipe, "transformer") or not hasattr(pipe.transformer, "set_attention_backend"):
            raise RuntimeError("This Diffusers build does not expose Z-Image attention backend selection.")

        pipe.transformer.set_attention_backend("flash")
        if not device_map:
            pipe.to("cuda")
        if hasattr(pipe, "set_progress_bar_config"):
            pipe.set_progress_bar_config(disable=True)

        if _bool_env("ZIMAGE_COMPILE_TRANSFORMER", False):
            pipe.transformer.compile()

        PIPE = pipe
        return PIPE


def _generate(payload: dict) -> dict:
    import torch

    prompt = _clean_prompt(payload.get("prompt", ""))
    if not prompt:
        raise ValueError("Image prompt is empty.")

    index = int(payload.get("index", 0))
    width = _dimension(payload.get("width"), int(os.getenv("AI_IMAGE_WIDTH", "720")))
    height = _dimension(payload.get("height"), int(os.getenv("AI_IMAGE_HEIGHT", "720")))
    steps = int(os.getenv("ZIMAGE_STEPS", "9"))
    guidance_scale = float(os.getenv("ZIMAGE_GUIDANCE_SCALE", "0.0"))
    seed = payload.get("seed")
    if seed is None:
        seed = int(time.time() * 1000) + index
    seed = int(seed)
    original_path, writable_path = _output_path(payload.get("output_path"), index)

    pipe = _load_pipe()
    generator = torch.Generator(device="cuda").manual_seed(seed)
    with torch.inference_mode():
        image = pipe(
            prompt=prompt,
            height=height,
            width=width,
            num_inference_steps=steps,
            guidance_scale=guidance_scale,
            generator=generator,
        ).images[0]

    if image.mode != "RGB":
        image = image.convert("RGB")
    image.save(writable_path, quality=95)
    return {
        "ok": True,
        "output_path": original_path,
        "wsl_output_path": writable_path,
        "width": width,
        "height": height,
        "seed": seed,
    }


class Handler(BaseHTTPRequestHandler):
    def _json(self, status: int, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            try:
                _load_pipe()
                self._json(200, {"ok": True, "backend": "flash"})
            except Exception as error:
                self._json(503, {"ok": False, "error": str(error)})
            return
        self._json(404, {"ok": False, "error": "Not found"})

    def do_POST(self):
        if self.path != "/generate":
            self._json(404, {"ok": False, "error": "Not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            self._json(200, _generate(payload))
        except Exception as error:
            try:
                import torch

                if isinstance(error, torch.cuda.OutOfMemoryError):
                    torch.cuda.empty_cache()
            except Exception:
                pass
            self._json(500, {"ok": False, "error": str(error)})

    def log_message(self, fmt, *args):
        print(f"{self.address_string()} - {fmt % args}", flush=True)


def main():
    load_dotenv(".env", override=True)
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=31416)
    args = parser.parse_args()

    os.environ.setdefault("HF_HOME", str(Path.cwd() / ".hf_cache"))
    os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(Path.cwd() / ".hf_cache" / "hub"))
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    token = os.getenv("HUGGINGFACE_TOKEN") or os.getenv("HF_TOKEN")
    if token:
        os.environ["HF_TOKEN"] = token

    print(f"Starting WSL Z-Image FlashAttention worker on {args.host}:{args.port}", flush=True)
    _load_pipe()
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()

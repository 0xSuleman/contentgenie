import os
from pathlib import Path

from dotenv import load_dotenv


def _absolute_path(value: str, default: str) -> str:
    path = Path(value or default)
    if not path.is_absolute():
        path = Path.cwd() / path
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def main():
    load_dotenv("./.env", override=True)

    repo_id = os.getenv("ZIMAGE_REPO_ID") or os.getenv("ZIMAGE_MODEL_ID") or "Tongyi-MAI/Z-Image-Turbo"
    local_dir = _absolute_path(os.getenv("ZIMAGE_LOCAL_MODEL_PATH"), ".hf_models/Z-Image-Turbo")
    gguf_repo_id = os.getenv("ZIMAGE_GGUF_REPO_ID", "jayn7/Z-Image-Turbo-GGUF")
    gguf_file = os.getenv("ZIMAGE_GGUF_FILE", "z_image_turbo-Q4_K_M.gguf")
    gguf_path = Path(os.getenv("ZIMAGE_GGUF_TRANSFORMER_PATH", f".hf_models/Z-Image-Turbo-GGUF/{gguf_file}"))
    if not gguf_path.is_absolute():
        gguf_path = Path.cwd() / gguf_path
    gguf_path.parent.mkdir(parents=True, exist_ok=True)

    text_encoder_gguf_repo_id = os.getenv("ZIMAGE_TEXT_ENCODER_GGUF_REPO_ID", "unsloth/Qwen3-4B-GGUF")
    text_encoder_gguf_file = os.getenv("ZIMAGE_TEXT_ENCODER_GGUF_FILE", "Qwen3-4B-Q4_K_M.gguf")
    text_encoder_gguf_path = Path(
        os.getenv("ZIMAGE_TEXT_ENCODER_GGUF_PATH", f".hf_models/Qwen3-4B-GGUF/{text_encoder_gguf_file}")
    )
    if not text_encoder_gguf_path.is_absolute():
        text_encoder_gguf_path = Path.cwd() / text_encoder_gguf_path
    text_encoder_gguf_path.parent.mkdir(parents=True, exist_ok=True)
    cache_root = _absolute_path(os.getenv("HF_HOME"), ".hf_cache")
    cache_dir = _absolute_path(os.getenv("HUGGINGFACE_HUB_CACHE"), str(Path(cache_root) / "hub"))

    os.environ["HF_HOME"] = cache_root
    os.environ["HUGGINGFACE_HUB_CACHE"] = cache_dir
    os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = os.getenv("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    os.environ["HF_HUB_DISABLE_XET"] = os.getenv("HF_HUB_DISABLE_XET", "1")
    os.environ["HF_XET_HIGH_PERFORMANCE"] = os.getenv("HF_XET_HIGH_PERFORMANCE", "0")

    token = os.getenv("HUGGINGFACE_TOKEN") or os.getenv("HF_TOKEN") or None
    if token:
        os.environ["HF_TOKEN"] = token

    from huggingface_hub import snapshot_download

    print(f"Downloading {repo_id} to {local_dir}")
    snapshot_download(
        repo_id=repo_id,
        local_dir=local_dir,
        cache_dir=cache_dir,
        token=token,
        max_workers=int(os.getenv("HF_DOWNLOAD_WORKERS", "1")),
    )

    if not gguf_path.exists():
        from huggingface_hub import hf_hub_download

        print(f"Downloading GGUF transformer {gguf_repo_id}/{gguf_file} to {gguf_path}")
        downloaded_path = hf_hub_download(
            repo_id=gguf_repo_id,
            filename=gguf_file,
            local_dir=str(gguf_path.parent),
            cache_dir=cache_dir,
            token=token,
        )
        if Path(downloaded_path) != gguf_path and not gguf_path.exists():
            raise RuntimeError(f"GGUF transformer did not download to {gguf_path}")

    if not text_encoder_gguf_path.exists():
        from huggingface_hub import hf_hub_download

        print(
            f"Downloading GGUF text encoder {text_encoder_gguf_repo_id}/{text_encoder_gguf_file} "
            f"to {text_encoder_gguf_path}"
        )
        downloaded_path = hf_hub_download(
            repo_id=text_encoder_gguf_repo_id,
            filename=text_encoder_gguf_file,
            local_dir=str(text_encoder_gguf_path.parent),
            cache_dir=cache_dir,
            token=token,
        )
        if Path(downloaded_path) != text_encoder_gguf_path and not text_encoder_gguf_path.exists():
            raise RuntimeError(f"GGUF text encoder did not download to {text_encoder_gguf_path}")

    import torch
    from diffusers import GGUFQuantizationConfig, ZImagePipeline, ZImageTransformer2DModel
    from transformers import Qwen3Model

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA PyTorch is installed incorrectly: torch.cuda.is_available() is false")

    dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    print(f"Loading GGUF transformer from {gguf_path}")
    quantization_config = GGUFQuantizationConfig(compute_dtype=dtype)
    try:
        transformer = ZImageTransformer2DModel.from_single_file(
            str(gguf_path),
            quantization_config=quantization_config,
            torch_dtype=dtype,
        )
    except TypeError:
        transformer = ZImageTransformer2DModel.from_single_file(
            str(gguf_path),
            quantization_config=quantization_config,
            dtype=dtype,
        )

    text_encoder_dir = Path(local_dir) / "text_encoder"
    print(f"Loading GGUF text encoder from {text_encoder_gguf_path}")
    try:
        text_encoder = Qwen3Model.from_pretrained(
            str(text_encoder_dir),
            gguf_file=str(text_encoder_gguf_path),
            torch_dtype=dtype,
        )
    except TypeError:
        text_encoder = Qwen3Model.from_pretrained(
            str(text_encoder_dir),
            gguf_file=str(text_encoder_gguf_path),
            dtype=dtype,
        )

    low_cpu_mem_usage = os.getenv("ZIMAGE_LOW_CPU_MEM_USAGE", "true").strip().lower() not in {"0", "false", "no", "off"}
    device_map = os.getenv("ZIMAGE_DEVICE_MAP", "cuda").strip() or None
    load_kwargs = {
        "torch_dtype": dtype,
        "low_cpu_mem_usage": low_cpu_mem_usage,
        "use_safetensors": True,
        "transformer": transformer,
        "text_encoder": text_encoder,
    }
    if device_map:
        load_kwargs["device_map"] = device_map
        if device_map in {"auto", "balanced", "balanced_low_0"}:
            load_kwargs["max_memory"] = {
                0: os.getenv("ZIMAGE_MAX_GPU_MEMORY", "14GiB"),
                "cpu": os.getenv("ZIMAGE_MAX_CPU_MEMORY", "24GiB"),
            }
    print(f"Loading {local_dir} on {torch.cuda.get_device_name(0)} with dtype={dtype}")
    try:
        pipe = ZImagePipeline.from_pretrained(local_dir, **load_kwargs)
    except TypeError:
        load_kwargs["dtype"] = load_kwargs.pop("torch_dtype")
        pipe = ZImagePipeline.from_pretrained(local_dir, **load_kwargs)
    if not device_map:
        pipe.to("cuda")
    print("Local Z-Image-Turbo is downloaded and ready for CUDA inference.")


if __name__ == "__main__":
    main()

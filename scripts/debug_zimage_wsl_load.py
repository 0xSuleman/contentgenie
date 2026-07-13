import os
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(".env", override=True)


def tick(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


tick("start")
tick(f"cwd={Path.cwd()}")

tick("import flash_attn")
import flash_attn

tick(f"flash_attn={getattr(flash_attn, '__version__', 'installed')}")

tick("import torch")
import torch

tick(f"torch={torch.__version__} cuda={torch.cuda.is_available()} device={torch.cuda.get_device_name(0)}")

tick("import diffusers/transformers")
from diffusers import GGUFQuantizationConfig, ZImagePipeline, ZImageTransformer2DModel
from transformers import Qwen3Model

dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
tick(f"dtype={dtype}")

model_dir = Path(os.getenv("ZIMAGE_LOCAL_MODEL_PATH", ".hf_models/Z-Image-Turbo")).resolve()
transformer_path = Path(os.getenv("ZIMAGE_GGUF_TRANSFORMER_PATH", ".hf_models/Z-Image-Turbo-GGUF/z_image_turbo-Q4_K_M.gguf")).resolve()
text_encoder_path = Path(os.getenv("ZIMAGE_TEXT_ENCODER_GGUF_PATH", ".hf_models/Qwen3-4B-GGUF/Qwen3-4B-Q4_K_M.gguf")).resolve()

tick(f"model_dir={model_dir.exists()} {model_dir}")
tick(f"transformer_gguf={transformer_path.exists()} {transformer_path}")
tick(f"text_encoder_gguf={text_encoder_path.exists()} {text_encoder_path}")

tick("load transformer")
quantization_config = GGUFQuantizationConfig(compute_dtype=dtype)
transformer = ZImageTransformer2DModel.from_single_file(
    str(transformer_path),
    quantization_config=quantization_config,
    torch_dtype=dtype,
)
tick("transformer loaded")

tick("load text_encoder")
text_encoder = Qwen3Model.from_pretrained(
    str(model_dir / "text_encoder"),
    gguf_file=str(text_encoder_path),
    torch_dtype=dtype,
)
tick("text_encoder loaded")

tick("load pipeline")
pipe = ZImagePipeline.from_pretrained(
    str(model_dir),
    transformer=transformer,
    text_encoder=text_encoder,
    torch_dtype=dtype,
    low_cpu_mem_usage=False,
    use_safetensors=True,
)
tick("pipeline loaded")

tick("set flash attention")
pipe.transformer.set_attention_backend("flash")
tick("flash attention set")

tick("to cuda")
pipe.to("cuda")
tick("ready")

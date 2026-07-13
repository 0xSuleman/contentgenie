#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi

export PATH="$HOME/.local/bin:$PATH"

uv --version
uv python install 3.12
if [ ! -x .wsl_venv_zimage/bin/python ]; then
  uv venv .wsl_venv_zimage --python 3.12
fi

# shellcheck disable=SC1091
. .wsl_venv_zimage/bin/activate
python --version
uv pip install --python .wsl_venv_zimage/bin/python --upgrade pip setuptools wheel packaging ninja psutil

uv pip install --python .wsl_venv_zimage/bin/python --index-url https://download.pytorch.org/whl/cu128 torch torchvision torchaudio
uv pip install --python .wsl_venv_zimage/bin/python git+https://github.com/huggingface/diffusers transformers accelerate safetensors "huggingface_hub[hf_xet]" "gguf>=0.10.0" sentencepiece python-dotenv pillow requests protobuf
uv pip install --python .wsl_venv_zimage/bin/python \
  "https://github.com/lesj0610/flash-attention/releases/download/v2.8.3-cu12-torch2.11/flash_attn-2.8.3%2Bcu12torch2.11cxx11abiTRUE-cp312-cp312-linux_x86_64.whl"

python - <<'PY'
import flash_attn
import torch
from diffusers import ZImagePipeline

print("torch", torch.__version__)
print("cuda available", torch.cuda.is_available())
print("cuda device", torch.cuda.get_device_name(0) if torch.cuda.is_available() else None)
print("bf16 supported", torch.cuda.is_bf16_supported() if torch.cuda.is_available() else None)
print("flash_attn", getattr(flash_attn, "__version__", "installed"))
print("ZImagePipeline", ZImagePipeline)
PY

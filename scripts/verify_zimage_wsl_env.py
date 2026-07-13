import flash_attn
import torch
from diffusers import ZImagePipeline

print("flash_attn", getattr(flash_attn, "__version__", "installed"))
print("torch", torch.__version__)
print("cuda_available", torch.cuda.is_available())
print("cuda_device", torch.cuda.get_device_name(0) if torch.cuda.is_available() else None)
print("bf16_supported", torch.cuda.is_bf16_supported() if torch.cuda.is_available() else None)
print("ZImagePipeline", ZImagePipeline)

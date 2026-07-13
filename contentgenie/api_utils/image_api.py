import json
import os
import re
import subprocess
import threading
import time
import urllib.parse
from datetime import datetime
from pathlib import Path

import requests

from requests.adapters import HTTPAdapter
from urllib3 import Retry

from contentgenie.config.performance import get_float_setting, get_int_setting

POLLINATIONS_URL = "https://image.pollinations.ai/prompt/{prompt}"
Z_IMAGE_REPO_ID = os.getenv("ZIMAGE_REPO_ID") or os.getenv("ZIMAGE_MODEL_ID", "Tongyi-MAI/Z-Image-Turbo")
Z_IMAGE_HF_URL = f"https://api-inference.huggingface.co/models/{Z_IMAGE_REPO_ID}"

IMAGE_PROVIDER_POLLINATIONS = "pollinations"
IMAGE_PROVIDER_ZIMAGE = "zimage"
IMAGE_PROVIDER_ZIMAGE_LOCAL = "zimage_local"
IMAGE_PROVIDER_BING = "bing"
IMAGE_PROVIDER_ALIASES = {
    "pollination": IMAGE_PROVIDER_POLLINATIONS,
    "pollinations.ai": IMAGE_PROVIDER_POLLINATIONS,
    "pollinations": IMAGE_PROVIDER_POLLINATIONS,
    "hf": IMAGE_PROVIDER_ZIMAGE,
    "huggingface": IMAGE_PROVIDER_ZIMAGE,
    "hugging_face": IMAGE_PROVIDER_ZIMAGE,
    "z-image": IMAGE_PROVIDER_ZIMAGE,
    "zimage": IMAGE_PROVIDER_ZIMAGE,
    "z_image": IMAGE_PROVIDER_ZIMAGE,
    "z-image-local": IMAGE_PROVIDER_ZIMAGE_LOCAL,
    "zimage-local": IMAGE_PROVIDER_ZIMAGE_LOCAL,
    "zimage_local": IMAGE_PROVIDER_ZIMAGE_LOCAL,
    "local_zimage": IMAGE_PROVIDER_ZIMAGE_LOCAL,
    "z_image_local": IMAGE_PROVIDER_ZIMAGE_LOCAL,
    "zimage_turbo": IMAGE_PROVIDER_ZIMAGE_LOCAL,
    "z-image-turbo": IMAGE_PROVIDER_ZIMAGE_LOCAL,
    "bing": IMAGE_PROVIDER_BING,
    "search": IMAGE_PROVIDER_BING,
}

_WSL_ZIMAGE_PROCESS = None
_WSL_ZIMAGE_LOCK = threading.Lock()
_WSL_ZIMAGE_LOG_HANDLE = None


def normalizeImageProvider(provider: str = "") -> str:
    provider = (provider or IMAGE_PROVIDER_POLLINATIONS).strip().lower()
    return IMAGE_PROVIDER_ALIASES.get(provider, IMAGE_PROVIDER_POLLINATIONS)


def _default_image_path(index: int = 0) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return str(Path(".editing_assets") / "generated_images" / f"scene_{index}_{timestamp}.jpg")


def _clean_image_prompt(prompt: str) -> str:
    return re.sub(r"\s+", " ", (prompt or "").replace("\n", " ")).strip()


def _normalize_image_dimension(value: int, default: int = 720) -> int:
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = default
    value = max(512, min(1536, value))
    return max(512, (value // 16) * 16)


def _write_image_response(response: requests.Response, output_path: str) -> str:
    content_type = response.headers.get("content-type", "").lower()
    if content_type and not content_type.startswith("image/"):
        raise Exception(f"Image provider returned non-image response: {response.text[:200]}")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as image_file:
        image_file.write(response.content)
    return output_path


def generateImagePollinations(prompt: str, output_path: str = None, index: int = 0,
                              width: int = 720, height: int = 720, model: str = "flux") -> str:
    """Generate an image with Pollinations.ai and return the local file path."""
    output_path = output_path or _default_image_path(index)
    clean_prompt = _clean_image_prompt(prompt)
    if not clean_prompt:
        raise Exception("Image prompt is empty")

    params = {
        "width": width,
        "height": height,
        "model": model,
        "nologo": "true",
    }
    url = POLLINATIONS_URL.format(prompt=requests.utils.quote(clean_prompt, safe=""))
    response = requests.get(url, params=params, timeout=90)
    response.raise_for_status()
    return _write_image_response(response, output_path)


def generateImageZImage(prompt: str, output_path: str = None, index: int = 0, hf_token: str = None) -> str:
    """Generate an image with Z-Image through HuggingFace Inference and return the local file path."""
    output_path = output_path or _default_image_path(index)
    clean_prompt = _clean_image_prompt(prompt)
    if not clean_prompt:
        raise Exception("Image prompt is empty")

    hf_token = hf_token or os.getenv("HUGGINGFACE_TOKEN")
    if not hf_token:
        raise Exception("HUGGINGFACE_TOKEN is required for Z-Image")

    headers = {"Authorization": f"Bearer {hf_token}"}
    response = requests.post(
        Z_IMAGE_HF_URL,
        headers=headers,
        json={"inputs": clean_prompt},
        timeout=120,
    )

    if response.status_code == 503:
        try:
            estimated_time = float(response.json().get("estimated_time", 0))
        except Exception:
            estimated_time = 0
        if estimated_time:
            time.sleep(estimated_time + 5)
            response = requests.post(
                Z_IMAGE_HF_URL,
                headers=headers,
                json={"inputs": clean_prompt},
                timeout=120,
            )

    response.raise_for_status()
    return _write_image_response(response, output_path)


def _windows_path_to_wsl(path: str) -> str:
    if not path:
        return path
    path = str(Path(path).resolve())
    if len(path) >= 3 and path[1:3] == ":\\":
        drive = path[0].lower()
        return f"/mnt/{drive}/{path[3:].replace(chr(92), '/')}"
    return path.replace("\\", "/")


def _wsl_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _get_wsl_worker_url() -> str:
    host = os.getenv("ZIMAGE_WSL_WORKER_HOST", "127.0.0.1").strip() or "127.0.0.1"
    port = os.getenv("ZIMAGE_WSL_WORKER_PORT", "31416").strip() or "31416"
    return f"http://{host}:{port}"


def _wsl_worker_health(timeout: float = 2.0) -> bool:
    try:
        response = requests.get(f"{_get_wsl_worker_url()}/health", timeout=timeout)
        return response.status_code == 200
    except requests.RequestException:
        return False


def _start_wsl_zimage_worker():
    global _WSL_ZIMAGE_LOG_HANDLE, _WSL_ZIMAGE_PROCESS
    if _wsl_worker_health(timeout=1.0):
        return

    with _WSL_ZIMAGE_LOCK:
        if _wsl_worker_health(timeout=1.0):
            return

        distro = os.getenv("ZIMAGE_WSL_DISTRO", "Ubuntu").strip() or "Ubuntu"
        project_dir = _windows_path_to_wsl(str(Path.cwd()))
        venv_dir = os.getenv("ZIMAGE_WSL_VENV", ".wsl_venv_zimage").strip() or ".wsl_venv_zimage"
        port = os.getenv("ZIMAGE_WSL_WORKER_PORT", "31416").strip() or "31416"
        log_path = Path(os.getenv("ZIMAGE_WSL_WORKER_LOG", ".editing_assets/zimage_wsl_worker.log"))
        log_path.parent.mkdir(parents=True, exist_ok=True)
        command = (
            f"cd {_wsl_quote(project_dir)} && "
            f"exec {_wsl_quote(venv_dir)}/bin/python -u scripts/zimage_wsl_worker.py "
            f"--host 0.0.0.0 --port {int(port)}"
        )
        _WSL_ZIMAGE_LOG_HANDLE = open(log_path, "ab", buffering=0)
        _WSL_ZIMAGE_PROCESS = subprocess.Popen(
            ["wsl", "-d", distro, "--", "bash", "-lc", command],
            stdout=_WSL_ZIMAGE_LOG_HANDLE,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

        timeout = get_float_setting("ZIMAGE_WSL_WORKER_START_TIMEOUT", 420.0, 10.0, 1800.0)
        deadline = time.time() + timeout
        while time.time() < deadline:
            if _wsl_worker_health(timeout=3.0):
                return
            time.sleep(2)
        raise Exception(f"WSL Z-Image worker did not become ready within {timeout:.0f}s. See {log_path}.")


def _generate_image_zimage_wsl(prompt: str, output_path: str, index: int,
                               width: int, height: int, seed: int = None) -> str:
    _start_wsl_zimage_worker()
    response = requests.post(
        f"{_get_wsl_worker_url()}/generate",
        json={
            "prompt": prompt,
            "output_path": output_path,
            "index": index,
            "width": width,
            "height": height,
            "seed": seed,
        },
        timeout=get_float_setting("ZIMAGE_WSL_GENERATE_TIMEOUT", 900.0, 30.0, 3600.0),
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise Exception(payload.get("error", "WSL Z-Image worker failed"))
    return payload["output_path"]


def preloadLocalZImage() -> bool:
    """Start the WSL FlashAttention Z-Image worker and load the model into GPU memory."""
    _start_wsl_zimage_worker()
    return True


def generateImageZImageLocal(prompt: str, output_path: str = None, index: int = 0,
                             width: int = 720, height: int = 720, seed: int = None) -> str:
    output_path = output_path or _default_image_path(index)
    clean_prompt = _clean_image_prompt(prompt)
    if not clean_prompt:
        raise Exception("Image prompt is empty")

    width = _normalize_image_dimension(width)
    height = _normalize_image_dimension(height)
    return _generate_image_zimage_wsl(clean_prompt, output_path, index, width, height, seed=seed)


def generateAiImage(prompt: str, provider: str = IMAGE_PROVIDER_POLLINATIONS, output_path: str = None,
                    index: int = 0, hf_token: str = None, width: int = 720, height: int = 720) -> str:
    provider = normalizeImageProvider(provider)
    if provider == IMAGE_PROVIDER_ZIMAGE_LOCAL:
        return generateImageZImageLocal(prompt, output_path=output_path, index=index, width=width, height=height)
    if provider == IMAGE_PROVIDER_ZIMAGE:
        return generateImageZImage(prompt, output_path=output_path, index=index, hf_token=hf_token)
    if provider == IMAGE_PROVIDER_POLLINATIONS:
        return generateImagePollinations(prompt, output_path=output_path, index=index, width=width, height=height)
    raise Exception(f"Unsupported AI image provider: {provider}")


def _extractBingImages(html):
    pattern = r'mediaurl=(.*?)&amp;.*?expw=(\d+).*?exph=(\d+)'
    matches = re.findall(pattern, html)
    result = []

    for match in matches:
        url, width, height = match
        if url.endswith('.jpg') or url.endswith('.png') or url.endswith('.jpeg'):
            result.append({'url': urllib.parse.unquote(url), 'width': int(width), 'height': int(height)})

    return result


def _extractGoogleImages(html):
  images = []
  regex = re.compile(r"AF_initDataCallback\({key: 'ds:1', hash: '2', data:(.*?), sideChannel: {}}\);")
  match = regex.search(html)
  if match:
      dz = json.loads(match.group(1))         
      for c in dz[56][1][0][0][1][0]:
          try:
              thing = list(c[0][0].values())[0]
              images.append(thing[1][3])
          except:
              pass
  return images


def getBingImages(query, retries=5):
    query = query.replace(" ", "+")
    images = []
    tries = 0
    
    # Create a session with custom retry strategy
    session = requests.Session()
    retry_strategy = Retry(
        total=retries,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    
    while(len(images) == 0 and tries < retries):
        try:
            # Use verify=False to bypass SSL verification (use with caution)
            response = session.get(
                f"https://www.bing.com/images/search?q={query}&first=1",
                verify=False,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }
            )
            if(response.status_code == 200):
                images = _extractBingImages(response.text)
            else:
                print("Error While making bing image searches", response.text)
                raise Exception("Error While making bing image searches")
        except requests.exceptions.SSLError as e:
            print(f"SSL Error occurred (attempt {tries + 1}/{retries}): {str(e)}")
            tries += 1
            if tries >= retries:
                raise Exception("Max retries reached - SSL Error while making Bing image searches")
            continue
        
    if(images):
        return images
    raise Exception("Error While making bing image searches")

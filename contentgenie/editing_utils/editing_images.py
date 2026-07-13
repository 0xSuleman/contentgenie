from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from contentgenie.api_utils.image_api import (
    IMAGE_PROVIDER_ZIMAGE_LOCAL,
    generateAiImage,
    getBingImages,
    normalizeImageProvider,
)
from contentgenie.config.api_db import ApiKeyManager
from contentgenie.config.render_settings import get_image_generation_size, get_visual_style_prompt
from tqdm import tqdm
from PIL import Image
import random
import math


def _get_configured_image_provider():
    return IMAGE_PROVIDER_ZIMAGE_LOCAL


def _get_configured_image_size():
    return get_image_generation_size()


def _get_generated_image_path(asset_dir, index):
    base_dir = Path(asset_dir or ".editing_assets/generated_images")
    base_dir.mkdir(parents=True, exist_ok=True)
    return str(base_dir / f"generated_image_{index}.jpg")


def _valid_generated_image(path):
    candidate = Path(path)
    if not candidate.is_file() or candidate.stat().st_size < 1024:
        return False
    try:
        with Image.open(candidate) as image:
            image.verify()
        return True
    except (OSError, ValueError):
        return False


def _get_image_worker_count(provider, total_items):
    if total_items <= 1:
        return 1
    if provider == IMAGE_PROVIDER_ZIMAGE_LOCAL:
        return 1

    configured_workers = ApiKeyManager.get_api_key("IMAGE_WORKERS") or 4
    try:
        configured_workers = int(configured_workers)
    except (TypeError, ValueError):
        configured_workers = 4
    return max(1, min(configured_workers, total_items, 8))


def _enhance_generated_image_prompt(query):
    return f"{query}, {get_visual_style_prompt()}"


def getImageUrlsTimed(imageTextPairs, image_provider=None, asset_dir=None):
    provider = normalizeImageProvider(image_provider or _get_configured_image_provider())
    imageTextPairs = list(imageTextPairs)
    if not imageTextPairs:
        return []

    workers = _get_image_worker_count(provider, len(imageTextPairs))

    def generate_pair(index, pair):
        return (
            pair[0],
            searchImageUrlsFromQuery(
                pair[1],
                image_provider=provider,
                output_path=_get_generated_image_path(asset_dir, index),
                index=index,
            ),
        )

    if workers == 1:
        return [
            generate_pair(index, pair)
            for index, pair in enumerate(tqdm(imageTextPairs, desc=f'{provider} queries for images...'))
        ]

    results = [None] * len(imageTextPairs)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(generate_pair, index, pair): index
            for index, pair in enumerate(imageTextPairs)
        }
        for future in tqdm(as_completed(futures), total=len(futures), desc=f'{provider} queries for images...'):
            index = futures[future]
            results[index] = future.result()
    return results


def generateImageFiles(image_prompts, image_provider=None, asset_dir=None):
    prompts = []
    for item in image_prompts or []:
        if isinstance(item, dict):
            prompt = str(item.get("prompt") or item.get("visual_prompt") or item.get("scene") or item.get("query") or "").strip()
        else:
            prompt = str(item).strip()
        if prompt:
            prompts.append(prompt)
    generated = getImageUrlsTimed(
        [(index, prompt) for index, prompt in enumerate(prompts)],
        image_provider=image_provider,
        asset_dir=asset_dir,
    )
    return [path for _index, path in generated]


def _searchBingImageUrl(query, top=3, expected_dim=[720,720], retries=5):
    images = getBingImages(query, retries=retries)
    if(images):
        distances = list(map(lambda x: math.dist([x['width'], x['height']], expected_dim), images[0:top]))
        shortest_ones = sorted(distances)
        random.shuffle(shortest_ones)
        for distance in shortest_ones:
            image_url = images[distances.index(distance)]['url']
            return image_url
    return None


def searchImageUrlsFromQuery(query, top=3, expected_dim=[720,720], retries=5,
                             image_provider=None, output_path=None, index=0):
    provider = normalizeImageProvider(image_provider or _get_configured_image_provider())
    if provider != IMAGE_PROVIDER_ZIMAGE_LOCAL:
        raise Exception("AI image generation is configured for zimage_local FlashAttention only.")

    width, height = _get_configured_image_size()
    if output_path and _valid_generated_image(output_path):
        return output_path
    prompt = _enhance_generated_image_prompt(query)
    hf_token = ApiKeyManager.get_api_key("HUGGINGFACE_TOKEN")

    return generateAiImage(
        prompt,
        provider=IMAGE_PROVIDER_ZIMAGE_LOCAL,
        output_path=output_path,
        index=index,
        hf_token=hf_token,
        width=width,
        height=height,
    )

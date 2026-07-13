import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from contentgenie.api_utils.image_api import generateImageZImageLocal


if __name__ == "__main__":
    output = generateImageZImageLocal(
        "a cinematic close up of a futuristic city at sunrise, high quality, no text, no watermark",
        output_path=".editing_assets/zimage_test.jpg",
        width=512,
        height=512,
    )
    print(output)

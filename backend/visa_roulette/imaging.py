"""Safe image decoding for untrusted uploads."""

import io

from PIL import Image, UnidentifiedImageError

from visa_roulette.errors import ScanError

MAX_PIXELS = 40_000_000


def load_image(data: bytes) -> Image.Image:
    try:
        image = Image.open(io.BytesIO(data))
        if image.width * image.height > MAX_PIXELS:
            raise ScanError("too_large", "That image has too many pixels.", 413)
        image.load()
    except ScanError:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, ValueError):
        raise ScanError("invalid_image", "That is not a readable image (use PNG, JPEG or WebP).") from None
    return image.convert("RGB")

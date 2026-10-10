"""Bounded raster validation, quality-controlled compression, and square cropping."""

from __future__ import annotations

import logging
import warnings
from pathlib import Path

from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

MAX_DIMENSION = 1600
MAX_IMAGE_PIXELS = 25_000_000
ALLOWED_RASTER_FORMATS = {"BMP", "GIF", "ICO", "JPEG", "PNG", "WEBP"}

# Vector files are not processed by the raster compressor.
_SKIP_SUFFIXES = {".svg"}


def validate_raster_image_file(path: Path) -> None:
    """Validate actual raster bytes independently of filename and declared MIME."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as image:
                image_format = (image.format or "").upper()
                width, height = image.size
                if image_format not in ALLOWED_RASTER_FORMATS:
                    raise ValueError("Desteklenmeyen görsel biçimi.")
                if width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS:
                    raise ValueError("Görsel boyutları güvenli sınırı aşıyor.")
                image.verify()
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError("Görsel boyutları güvenli sınırı aşıyor.") from exc
    except (OSError, SyntaxError) as exc:
        raise ValueError("Dosya geçerli bir raster görsel değil.") from exc


COMPRESSION_PROFILES = ((4096, 95), (3072, 92), (2400, 86), (1920, 80), (1600, 72))


def compress_image_file(path: Path, max_dimension: int | None = None, *, level: int = 2) -> None:
    """Compress staging bytes with bounded resizing and preserved transparency.

    JPEG/WebP use graded quality; PNG remains lossless. Failures reject the
    staged upload rather than publishing an incompletely processed image.
    """
    if path.suffix.lower() in _SKIP_SUFFIXES:
        return

    if type(level) is not int or not 0 <= level < len(COMPRESSION_PROFILES):
        raise ValueError("Invalid image compression level")
    limit, quality = COMPRESSION_PROFILES[level]
    max_dimension = max_dimension or limit

    try:
        with Image.open(path) as img:
            source_format = img.format
            img = ImageOps.exif_transpose(img)

            if img.width > max_dimension or img.height > max_dimension:
                img.thumbnail((max_dimension, max_dimension), Image.LANCZOS)

            fmt = (source_format or "").upper()
            suffix = path.suffix.lower()

            if fmt in ("JPEG", "JPG") or suffix in (".jpg", ".jpeg"):
                if img.mode in ("RGBA", "P", "LA"):
                    img = img.convert("RGB")
            elif fmt == "WEBP" or suffix == ".webp":
                pass
            else:
                # Other supported rasters become optimized PNG.
                if img.mode not in ("RGBA", "RGB", "P", "L"):
                    img = img.convert("RGBA")
            img.load()

        # Close the source handle before replacing staged bytes in place.
        if fmt in ("JPEG", "JPG") or suffix in (".jpg", ".jpeg"):
            img.save(path, format="JPEG", quality=quality, optimize=True, progressive=True)
        elif fmt == "WEBP" or suffix == ".webp":
            img.save(path, format="WEBP", quality=quality, method=6)
        else:
            img.save(path, format="PNG", optimize=True)

        after = path.stat().st_size
        logger.info("Image compressed: size_kb=%.1f", after / 1024)
    except Exception as exc:
        logger.warning("Image compression failed: error_type=%s", type(exc).__name__)
        raise ValueError("Image processing failed") from exc


def make_square_icon(src_path: Path, dest_path: Path, size: int = 256) -> None:
    """Center-crop a raster to an optimized square PNG, preserving transparency."""
    validate_raster_image_file(src_path)
    with Image.open(src_path) as img:
        img = ImageOps.exif_transpose(img)
        if img.mode not in ("RGBA", "RGB", "L"):
            img = img.convert("RGBA")

        width, height = img.size
        side = min(width, height)
        left = (width - side) // 2
        top = (height - side) // 2
        img = img.crop((left, top, left + side, top + side))
        img = img.resize((size, size), Image.LANCZOS)
        img.load()

    # The source handle is closed before an optional in-place replacement.
    img.save(dest_path, format="PNG", optimize=True)
    logger.info("Automatic icon created: width=%d height=%d", size, size)

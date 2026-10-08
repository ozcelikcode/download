"""Bounded gallery paths and mandatory, metadata-free WebP processing."""

import json
import re
from pathlib import Path

from PIL import Image, ImageOps

from app.imaging import COMPRESSION_PROFILES, validate_raster_image_file

GALLERY_LIMITS = (3, 5, 10, 15, 20, 25)
GALLERY_PATH = re.compile(r'/static/uploads/gallery/[a-f0-9]{32}\.webp\Z')


def gallery_paths(value: str | None) -> list[str]:
    try:
        paths = json.loads(value or '[]')
    except (TypeError, ValueError):
        raise ValueError('Invalid gallery images') from None
    if not isinstance(paths, list) or len(paths) > 25 or any(not isinstance(path, str) or not GALLERY_PATH.fullmatch(path) for path in paths) or len(set(paths)) != len(paths):
        raise ValueError('Invalid gallery images')
    return paths


def prepare_gallery_image(path: Path, *, level: int = 2) -> None:
    validate_raster_image_file(path)
    limit, quality = COMPRESSION_PROFILES[level]
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source).convert('RGBA' if source.mode in {'RGBA', 'LA', 'P'} else 'RGB')
        image.thumbnail((limit, limit), Image.Resampling.LANCZOS)
        image.load()
    image.save(path, format='WEBP', quality=quality, method=6, exif=b'', icc_profile=b'')

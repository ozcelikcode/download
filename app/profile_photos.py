"""Private account photos stored against immutable user IDs, not usernames."""

from pathlib import Path

from fastapi import Request
from PIL import Image, ImageOps

from app.config import settings
from app.imaging import validate_raster_image_file

PHOTO_UPLOAD_LIMIT = 5 * 1024 * 1024


def photo_path(user_id: int) -> Path:
    root = settings.upload_path.resolve()
    directory = root / "icons" / ".profiles"
    path = directory / f"{int(user_id)}.webp"
    if user_id <= 0 or directory.parent.is_symlink() or directory.is_symlink() or path.is_symlink():
        raise ValueError("Unsafe profile photo storage")
    return path


def photo_url(request: Request) -> str | None:
    user_id = getattr(request.state, "admin_id", None)
    if user_id is None:
        return None
    try:
        path = photo_path(user_id)
        if path.is_file():
            return f"/panel/account/photo?v={path.stat().st_mtime_ns}"
    except (OSError, ValueError):
        pass
    return None


def prepare_photo(path: Path) -> None:
    """Validate actual raster bytes, correct orientation, crop, and strip metadata."""
    validate_raster_image_file(path)
    with Image.open(path) as source:
        oriented = ImageOps.exif_transpose(source).convert("RGBA")
        fitted = ImageOps.fit(oriented, (256, 256), method=Image.Resampling.LANCZOS)
        # A new image carries no EXIF, location data, source comments or animation.
        clean = Image.new("RGBA", fitted.size)
        clean.paste(fitted)
    clean.save(path, format="WEBP", quality=82, method=6)

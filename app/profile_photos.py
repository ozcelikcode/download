"""Private account photos stored against immutable user IDs, not usernames."""

from pathlib import Path
from functools import lru_cache
import re

from fastapi import Request
from PIL import Image, ImageOps

from app.config import settings
from app.imaging import validate_raster_image_file

PHOTO_UPLOAD_LIMIT = 5 * 1024 * 1024
PROFILE_ICONS = ("user-circle", "user", "user-round", "circle-user-round", "contact-round", "smile", "code", "pen-tool", "book-open", "camera", "palette")


@lru_cache(maxsize=1)
def available_profile_icons() -> frozenset[str]:
    """Accept only names exported by the pinned, locally shipped Lucide bundle."""
    bundle = Path(__file__).parent / 'static/vendor/lucide/1.24.0/lucide.min.js'
    names = re.findall(r'\ba\.([A-Z][A-Za-z0-9]*)=', bundle.read_text(encoding='utf-8'))
    return frozenset(re.sub(r'(?<!^)(?=[A-Z])', '-', name).lower() for name in names)


def valid_profile_icon(value: object) -> bool:
    return isinstance(value, str) and len(value) <= 50 and value in available_profile_icons()


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


def publisher_photo_url(request: Request, publisher: object) -> str | None:
    if publisher is None or not publisher.is_active or publisher.deleted_at is not None:
        return None
    if request.url.path.startswith('/panel'):
        return photo_url(request) if publisher.id == getattr(request.state, 'admin_id', None) else None
    try:
        path = photo_path(publisher.id)
        if path.is_file():
            return f"/publisher/{publisher.id}/photo?v={path.stat().st_mtime_ns}"
    except (OSError, ValueError):
        pass
    return None

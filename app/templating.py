"""
Paylaşılan Jinja2Templates örneği ve özel filtreler/globals.

Tüm router'lar bu modülden import eder — tek kaynak.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi.templating import Jinja2Templates

from app.config import settings
from app.models import FileType, IconType

templates = Jinja2Templates(directory="app/templates")


# ---------------------------------------------------------------------------
# Özel filtreler
# ---------------------------------------------------------------------------

def _format_date(value: Optional[datetime], fmt: str = "%d.%m.%Y") -> str:
    if value is None:
        return "-"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.strftime(fmt)


def _human_size(value: Optional[int]) -> str:
    if value is None:
        return ""
    size = float(value)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _icon_name(icon_type: IconType, file_type: FileType) -> str:
    """
    Lucide icon adını döndürür.
    https://lucide.dev/icons/
    """
    mapping = {
        IconType.zip: "archive",
        IconType.pdf: "file-text",
        IconType.link: "external-link",
        IconType.image: "image",
        IconType.exe: "monitor",
        IconType.apk: "smartphone",
        IconType.dmg: "apple",   # en yakın alternatif
        IconType.deb: "terminal",
        IconType.auto: "download",
    }
    if icon_type == IconType.auto:
        return "link" if file_type == FileType.external else "download"
    return mapping.get(icon_type, "file")


def _pluralize(count: int, singular: str, plural: str) -> str:
    return singular if count == 1 else plural


def _thousands(value: Optional[int]) -> str:
    if value is None:
        return "0"
    return f"{value:,}".replace(",", ".")


# ---------------------------------------------------------------------------
# Filtre / global kayıt
# ---------------------------------------------------------------------------

templates.env.filters["format_date"] = _format_date
templates.env.filters["human_size"] = _human_size
templates.env.filters["icon_name"] = _icon_name
templates.env.filters["pluralize"] = _pluralize
templates.env.filters["thousands"] = _thousands

# Global: site başlığı (.env APP_NAME'den gelir)
templates.env.globals["site_name"] = settings.app_name

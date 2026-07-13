"""
Paylaşılan Jinja2Templates örneği ve özel filtreler/globals.

Tüm router'lar bu modülden import eder — tek kaynak.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional

from fastapi.templating import Jinja2Templates

from app.branding import resolve_icon_color
from app.config import settings
from app.models import FileType, IconType, SiteSettings

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


_EXTENSION_ICON_MAP = {
    "zip": "archive", "rar": "archive", "7z": "archive", "tar": "archive", "gz": "archive",
    "pdf": "file-text",
    "exe": "monitor", "msi": "monitor",
    "apk": "smartphone",
    "dmg": "apple", "pkg": "apple",
    "deb": "terminal", "rpm": "terminal",
    "iso": "disc",
    "mp4": "video", "mov": "video", "avi": "video", "mkv": "video",
    "mp3": "music", "wav": "music",
    "doc": "file-text", "docx": "file-text",
    "xls": "file-spreadsheet", "xlsx": "file-spreadsheet",
    "ppt": "presentation", "pptx": "presentation",
}


def _icon_name(
    icon_type: IconType, file_type: FileType, extension: Optional[str] = None
) -> str:
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
    if icon_type == IconType.extension:
        ext = (extension or "").lower().lstrip(".")
        return _EXTENSION_ICON_MAP.get(ext, "file")
    if icon_type == IconType.auto:
        return "link" if file_type == FileType.external else "download"
    return mapping.get(icon_type, "file")


def _pluralize(count: int, singular: str, plural: str) -> str:
    return singular if count == 1 else plural


def _thousands(value: Optional[int]) -> str:
    if value is None:
        return "0"
    return f"{value:,}".replace(",", ".")


def _pagination_range(current: int, total: int, edge: int = 2, around: int = 1) -> list:
    """
    Uzun sayfalama listelerinde taşmayı önlemek için "1 2 3 … 10 11 12" tarzı
    kısaltılmış sayfa numarası listesi üretir. `None` değerleri "…" (ellipsis)
    yer tutucusudur.
    """
    if total <= 1:
        return [1]

    pages = set()
    for i in range(1, edge + 1):
        pages.add(i)
    for i in range(total - edge + 1, total + 1):
        pages.add(i)
    for i in range(current - around, current + around + 1):
        if 1 <= i <= total:
            pages.add(i)

    ordered = sorted(p for p in pages if 1 <= p <= total)
    result: list = []
    prev: Optional[int] = None
    for p in ordered:
        if prev is not None and p - prev > 1:
            result.append(None)
        result.append(p)
        prev = p
    return result


# ---------------------------------------------------------------------------
# Filtre / global kayıt
# ---------------------------------------------------------------------------

templates.env.filters["format_date"] = _format_date
templates.env.filters["human_size"] = _human_size
templates.env.filters["icon_name"] = _icon_name
templates.env.filters["pluralize"] = _pluralize
templates.env.filters["thousands"] = _thousands
templates.env.globals["pagination_range"] = _pagination_range

# Global: statik CSS dosyalarının cache-busting sürüm numarası. Tarayıcının
# `make css` sonrası eski tailwind.css/app.css'i önbellekten göstermeye devam
# etmesini önler — dosya değiştikçe link'in sonuna eklenen ?v= değeri de değişir.
def _css_asset_version() -> int:
    paths = ["app/static/css/tailwind.css", "app/static/css/app.css"]
    mtimes = [os.path.getmtime(p) for p in paths if os.path.exists(p)]
    return int(max(mtimes)) if mtimes else 0


templates.env.globals["css_asset_v"] = _css_asset_version()

# Global: site başlığı (.env APP_NAME'den gelir) — SiteSettings yüklenene kadarki varsayılan.
templates.env.globals["site_name"] = settings.app_name
templates.env.globals["site_icon"] = "download-cloud"
templates.env.globals["site_icon_color_light"], templates.env.globals["site_icon_color_dark"] = (
    resolve_icon_color("blue")
)
templates.env.globals["admin_icon"] = "user-circle"
templates.env.globals["admin_icon_color_light"], templates.env.globals["admin_icon_color_dark"] = (
    resolve_icon_color("slate")
)


def refresh_site_branding_globals(site_settings: SiteSettings) -> None:
    """SiteSettings veritabanı satırından Jinja global'lerini günceller.

    Uygulama başlangıcında (main.py lifespan) ve admin site kimliği/profil
    ikonu kaydedildiğinde çağrılır — böylece sunucu yeniden başlatılmadan
    değişiklik anında yansır.
    Not: çoklu worker'da (ör. `make prod`) her worker kendi bellek-içi kopyasını
    tutar; diğer worker'lar bir sonraki isteklerinde eski değeri göstermeye devam
    edebilir (bu proje ölçeğinde kabul edilebilir bir sınırlama).
    """
    templates.env.globals["site_name"] = site_settings.site_name
    templates.env.globals["site_icon"] = site_settings.site_icon
    light, dark = resolve_icon_color(site_settings.site_icon_color)
    templates.env.globals["site_icon_color_light"] = light
    templates.env.globals["site_icon_color_dark"] = dark

    templates.env.globals["admin_icon"] = site_settings.admin_icon
    admin_light, admin_dark = resolve_icon_color(site_settings.admin_icon_color)
    templates.env.globals["admin_icon_color_light"] = admin_light
    templates.env.globals["admin_icon_color_dark"] = admin_dark

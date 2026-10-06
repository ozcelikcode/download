"""Shared Jinja2 templates, filters, and globals for all routers."""

from __future__ import annotations

import re
from pathlib import Path
from datetime import datetime
from typing import Optional
from urllib.parse import quote

from fastapi.templating import Jinja2Templates

from app.branding import resolve_accent_theme, resolve_icon_color
from app.config import settings
from app.content_security import safe_http_url, safe_navigation_url, sanitize_rich_text
from app.models import FileType, IconType, SiteSettings
from app.seo import inspect_public_base_url

from app.security import csrf_token
from app.timezones import local_datetime
from app.i18n import LANGUAGE_CHOICES, date_locale, og_locale, set_ui_language, translate, translate_format, ui_language, system_message

templates = Jinja2Templates(directory="app/templates")

templates.env.globals["csrf_token"] = csrf_token
templates.env.globals["t"] = translate
templates.env.globals["tf"] = translate_format
templates.env.globals["system_message"] = system_message
templates.env.globals["ui_language"] = ui_language
templates.env.globals["og_locale"] = og_locale
templates.env.globals["date_locale"] = date_locale
templates.env.globals["language_choices"] = LANGUAGE_CHOICES
from app.trash_retention import expires_at, days_remaining
templates.env.globals["trash_expires_at"] = expires_at
templates.env.globals["trash_days_remaining"] = days_remaining
templates.env.globals.update({
    "theme_color": "blue", "theme_accent_light": "#356fd4", "theme_accent_dark": "#72a7e8",
    "theme_surface_light": "#eaf2fc", "theme_surface_dark": "#152033",
    "theme_border_light": "#b8d0ee", "theme_border_dark": "#36577f",
})


# ---------------------------------------------------------------------------
# Custom filters.
# ---------------------------------------------------------------------------

def _format_date(value: Optional[datetime], fmt: str = "%d.%m.%Y") -> str:
    if value is None:
        return "-"
    return local_datetime(value, templates.env.globals.get("site_timezone", "UTC")).strftime(fmt)


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
    """Return the matching Lucide icon name (https://lucide.dev/icons/)."""
    mapping = {
        IconType.zip: "archive",
        IconType.pdf: "file-text",
        IconType.link: "external-link",
        IconType.image: "image",
        IconType.exe: "monitor",
        IconType.apk: "smartphone",
        IconType.dmg: "apple",   # Closest available icon.
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
    """Return a compact page range; ``None`` marks an ellipsis."""
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
# Register filters and globals.
# ---------------------------------------------------------------------------

templates.env.filters["format_date"] = _format_date
templates.env.filters["human_size"] = _human_size
templates.env.filters["icon_name"] = _icon_name
templates.env.filters["pluralize"] = _pluralize
templates.env.filters["thousands"] = _thousands
templates.env.filters["sanitize_html"] = sanitize_rich_text
templates.env.filters["safe_http_url"] = safe_http_url
templates.env.filters["safe_navigation_url"] = safe_navigation_url
templates.env.globals["pagination_range"] = _pagination_range


def _qs_override(params: dict, **overrides) -> str:
    """Merge query parameters without dropping unrelated filter or page state."""
    merged = {**params, **overrides}
    parts = [
        f"{k}={quote(str(v))}" for k, v in merged.items() if v not in (None, "")
    ]
    return "?" + "&".join(parts) if parts else ""


templates.env.globals["qs_override"] = _qs_override


def _canonical_url(request) -> str:
    base_url, _, _ = inspect_public_base_url()
    if base_url is None:
        return ""
    path = request.url.path
    # Exclude filter/search variants from canonical URLs; retain real page numbers.
    page = request.query_params.get("page")
    try:
        page_number = int(page or "")
    except ValueError:
        page_number = 0
    page_suffix = f"?page={page_number}" if page_number > 1 else ""
    return f"{base_url}{path}{page_suffix}"


templates.env.globals["canonical_url"] = _canonical_url

# Resolve current asset versions during rendering, not only at process startup.
def _css_asset_version() -> int:
    paths = [Path("app/static/css/tailwind.css"), Path("app/static/css/app.css")]
    paths.extend(Path("app/static/js").glob("*.js"))
    mtimes = []
    for path in paths:
        try:
            mtimes.append(path.stat().st_mtime_ns)
        except FileNotFoundError:
            continue
    return max(mtimes, default=0)


templates.env.globals["css_asset_v"] = _css_asset_version

# Defaults used until SiteSettings has been loaded.
templates.env.globals["site_name"] = settings.app_name
templates.env.globals["site_language"] = "en"
templates.env.globals["site_timezone"] = "UTC"
templates.env.globals["site_icon"] = "download-cloud"
templates.env.globals["logo_mode"] = "icon_text"
templates.env.globals["logo_light_path"] = None
templates.env.globals["favicon_path"] = None


def favicon_url() -> str | None:
    """Invalidate browser caches after an existing icon is edited in place."""
    path = templates.env.globals.get("favicon_path")
    if not isinstance(path, str) or not re.fullmatch(r"/static/uploads/icons/[a-f0-9]{12}\.png", path):
        return None
    file = settings.upload_path / "icons" / Path(path).name
    try:
        if not file.is_file():
            return None
        version = file.stat().st_mtime_ns
    except OSError:
        return None
    return f"{path}?v={version}"


templates.env.globals["favicon_url"] = favicon_url
templates.env.globals["logo_dark_path"] = None
templates.env.globals["site_icon_color_light"], templates.env.globals["site_icon_color_dark"] = (
    resolve_icon_color("blue")
)
templates.env.globals["admin_icon"] = "user-circle"
templates.env.globals["admin_icon_color_light"], templates.env.globals["admin_icon_color_dark"] = (
    resolve_icon_color("slate")
)


def refresh_site_branding_globals(site_settings: SiteSettings) -> None:
    """Refresh Jinja globals from SiteSettings without restarting the server.

    This process-local cache assumes the supported single-worker deployment.
    """
    templates.env.globals["site_name"] = site_settings.site_name
    templates.env.globals["site_language"] = site_settings.site_language
    templates.env.globals["site_timezone"] = site_settings.site_timezone
    set_ui_language(site_settings.site_language)
    templates.env.globals["site_icon"] = site_settings.site_icon
    templates.env.globals["logo_mode"] = site_settings.logo_mode
    templates.env.globals["logo_light_path"] = site_settings.logo_light_path
    templates.env.globals["logo_dark_path"] = site_settings.logo_dark_path
    templates.env.globals["favicon_path"] = site_settings.favicon_path
    light, dark = resolve_icon_color(site_settings.site_icon_color)
    templates.env.globals["site_icon_color_light"] = light
    templates.env.globals["site_icon_color_dark"] = dark
    accent_light, accent_dark, surface_light, surface_dark, border_light, border_dark = resolve_accent_theme(site_settings.theme_color)
    templates.env.globals["theme_color"] = site_settings.theme_color
    templates.env.globals["theme_accent_light"] = accent_light
    templates.env.globals["theme_accent_dark"] = accent_dark
    templates.env.globals["theme_surface_light"] = surface_light
    templates.env.globals["theme_surface_dark"] = surface_dark
    templates.env.globals["theme_border_light"] = border_light
    templates.env.globals["theme_border_dark"] = border_dark

    templates.env.globals["admin_icon"] = site_settings.admin_icon
    admin_light, admin_dark = resolve_icon_color(site_settings.admin_icon_color)
    templates.env.globals["admin_icon_color_light"] = admin_light
    templates.env.globals["admin_icon_color_dark"] = admin_dark

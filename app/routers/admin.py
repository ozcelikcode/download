"""
Admin router — şifre korumalı yönetim paneli.

Rotalar:
  GET  /panel/logout                 → Çıkış
  GET  /panel                        → Dashboard (özet: son 5 içerik + istatistikler)
  GET  /panel/downloads              → İçerikler (tam liste, arama/filtre/sayfalama)
  GET  /panel/downloads/new          → Yeni dosya formu
  POST /panel/downloads/new          → Dosya oluştur
  GET  /panel/downloads/{id}/edit    → Düzenle formu
  POST /panel/downloads/{id}/edit    → Dosya güncelle
  POST /panel/downloads/{id}/delete  → İçeriği Silinenler'e taşı
  GET  /panel/downloads/trash        → Silinenler
  GET  /panel/categories             → Kategori listesi
  POST /panel/categories             → Kategori oluştur
  POST /panel/categories/{id}/edit   → Kategori güncelle
  POST /panel/categories/{id}/delete → Kategori sil
  GET  /panel/tags                   → Tag listesi
  POST /panel/tags                   → Tag oluştur
  POST /panel/tags/{id}/edit         → Tag güncelle
  POST /panel/tags/{id}/delete       → Tag sil
  GET  /panel/media                  → Medya arşivi (resim + dosya)
  GET  /panel/settings/menu           → Menü düzenleme
  POST /panel/settings/menu           → Menü öğesi oluştur
  POST /panel/settings/menu/{id}/edit → Menü öğesi güncelle
  POST /panel/settings/menu/{id}/delete → Menü öğesi sil
  POST /panel/settings/menu/reorder   → Menü sırasını güncelle (AJAX)
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import re
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote, unquote, urlencode, urljoin, urlsplit

import httpx
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from starlette.background import BackgroundTask
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select, func, text

from app import crud
from app.branding import SITE_ICON_COLORS
from app.config import settings
from app.content_security import normalize_navigation_url, safe_http_url
from app.default_content import HERO_TEXT
from app.database import AsyncSessionLocal
from app.health import get_admin_site_health
from app.imaging import compress_image_file, make_square_icon, validate_raster_image_file
from starlette.concurrency import run_in_threadpool
from app.i18n import translate, system_message
from app.link_checks import resolve_public_url
from app.dependencies import (
    get_db,
    get_request_ip,
    hash_password_async,
    require_admin,
    verify_password_async,
    SESSION_COOKIE,
)
from app.models import Download, FileType, IconType, Page, Tag, User
from app.ownership import require_owned_media
from app.media import delete_unused_media, media_path, media_usage
from app.pagination import PageNumber
from app.validation import MAX_RECORD_ID, RecordId
from app.routers.public import build_download_detail_context
from app.schemas import (
    CategoryCreate,
    CategoryUpdate,
    DownloadCreate,
    DownloadUpdate,
    MenuItemCreate,
    MenuItemUpdate,
    AppearanceSettingsUpdate,
    SeoSettingsUpdate,
    SiteSettingsUpdate,
    TagCreate,
)
from app.templating import refresh_site_branding_globals, templates
from app.uploads import STAGING_PREFIXES, save_upload
from app.storage_quota import publish_media, quota_bytes, usage_bytes
from app.audit import add_event
from app.timezones import TIMEZONE_CHOICES, validate_timezone
from app.security import clear_successful_attempt, require_csrf, reserve_login_attempt
import secrets

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/panel", tags=["admin"], dependencies=[Depends(require_csrf)])

_ACTIVE_WEB_EXTENSIONS = {
    ".css", ".htm", ".html", ".js", ".mjs", ".svg", ".svgz", ".xhtml", ".xml",
}
_ACTIVE_WEB_CONTENT_TYPES = {
    "application/javascript", "application/xhtml+xml", "image/svg+xml", "text/css",
    "text/html", "text/javascript", "text/xml",
}
_SAFE_IMAGE_EXTENSIONS = {".bmp", ".gif", ".ico", ".jpeg", ".jpg", ".png", ".webp"}
_REMOTE_IMAGE_TYPES = {
    "image/bmp": ".bmp", "image/gif": ".gif", "image/jpeg": ".jpg",
    "image/png": ".png", "image/webp": ".webp", "image/x-icon": ".ico",
    "image/vnd.microsoft.icon": ".ico",
}

# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------

def _redirect(path: str) -> RedirectResponse:
    return RedirectResponse(url=path, status_code=status.HTTP_302_FOUND)


def _download_form_error(request: Request, exc: Exception) -> str:
    """Doğrulama ayrıntılarını ve gönderilen veriyi kullanıcı mesajından çıkar."""
    if isinstance(exc, ValidationError):
        labels = {
            "title": "title", "version": "version",
            "external_url": "external_url", "icon_image_url": "image_url",
            "short_description": "short_description",
        }
        messages = []
        for error in exc.errors(include_url=False, include_input=False):
            message = system_message(request, error["msg"].removeprefix("Value error, "))
            if error["type"] in {"string_too_long", "string_too_short"}:
                limit_key = "max_length" if error["type"] == "string_too_long" else "min_length"
                message = translate(request, error["type"]).format(limit=error["ctx"][limit_key])
            field = str(error["loc"][0]) if error["loc"] else ""
            if field in labels:
                message = f"{translate(request, labels[field])}: {message}"
            if message not in messages:
                messages.append(message)
        return " ".join(messages)
    if isinstance(exc, ValueError):
        return system_message(request, str(exc))
    return translate(request, "content_save_failed")


def _gallery_form_paths(value: str | None) -> list[str] | None:
    from app.gallery import gallery_paths
    return gallery_paths(value) if value is not None else None


def _same_admin_page(request: Request, fallback: str) -> str:
    """Yönlendirmeyi yalnızca bu uygulamadaki admin sayfalarında tutar."""
    candidate = request.query_params.get("return_to") or fallback
    parsed = urlsplit(candidate)
    if (
        parsed.scheme
        or parsed.netloc
        or "\\" in candidate
        or parsed.path not in {"/panel"} and not parsed.path.startswith("/panel/")
    ):
        return fallback
    return candidate


def _int_or_none(value: Optional[str]) -> Optional[int]:
    """Parse an optional positive SQLite identity without overflowing bindings."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        parsed = int(s)
        return parsed if 1 <= parsed <= MAX_RECORD_ID else None
    except (ValueError, TypeError):
        return None


def _form_bool(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _wants_json(request: Request) -> bool:
    return "application/json" in request.headers.get("accept", "")


def _ensure_safe_public_upload(filename: str | None, content_type: str | None) -> None:
    suffix = Path((filename or "").replace("\\", "/")).suffix.lower()
    normalized_type = (content_type or "").split(";", 1)[0].strip().lower()
    if suffix in _ACTIVE_WEB_EXTENSIONS or normalized_type in _ACTIVE_WEB_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Tarayıcıda çalışabilen HTML, SVG, JavaScript ve CSS dosyaları yüklenemez.",
        )


def _stored_download_path(value: object) -> Optional[str]:
    path = media_path(str(value or ""))
    private_root = settings.download_path.resolve()
    return (
        str(path)
        if path is not None
        and path.is_file()
        and path.is_relative_to(private_root)
        else None
    )


def _parse_file_size_to_bytes(value_str: Optional[str], unit: str) -> Optional[int]:
    """Sayısal değer ve birim (B, KB, MB, GB) ikilisini byte değerine dönüştürür."""
    if not value_str:
        return None
    s = str(value_str).strip()
    if not s:
        return None
    try:
        val = float(s)
        if val <= 0:
            return None
        unit = str(unit).upper().strip()
        if unit == "KB":
            return int(val * 1024)
        elif unit == "MB":
            return int(val * 1024 * 1024)
        elif unit == "GB":
            return int(val * 1024 * 1024 * 1024)
        else:
            return int(val)
    except (ValueError, TypeError):
        return None


def _deconstruct_file_size(bytes_val: Optional[int]) -> tuple[Optional[float], str]:
    """Byte değerini en uygun birim (B, KB, MB, GB) ve sayısal değere geri çözer."""
    if bytes_val is None:
        return None, "MB"
    val = float(bytes_val)
    if val >= 1024 * 1024 * 1024:
        res = val / (1024 * 1024 * 1024)
        return int(res) if res.is_integer() else round(res, 2), "GB"
    elif val >= 1024 * 1024:
        res = val / (1024 * 1024)
        return int(res) if res.is_integer() else round(res, 2), "MB"
    elif val >= 1024:
        res = val / 1024
        return int(res) if res.is_integer() else round(res, 2), "KB"
    return int(bytes_val), "B"



async def _save_upload(file: UploadFile, session: AsyncSession) -> str:
    """Publish a quota-checked download outside the public web root."""
    _ensure_safe_public_upload(file.filename, file.content_type)
    upload_dir = settings.download_path
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / _unique_upload_filename(file.filename)
    await save_upload(file, dest, publisher=lambda staged, target: publish_media(session, staged, target))
    logger.info("File uploaded")
    return str(dest)


def _unique_icon_filename(original_name: str, fallback_ext: str = ".png") -> str:
    """Çakışmaları önlemek için orijinal ada kısa bir uuid ön eki ekler."""
    safe_name = Path(original_name or "").name
    ext = Path(safe_name).suffix.lower()
    if ext not in _SAFE_IMAGE_EXTENSIONS:
        ext = fallback_ext
    return f"{uuid.uuid4().hex[:12]}{ext}"


async def _save_icon_upload(file: UploadFile, session: AsyncSession, compress: bool | None = None) -> str:
    """Validate and optionally compress an icon before quota-checked publication."""
    icons_dir = settings.upload_path / "icons"
    icons_dir.mkdir(parents=True, exist_ok=True)
    filename = _unique_icon_filename(file.filename)
    dest = icons_dir / filename
    result_path = f"/static/uploads/icons/{filename}"
    policy = await crud.get_site_settings(session)
    compress = policy.image_compression_enabled if compress is None else compress
    level = policy.image_compression_level
    try:
        def prepare(staged: Path) -> None:
            validate_raster_image_file(staged)
            if compress:
                compress_image_file(staged, level=level)

        async def publish(staged: Path, target: Path) -> None:
            nonlocal result_path
            result_path = await publish_media(session, staged, target, reuse_identical=True)

        await save_upload(file, dest, validator=prepare,
                          publisher=publish)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info("Icon uploaded: compressed=%s", compress)
    return result_path


def _resolve_icon_path(path: str) -> Path:
    """Bir ikon web yolunu ('/static/uploads/icons/x.png') gerçek disk yoluna çevirir.
    Yalnızca dosya adı kullanılır — dizin gezinmesine (path traversal) izin verilmez."""
    return settings.upload_path / "icons" / Path(unquote(path or "")).name


async def _replace_icon_upload(file: UploadFile, existing_path: str, session: AsyncSession) -> str:
    """Replace a prepared icon, copying shared illustrations before editing."""
    dest = _resolve_icon_path(existing_path)
    if not dest.is_file():
        raise HTTPException(status_code=404, detail="Kaynak görsel bulunamadı.")
    if dest.suffix.lower() not in _SAFE_IMAGE_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Güvensiz görsel uzantısı yerinde güncellenemez.")
    result_path = existing_path
    async def publish(staged: Path, target: Path) -> None:
        nonlocal result_path
        result_path = await publish_media(session, staged, target, copy_if_shared=True)
    try:
        await save_upload(file, dest, validator=validate_raster_image_file,
                          publisher=publish)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info("Icon replaced in place")
    return result_path


# İlerleme durumu: {token: {"percent": int, "done": bool, "error": str|None, "path": str|None}}
# Tek worker'lı geliştirme sunucusu için bellek-içi; çoklu worker'da paylaşılmaz.
_icon_fetch_progress: dict[str, dict] = {}


async def _fetch_icon_from_url(url: str, token: str, uploaded_by: str, actor_info: dict | None = None,
                               square_size: int | None = None, compression: bool | None = None) -> None:
    """Stream an external image to staging, then validate, process, and publish it."""
    dest: Optional[Path] = None
    staged: Optional[Path] = None
    try:
        current = httpx.URL(url)
        visited: set[str] = set()
        for _ in range(6):
            if str(current) in visited:
                raise ValueError("Yönlendirme döngüsü tespit edildi.")
            visited.add(str(current))
            ip = await resolve_public_url(current)
            pinned = current.copy_with(host=ip)
            headers = {"Host": current.netloc.decode("ascii"), "User-Agent": "DownloadSite-ImageFetch/1.0"}
            async with httpx.AsyncClient(follow_redirects=False, timeout=30.0, trust_env=False) as client:
                async with client.stream(
                    "GET",
                    pinned,
                    headers=headers,
                    extensions={"sni_hostname": current.host},
                ) as resp:
                    if resp.status_code in {301, 302, 303, 307, 308}:
                        location = resp.headers.get("location")
                        if not location:
                            raise ValueError("Yönlendirme adresi eksik.")
                        current = httpx.URL(urljoin(str(current), location))
                        continue
                    resp.raise_for_status()
                    content_type = (resp.headers.get("content-type") or "").split(";")[0].strip()
                    if content_type not in _REMOTE_IMAGE_TYPES:
                        raise ValueError("Bağlantı bir görsel dosyası döndürmüyor.")

                    total = int(resp.headers.get("content-length") or 0)
                    if total > settings.max_upload_size_bytes:
                        raise ValueError("Dosya yükleme boyutu sınırını aşıyor.")
                    ext = ".png" if square_size else _REMOTE_IMAGE_TYPES[content_type]
                    icons_dir = settings.upload_path / "icons"
                    icons_dir.mkdir(parents=True, exist_ok=True)
                    filename = f"{uuid.uuid4().hex[:12]}{ext}"
                    dest = icons_dir / filename
                    fd, name = tempfile.mkstemp(prefix=".remote-", suffix=".part", dir=icons_dir)
                    os.close(fd)
                    staged = Path(name)

                    received = 0
                    with staged.open("wb") as out:
                        async for chunk in resp.aiter_bytes(chunk_size=65536):
                            received += len(chunk)
                            if received > settings.max_upload_size_bytes:
                                raise ValueError("Dosya yükleme boyutu sınırını aşıyor.")
                            out.write(chunk)
                            percent = min(90, int(received * 90 / total)) if total else 90
                            _icon_fetch_progress[token]["percent"] = percent
                break
        else:
            raise ValueError("Çok fazla yönlendirme.")

        _icon_fetch_progress[token].update({"percent": 92, "phase": "compressing"})
        final_path = f"/static/uploads/icons/{filename}"
        async with AsyncSessionLocal() as session:
            policy = await crud.get_site_settings(session)
            def prepare() -> None:
                validate_raster_image_file(staged)
                if square_size:
                    make_square_icon(staged, staged, size=square_size)
                elif (policy.image_compression_enabled if compression is None else compression):
                    compress_image_file(staged, level=policy.image_compression_level)
            await run_in_threadpool(prepare)
            session.info["audit_actor"] = uploaded_by
            session.info["actor_id"] = _icon_fetch_progress[token].get("owner_id")
            session.info.update(actor_info or {})
            final_path = await publish_media(session, staged, dest, reuse_identical=True)
        _icon_fetch_progress[token].update(
            {"percent": 100, "done": True, "phase": "done", "path": final_path}
        )
        logger.info("Remote image downloaded")
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.error("Remote image download failed: error_type=%s", type(exc).__name__)
        _icon_fetch_progress[token].update({"done": True, "error": str(exc.detail) if isinstance(exc, HTTPException) else str(exc)})
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)


async def _fetch_icon_with_timeout(url: str, token: str, uploaded_by: str, actor_info: dict | None = None,
                                  square_size: int | None = None, compression: bool | None = None) -> None:
    try:
        await asyncio.wait_for(_fetch_icon_from_url(url, token, uploaded_by, actor_info, square_size, compression), timeout=60)
    except TimeoutError:
        _icon_fetch_progress[token].update({"done": True, "error": "Bağlantı kontrolü zaman aşımına uğradı."})


# ---------------------------------------------------------------------------
# Medya Arşivi — sisteme yüklenmiş tüm resim ve dosyaların listesi
# ---------------------------------------------------------------------------

_IMAGE_EXTS = {"png", "jpg", "jpeg", "gif", "webp", "bmp", "ico"}

_MEDIA_ICON_MAP = {
    "zip": "archive", "rar": "archive", "7z": "archive", "tar": "archive", "gz": "archive",
    "pdf": "file-text", "txt": "file-text", "doc": "file-text", "docx": "file-text",
    "xls": "file-spreadsheet", "xlsx": "file-spreadsheet",
    "ppt": "presentation", "pptx": "presentation",
    "exe": "monitor", "msi": "monitor",
    "apk": "smartphone",
    "dmg": "apple", "pkg": "apple",
    "deb": "terminal", "rpm": "terminal",
    "mp4": "video", "mov": "video", "avi": "video", "mkv": "video",
    "mp3": "music", "wav": "music",
}

# Dosya Arşivi'nde tür filtresi için kategori grupları
_TYPE_CATEGORIES: dict[str, set] = {
    "archive": {"zip", "rar", "7z", "tar", "gz"},
    "document": {"pdf", "txt", "doc", "docx", "xls", "xlsx", "ppt", "pptx"},
    "executable": {"exe", "msi"},
    "apk": {"apk"},
    "mac": {"dmg", "pkg"},
    "linux": {"deb", "rpm"},
    "video": {"mp4", "mov", "avi", "mkv"},
    "audio": {"mp3", "wav"},
}
_TYPE_CATEGORY_LABELS: dict[str, str] = {
    "archive": "archive", "document": "document", "executable": "Windows (EXE)",
    "apk": "Android (APK)", "mac": "macOS", "linux": "Linux",
    "video": "video", "audio": "audio", "other": "other",
}
_MEDIA_PAGE_SIZES = [12, 24, 48, 96]


def _media_human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _guess_media_icon(ext: str) -> str:
    ext = ext.lower().lstrip(".")
    if ext in _IMAGE_EXTS:
        return "image"
    return _MEDIA_ICON_MAP.get(ext, "file")


def _media_type_category(ext: str) -> str:
    ext = ext.lower().lstrip(".")
    for cat, exts in _TYPE_CATEGORIES.items():
        if ext in exts:
            return cat
    return "other"


def _list_media_files(directory: Path, url_prefix: str) -> List[dict]:
    """List ordinary visible files, tolerating concurrent removal."""
    items: List[dict] = []
    if directory.exists():
        for p in directory.iterdir():
            if p.name.startswith(".") or p.is_symlink():
                continue
            try:
                if not p.is_file():
                    continue
                stat = p.stat()
            except OSError:
                continue
            ext = p.suffix.lstrip(".").lower()
            items.append(
                {
                    "name": p.name,
                    "url": f"{url_prefix}/{quote(p.name)}",
                    "size_human": _media_human_size(stat.st_size),
                    "modified": datetime.fromtimestamp(stat.st_mtime),
                    "ext": ext,
                    "icon": _guess_media_icon(ext),
                    "is_image": ext in _IMAGE_EXTS,
                    "type_category": _media_type_category(ext),
                    "can_crop": url_prefix == "/static/uploads/icons",
                }
            )
    items.sort(key=lambda x: x["modified"], reverse=True)
    return items


def _build_download_media_maps(downloads: List) -> tuple[dict, dict]:
    """
    Fiziksel dosya adına göre (uzantı/dizin farkı gözetmeksizin) hangi
    indirmenin bu ikonu/dosyayı kullandığını bulmak için iki eşleme üretir:
    icon dosya adı → Download, yerel dosya adı → Download.
    """
    icon_map: dict[str, object] = {}
    file_map: dict[str, object] = {}
    for d in downloads:
        if d.icon_image_path:
            icon_map[Path(d.icon_image_path).name] = d
        if d.file_type == FileType.local and d.file_path:
            file_map[Path(d.file_path).name] = d
    return icon_map, file_map


def _paginate_media(
    request: Request,
    items: List[dict],
    prefix: str,
    downloads_map: dict,
) -> dict:
    """Tek bir sekme (images/files) için arama + sayfalama uygular, bağlı
    içerik bilgisini ekler. Sonuç, template'e geçirilecek bir bağlam sözlüğüdür."""
    q = (request.query_params.get(f"{prefix}_q") or "").strip().lower()
    try:
        page = max(1, int(request.query_params.get(f"{prefix}_page", "1")))
    except ValueError:
        page = 1
    try:
        page_size = int(request.query_params.get(f"{prefix}_page_size", "24"))
    except ValueError:
        page_size = 24
    if page_size not in _MEDIA_PAGE_SIZES:
        page_size = 24

    # Bağlı içerik bilgisini ekle
    for item in items:
        d = downloads_map.get(item["name"])
        item["linked_download"] = (
            {"id": d.id, "title": d.title, "os_compatibility": d.os_compatibility}
            if d else None
        )

    if q:
        items = [it for it in items if q in it["display_name"].lower() or q in it["name"].lower()]

    if prefix == "files":
        type_filter = request.query_params.get("files_type") or ""
        if type_filter:
            items = [it for it in items if it["type_category"] == type_filter]
        os_filter = request.query_params.get("files_os") or ""
        if os_filter:
            items = [
                it for it in items
                if it["linked_download"] and os_filter in (it["linked_download"]["os_compatibility"] or "").split(",")
            ]

    total = len(items)
    total_pages = max(1, math.ceil(total / page_size))
    page = min(page, total_pages)
    start = (page - 1) * page_size
    page_items = items[start:start + page_size]

    return {
        "results": page_items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "q": q,
    }


@router.get("/media", name="admin_media")
async def media_view(
    request: Request,
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
):
    quota_account = await crud.get_site_settings(session)
    quota_user = await session.get(User, session.info["actor_id"])
    storage_limit = quota_bytes(quota_user, quota_account)
    storage_used = await usage_bytes(session, quota_user.id)
    upload_root = settings.upload_path
    icons_dir = upload_root / "icons"

    images = await run_in_threadpool(_list_media_files, icons_dir, "/static/uploads/icons")
    images += await run_in_threadpool(_list_media_files, upload_root / "gallery", "/static/uploads/gallery")
    images.sort(key=lambda item: item["modified"], reverse=True)
    files = await run_in_threadpool(_list_media_files, settings.download_path, "/panel/media/files")
    usage = await media_usage(session, str(request.base_url))
    for item in images + files:
        item["used_by"] = usage.get(media_path(item["url"]), [])

    # Link (path) hiçbir zaman değişmez; kullanıcı yalnızca görünen adı
    # düzenler. Bu, fiziksel dosya adından bağımsız ayrı bir alandır.
    all_paths = [item["url"] for item in images] + [item["url"] for item in files]
    assets = await crud.get_media_assets_info(session, all_paths)
    if session.info.get("editor_owner_id") is not None:
        images = [item for item in images if item["url"] in assets]
        files = [item for item in files if item["url"] in assets]
    for item in images + files:
        asset = assets.get(item["url"])
        item["display_name"] = (asset.display_name if asset and asset.display_name else None) or item["name"]
        item["uploaded_by"] = asset.uploaded_by if asset else None
        item["uploaded_at"] = asset.created_at if asset else None

    all_downloads = await crud.get_all_downloads_for_media_matching(session)
    icon_map, file_map = _build_download_media_maps(all_downloads)

    images_ctx = _paginate_media(request, images, "images", icon_map)
    files_ctx = _paginate_media(request, files, "files", file_map)

    active_tab = request.query_params.get("tab") or "images"
    if active_tab not in ("images", "files"):
        active_tab = "images"

    files_type = request.query_params.get("files_type") or ""
    files_os = request.query_params.get("files_os") or ""

    current_params = {
        "tab": active_tab,
        "images_q": images_ctx["q"],
        "images_page": images_ctx["page"],
        "images_page_size": images_ctx["page_size"],
        "files_q": files_ctx["q"],
        "files_page": files_ctx["page"],
        "files_page_size": files_ctx["page_size"],
        "files_type": files_type,
        "files_os": files_os,
    }

    flash_message = request.session.pop("flash_message", None)

    return templates.TemplateResponse(
        request=request, name="admin/media.html",
        context={
            "request": request,
            "images": images_ctx,
            "files": files_ctx,
            "images_total_all": len(images),
            "files_total_all": len(files),
            "active_tab": active_tab,
            "page_sizes": _MEDIA_PAGE_SIZES,
            "storage_limit": storage_limit, "storage_used": storage_used,
            "type_categories": {key: translate(request, label) for key, label in _TYPE_CATEGORY_LABELS.items()},
            "files_type": files_type,
            "files_os": files_os,
            "current_params": current_params,
            "admin_user": _admin,
            "flash_message": flash_message,
        },
    )


def _unique_upload_filename(original_name: str) -> str:
    """Çakışmaları önlemek için orijinal dosya adının sonuna kısa bir uuid ekler."""
    safe_name = Path((original_name or "dosya").replace("\\", "/")).name
    stem = Path(safe_name).stem or "dosya"
    ext = Path(safe_name).suffix
    return f"{stem}-{uuid.uuid4().hex[:8]}{ext}"


@router.post("/media/upload-file", name="admin_media_upload_file")
async def media_upload_file(
    _admin: str = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
    file: UploadFile = File(...),
):
    """Dosya Arşivi için genel amaçlı dosya yükleme (herhangi bir tür, orijinal haliyle saklanır)."""
    _ensure_safe_public_upload(file.filename, file.content_type)
    upload_dir = settings.download_path
    upload_dir.mkdir(parents=True, exist_ok=True)
    filename = _unique_upload_filename(file.filename)
    dest = upload_dir / filename
    await save_upload(file, dest, publisher=lambda staged, target: publish_media(session, staged, target))
    web_path = f"/panel/media/files/{quote(filename)}"
    logger.info("File added to media library")
    return {"path": web_path, "storage_path": str(dest), "name": filename}


@router.get("/media/files/{filename:path}", name="admin_media_file")
async def media_file(
    filename: str,
    _admin: str = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    safe_name = Path(unquote(filename or "")).name
    if not safe_name or safe_name.startswith(STAGING_PREFIXES) or safe_name == ".gitkeep" or safe_name != unquote(filename):
        raise HTTPException(status_code=404, detail="Dosya bulunamadı.")
    await require_owned_media(session, f"/panel/media/files/{quote(safe_name)}")
    root = settings.download_path.resolve()
    try:
        path = (root / safe_name).resolve()
    except (OSError, RuntimeError) as exc:
        raise HTTPException(status_code=404, detail="Dosya bulunamadı.") from exc
    if not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(status_code=404, detail="Dosya bulunamadı.")
    if path.suffix.lower().lstrip(".") in _IMAGE_EXTS:
        return FileResponse(path)
    return FileResponse(
        path,
        filename=path.name,
        media_type="application/octet-stream",
    )


@router.post("/media/replace-file", name="admin_media_replace_file")
async def media_replace_file(
    _admin: str = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
    path: str = Form(...),
    file: UploadFile = File(...),
):
    """Dosya Arşivi'nde mevcut bir dosyanın İÇERİĞİNİ değiştirir; link/ad aynı kalır."""
    await require_owned_media(session, path, mutation=True)
    filename = Path(unquote(path or "")).name
    if not filename:
        raise HTTPException(status_code=400, detail="Geçersiz yol.")
    dest = media_path(path)
    if dest is None or not dest.is_file() or not dest.is_relative_to(settings.download_path.resolve()):
        raise HTTPException(status_code=404, detail="Kaynak dosya bulunamadı.")
    _ensure_safe_public_upload(dest.name, file.content_type)
    _ensure_safe_public_upload(file.filename, file.content_type)
    await save_upload(file, dest, publisher=lambda staged, target: publish_media(session, staged, target))
    logger.info("File replaced in place")
    add_event(session, "replace", "media_assets", path)
    await session.commit()
    return {"path": path}


@router.post("/media/delete-file", name="admin_media_delete_file")
async def media_delete_file(
    request: Request,
    _admin: str = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
    path: str = Form(...),
):
    """Delete unused library media with transactional filesystem recovery."""
    await delete_unused_media(session, path, str(request.base_url))
    return {"deleted": True}


@router.post("/media/rename", name="admin_media_rename")
async def media_rename(
    _admin: str = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
    path: str = Form(...),
    display_name: str = Form(""),
):
    """Bir medya öğesinin görünen adını değiştirir. Link (path) hiç değişmez;
    boş ad gönderilirse fiziksel dosya adına geri döner."""
    await require_owned_media(session, path)
    await crud.set_media_display_name(session, path, display_name)
    return {"ok": True, "display_name": display_name.strip() or Path(path).name}


# ---------------------------------------------------------------------------
# İkon görseli — AJAX yükleme / dış URL indirme / ilerleme / silme
# ---------------------------------------------------------------------------

@router.post("/upload/icon-image", name="admin_upload_icon_image")
async def upload_icon_image(
    _admin: str = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
    file: UploadFile = File(...),
    replace_path: Optional[str] = Form(None),
    skip_compression: bool = Form(False),
    compression: Optional[bool] = Form(None),
):
    if (file.content_type or "").split(";", 1)[0].strip().lower() not in _REMOTE_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Sadece görsel dosyaları yüklenebilir.")

    if replace_path:
        await require_owned_media(session, replace_path, mutation=True)
        # Yerinde güncelleme: link/dosya adı asla değişmez, sıkıştırma uygulanmaz
        # (kaynak — kırpma tuvali çıktısı — zaten işlenmiş kabul edilir).
        path = await _replace_icon_upload(file, replace_path, session)
        add_event(session, "replace", "media_assets", path)
        await session.commit()
    else:
        path = await _save_icon_upload(file, session, compress=False if skip_compression else compression)
    return {"path": path}


@router.post("/upload/icon-image-url", name="admin_upload_icon_image_url")
async def upload_icon_image_url(
    request: Request,
    _admin: str = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
    url: str = Form(...),
    token: str = Form(...),
    compression: Optional[bool] = Form(None),
):
    if token in _icon_fetch_progress:
        raise HTTPException(409)
    _icon_fetch_progress[token] = {
        "owner_id": request.state.admin_id,
        "percent": 0, "done": False, "error": None, "path": None, "phase": "downloading",
    }
    return JSONResponse({"started": True, "token": token},
                        background=BackgroundTask(_fetch_icon_with_timeout, url, token, _admin, dict(session.info), None, compression))


@router.get("/upload/progress/{token}", name="admin_upload_progress")
async def upload_progress(token: str, request: Request, _admin: str = Depends(require_admin)):
    data = _icon_fetch_progress.get(token)
    if not data or (request.state.admin_role == "editor" and data.get("owner_id") != request.state.admin_id):
        raise HTTPException(status_code=404, detail="Bilinmeyen işlem.")
    if data.get("done"):
        _icon_fetch_progress.pop(token, None)
    return {**data, "error": system_message(request, data["error"]) if data.get("error") else None}


@router.post("/upload/icon-image-delete", name="admin_upload_icon_image_delete")
async def delete_icon_image(
    request: Request,
    _admin: str = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
    path: str = Form(...),
):
    await delete_unused_media(session, path, str(request.base_url))
    return {"deleted": True}


@router.post("/upload/icon-auto-crop", name="admin_upload_icon_auto_crop")
async def upload_icon_auto_crop(
    _admin: str = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
    path: str = Form(...),
    size: int = Form(256),
    in_place: bool = Form(False),
):
    """Crop a stored icon in a worker, optionally preserving its public URL."""
    await require_owned_media(session, path, mutation=in_place)
    src = media_path(path)
    icon_root = (settings.upload_path / "icons").resolve()
    if src is None or src.parent != icon_root or src.name.startswith(".") or not src.is_file():
        raise HTTPException(status_code=404, detail="Kaynak görsel bulunamadı.")

    if in_place:
        dest = src
    else:
        dest = settings.upload_path / "icons" / f"{uuid.uuid4().hex[:12]}.png"

    fd, name = tempfile.mkstemp(prefix=".crop-", suffix=".part", dir=src.parent)
    os.close(fd)
    staged = Path(name)
    try:
        try:
            await run_in_threadpool(make_square_icon, src, staged, size=max(32, min(int(size), 1024)))
        except Exception as exc:
            logger.error("Automatic icon cropping failed: error_type=%s", type(exc).__name__)
            raise HTTPException(status_code=422, detail="Görsel işlenemedi.") from exc
        await publish_media(session, staged, dest)
    finally:
        staged.unlink(missing_ok=True)

    add_event(session, "crop", "media_assets", f"/static/uploads/icons/{dest.name}")
    await session.commit()
    return {"path": f"/static/uploads/icons/{dest.name}"}


# ---------------------------------------------------------------------------
# Login / Logout
# ---------------------------------------------------------------------------

@router.get("/login", include_in_schema=False)
async def legacy_login() -> RedirectResponse:
    """Keep old bookmarks usable without hosting a second sign-in form."""
    return RedirectResponse("/login", status_code=303)


@router.post("/logout", name="admin_logout")
async def logout(request: Request):
    request.session.clear()
    response = _redirect("/login")
    response.delete_cookie(SESSION_COOKIE)
    return response


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@router.get("", name="admin_dashboard")
@router.get("/", include_in_schema=False)
async def dashboard(
    request: Request,
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
):
    recent_items, _ = await crud.get_downloads_paginated(
        session, page=1, page_size=5, include_inactive=True, pin_featured=False
    )

    stats = await crud.get_dashboard_stats(session)
    from app.routers.notifications import snapshot
    notices = getattr(request.state, "panel_notices", None)
    if notices is None:
        notices = await snapshot(request, session)
    dashboard_updates = [item for item in notices["items"] if item["unread"] or (
        request.state.admin_role != "editor" and item["kind"] != "reports"
    )]
    if request.state.admin_role == "editor":
        return templates.TemplateResponse(request=request, name="admin/editor_dashboard.html", context={
            "request": request, "stats": stats, "recent_items": recent_items, "dashboard_updates": dashboard_updates,
            "pending_deletions": await session.scalar(select(func.count()).select_from(Download).where(Download.deletion_pending.is_(True), Download.deleted_at.is_not(None))) or 0,
            "admin_user": _admin, "flash_message": request.session.pop("flash_message", None),
        })
    site_health = await get_admin_site_health(session)
    recent_activity = await crud.get_recent_audit_logs(session)
    flash_message = request.session.pop("flash_message", None)

    return templates.TemplateResponse(
        request=request, name="admin/dashboard.html",
        context={
            "request": request,
            "recent_items": recent_items,
            "stats": stats,
            "health": site_health.summary,
            "seo_warning_count": site_health.seo_warning_count,
            "configuration_attention_count": site_health.configuration_attention_count,
            "recent_activity": recent_activity,
            "dashboard_updates": dashboard_updates,
            "admin_user": _admin,
            "flash_message": flash_message,
        },
    )


@router.get("/site-health", name="admin_site_health")
async def site_health(
    request: Request,
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
):
    report = await get_admin_site_health(session)
    site_settings = await crud.get_site_settings(session)
    flash_message = request.session.pop("flash_message", None)
    flash_type = request.session.pop("flash_type", "success")
    return templates.TemplateResponse(
        request=request,
        name="admin/site_health.html",
        context={
            "request": request,
            "admin_user": _admin,
            "site_health": report,
            "site_settings": site_settings,
            "flash_message": flash_message,
            "flash_type": flash_type,
        },
    )


# ---------------------------------------------------------------------------
# İçerikler — tüm indirmelerin filtrelenebilir/aranabilir tam listesi
# ---------------------------------------------------------------------------

@router.get("/downloads", name="admin_content_list")
async def content_list(
    request: Request,
    page: PageNumber = 1,
    q: Optional[str] = None,
    category_id: Optional[str] = None,
    status_filter: Optional[str] = None,
    file_type_filter: Optional[str] = None,
    sort: str = "newest",
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
):
    page_size = 20
    q = q.strip() if q and q.strip() else None
    status_filter = status_filter if status_filter in {"active", "inactive", "draft", "pending", "hidden"} else None
    file_type_filter = file_type_filter if file_type_filter in {"external", "local"} else None
    if category_id != "uncategorized" and _int_or_none(category_id) is None:
        category_id = None
    category_id_int = _int_or_none(category_id)
    uncategorized = category_id == "uncategorized"
    if sort not in {"newest", "popular", "title"}:
        sort = "newest"
    items, total = await crud.get_downloads_paginated(
        session,
        page=page,
        page_size=page_size,
        search=q,
        category_id=category_id_int,
        uncategorized=uncategorized,
        status=status_filter or None,
        file_type_filter=file_type_filter or None,
        sort=sort,
        include_inactive=True,
        pin_featured=False,
    )


    total_pages = max(1, math.ceil(total / page_size))
    categories = await crud.get_categories(session)
    category_names = {str(category.id): category.name for category in categories}
    query_state = {
        key: value
        for key, value in {
            "q": (q or "").strip(),
            "category_id": category_id or "",
            "status_filter": status_filter or "",
            "file_type_filter": file_type_filter or "",
            "sort": sort if sort != "newest" else "",
        }.items()
        if value
    }
    status_labels = {
        "active": translate(request, "active"),
        "inactive": translate(request, "inactive"),
        "draft": translate(request, "draft"),
        "pending": translate(request, "publication_pending"),
    }
    filter_chips = []
    chip_values = [
        ("q", f"{translate(request, 'search')}: {q}" if q else ""),
        (
            "category_id",
            f"{translate(request, 'category')}: "
            f"{translate(request, 'uncategorized_content') if uncategorized else category_names.get(category_id or '', category_id or '')}",
        ),
        ("status_filter", status_labels.get(status_filter or "", "")),
        (
            "file_type_filter",
            translate(request, "local_file") if file_type_filter == "local"
            else translate(request, "external_link") if file_type_filter == "external"
            else "",
        ),
    ]
    for key, label in chip_values:
        if not label or key not in query_state:
            continue
        remaining = {name: value for name, value in query_state.items() if name != key}
        filter_chips.append({
            "label": label,
            "remove_url": "/panel/downloads" + ("?" + urlencode(remaining) if remaining else ""),
        })
    flash_message = request.session.pop("flash_message", None)

    return templates.TemplateResponse(
        request=request, name="admin/content_list.html",
        context={
            "request": request,
            "downloads": items,
            "total": total,
            "page": page,
            "total_pages": total_pages,
            "categories": categories,
            "q": q or "",
            "category_id": "uncategorized" if uncategorized else category_id_int,
            "status_filter": status_filter or "",
            "file_type_filter": file_type_filter or "",
            "sort": sort,
            "filter_chips": filter_chips,
            "active_filter_count": len(filter_chips),
            "admin_user": _admin,
            "flash_message": flash_message,
        },
    )


@router.post("/downloads/bulk", name="admin_download_bulk")
async def download_bulk(
    request: Request,
    action: str = Form(...),
    download_ids: List[RecordId] = Form(...),
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
):
    try:
        count = await crud.bulk_update_downloads(session, download_ids, action)
    except ValueError as exc:
        request.session["flash_message"] = system_message(request, str(exc))
    else:
        request.session["flash_message"] = translate(request, "bulk_completed").format(count=count)
    return _redirect(_same_admin_page(request, "/panel/downloads"))


@router.get("/downloads/trash", name="admin_download_trash")
async def download_trash(
    request: Request,
    page: PageNumber = 1,
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
):
    page = max(1, page)
    items, total = await crud.get_trashed_downloads(session, page)
    from app.trash_retention import protected_trash_ids
    protected_ids = await protected_trash_ids(session, [item.id for item in items])
    total_pages = max(1, math.ceil(total / 20))
    if page > total_pages:
        return _redirect(f"/panel/downloads/trash?page={total_pages}")
    return templates.TemplateResponse(request=request, name="admin/trash.html", context={
        "request": request,
        "items": items,
        "total": total,
        "page": page,
        "total_pages": total_pages,
        "retention_days": (await crud.get_site_settings(session)).trash_retention_days,
        "retention_protected_ids": protected_ids,
        "admin_user": _admin,
        "flash_message": request.session.pop("flash_message", None),
    })


@router.post("/downloads/trash/bulk", name="admin_download_trash_bulk")
async def download_trash_bulk(
    request: Request,
    action: str = Form(...),
    download_ids: List[RecordId] = Form(...),
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
):
    # Serialize review and withdrawal so approval cannot delete an already restored item.
    await session.rollback()
    await session.execute(text("BEGIN IMMEDIATE"))
    await require_admin(request, request.cookies.get(SESSION_COOKIE), session)
    try:
        count = await crud.update_trashed_downloads(session, download_ids, action)
    except ValueError as exc:
        request.session["flash_message"] = system_message(request, str(exc))
    else:
        key = "trash_rejected" if action == "reject" else "trash_restored" if action == "restore" else "trash_purged"
        request.session["flash_message"] = translate(request, key).format(count=count)
    return _redirect("/panel/downloads/trash")


# ---------------------------------------------------------------------------
# Download — Yeni
# ---------------------------------------------------------------------------

@router.get("/downloads/new", name="admin_download_new")
async def download_new_get(
    request: Request,
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
):
    categories = await crud.get_categories(session)
    tags = await crud.get_tags(session)
    all_downloads, _ = await crud.get_downloads_paginated(
        session, page=1, page_size=200, include_inactive=True
    )
    flash_message = request.session.pop("flash_message", None)

    return templates.TemplateResponse(
        request=request, name="admin/file_form.html",
        context={
            "request": request,
            "categories": categories,
            "tags": tags,
            "all_downloads": all_downloads,
            "edit_mode": False,
            "download": None,
            "draft_token": secrets.token_urlsafe(24),
            "image_compression_enabled": (await crud.get_site_settings(session)).image_compression_enabled,
            "admin_user": _admin,
            "flash_message": flash_message,
        },
    )


@router.get("/downloads/{download_id}/preview", name="admin_download_preview")
async def download_preview(
    download_id: RecordId,
    request: Request,
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
):
    """Render a saved draft in the public detail layout, for admins only."""
    download = await crud.get_download_detail_by_id(session, download_id)
    if not download or not download.is_draft:
        raise HTTPException(status_code=404, detail="Taslak bulunamadı.")

    context = await build_download_detail_context(
        request, session, download, is_preview=True
    )
    context["page_title"] = f"{download.title} — {translate(request, 'draft_preview_title')}"
    return templates.TemplateResponse(
        request=request, name="detail.html", context=context
    )


@router.post("/downloads/new", name="admin_download_new_post")
async def download_new_post(
    request: Request,
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
    title: str = Form(...),
    description: Optional[str] = Form(None),
    short_description: Optional[str] = Form(None),
    gallery_images: Optional[str] = Form(None),
    version: Optional[str] = Form(None),
    is_latest_version: bool = Form(False),
    file_type: str = Form(...),
    external_url: Optional[str] = Form(None),
    file_final_path: Optional[str] = Form(None),
    file_size_value: Optional[str] = Form(None),
    file_size_unit: str = Form("MB"),
    icon_type: str = Form("auto"),
    icon_extension: Optional[str] = Form(None),
    icon_image_url: Optional[str] = Form(None),
    icon_image_final_path: Optional[str] = Form(None),
    category_id: Optional[str] = Form(None),
    parent_id: Optional[str] = Form(None),
    os_tags: List[str] = Form(default_factory=list),
    is_active: bool = Form(False),
    is_hidden: bool = Form(False),
    submission_intent: str = Form("save"),
    is_featured: bool = Form(False),
    is_official_source: bool = Form(True),
    tag_ids: List[str] = Form(default_factory=list),
    upload_file: Optional[UploadFile] = File(None),
    icon_image_file: Optional[UploadFile] = File(None),
):
    if submission_intent != "publish":
        return JSONResponse(
            {"ok": False, "message": translate(request, "publish_explicit")},
            status_code=409,
        )

    # ── Dosya yükleme ────────────────────────────────────────────────────
    file_path: Optional[str] = _stored_download_path(file_final_path)
    if file_type == "local" and upload_file and upload_file.filename:
        file_path = await _save_upload(upload_file, session)

    # ── İkon görseli ──────────────────────────────────────────────────────
    # Öncelik: AJAX ile önceden yüklenmiş/indirilmiş yerel dosya yolu.
    icon_img_path: Optional[str] = None
    icon_img_url: Optional[str] = icon_image_url or None
    if icon_image_final_path:
        icon_img_path = icon_image_final_path
        icon_img_url = None
    elif icon_image_file and icon_image_file.filename:
        icon_img_path = await _save_icon_upload(icon_image_file, session)

    # ── Tip dönüşümleri (boş string → None) ─────────────────────────────
    cat_id     = _int_or_none(category_id)
    par_id     = _int_or_none(parent_id)
    size_bytes = _parse_file_size_to_bytes(file_size_value, file_size_unit)
    tag_id_list = [int(t) for t in tag_ids if t and str(t).isdigit()]

    try:
        data = DownloadCreate(
            gallery_paths=_gallery_form_paths(gallery_images) or [],
            title=title,
            description=description or None,
            short_description=short_description or None,
            version=None if is_latest_version and file_type == "external" else version or None,
            is_latest_version=is_latest_version and file_type == "external",
            file_type=FileType(file_type),
            file_path=file_path,
            external_url=external_url or None,
            file_size_bytes=size_bytes,
            icon_type=IconType(icon_type),
            icon_extension=(icon_extension or "").strip().lstrip(".").lower() or None,
            icon_image_path=icon_img_path,
            icon_image_url=icon_img_url,
            os_compatibility=os_tags,
            category_id=cat_id,
            parent_id=par_id,
            is_active=is_active,
            is_hidden=is_hidden,
            is_featured=is_featured,
            is_official_source=is_official_source,
            tag_ids=tag_id_list,
        )
        download = await crud.create_download(session, data)
    except HTTPException:
        await session.rollback()
        raise
    except Exception as exc:
        await session.rollback()
        logger.error("Download creation failed: error_type=%s", type(exc).__name__)
        error_message = _download_form_error(request, exc)
        categories = await crud.get_categories(session)
        tags = await crud.get_tags(session)
        all_dl, _ = await crud.get_downloads_paginated(
            session, page=1, page_size=200, include_inactive=True
        )
        if _wants_json(request):
            return JSONResponse({"ok": False, "message": error_message}, status_code=422)
        return templates.TemplateResponse(
            request=request, name="admin/file_form.html",
            context={
                "request": request,
                "categories": categories,
                "tags": tags,
                "all_downloads": all_dl,
                "edit_mode": False,
                "download": None,
                "draft_token": secrets.token_urlsafe(24),
                "file_size_val": file_size_value,
                "file_size_unit": file_size_unit,
                "error": error_message,
                "admin_user": _admin,
            },
            status_code=422,
        )

    request.session["flash_message"] = (translate(request, "publication_submitted") if download.publication_pending
                                        else translate(request, "application_added").format(title=download.title))
    if _wants_json(request):
        return JSONResponse(
            {"ok": True, "message": request.session["flash_message"], "redirect_url": "/panel/downloads"}
        )
    return _redirect("/panel/downloads")


@router.post("/downloads/drafts/autosave", name="admin_download_draft_autosave")
async def download_draft_autosave(
    request: Request,
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
):
    form = await request.form()
    draft_token = str(form.get("draft_token") or "").strip()
    if not draft_token or len(draft_token) > 64:
        return JSONResponse(
            {"ok": False, "message": translate(request, "draft_key_invalid")}, status_code=422
        )

    draft = None
    draft_id = _int_or_none(str(form.get("draft_id") or ""))
    if draft_id is not None:
        draft = await crud.get_download_by_id(session, draft_id)
        if draft is not None and not draft.is_draft:
            return JSONResponse(
                {"ok": False, "message": translate(request, "draft_published")},
                status_code=409,
            )
    if draft is None:
        draft = await crud.get_download_draft_by_token(session, draft_token)

    session.info["audit_suppressed"] = True
    try:
        if draft is None:
            draft = await crud.create_download_draft(
                session, draft_token, str(form.get("title") or "")
            )

        file_type = FileType(str(form.get("file_type") or "external"))
        is_latest = (
            _form_bool(form.get("is_latest_version"))
            and file_type == FileType.external
        )
        icon_path = str(form.get("icon_image_final_path") or "").strip() or None
        icon_url = str(form.get("icon_image_url") or "").strip() or None
        if _form_bool(form.get("icon_image_cleared")):
            icon_path = None
            icon_url = None
        elif icon_path:
            icon_url = None

        data = DownloadUpdate(
            title=str(form.get("title") or "").strip()[:200],
            gallery_paths=_gallery_form_paths(form.get('gallery_images')),
            description=str(form.get("description") or "").strip() or None,
            short_description=str(form.get("short_description") or "").strip() or None,
            version=None if is_latest else str(form.get("version") or "").strip() or None,
            is_latest_version=is_latest,
            file_type=file_type,
            file_path=_stored_download_path(form.get("file_final_path")) or draft.file_path,
            external_url=str(form.get("external_url") or "").strip() or None,
            file_size_bytes=_parse_file_size_to_bytes(
                str(form.get("file_size_value") or ""),
                str(form.get("file_size_unit") or "MB"),
            ),
            icon_type=IconType(str(form.get("icon_type") or "auto")),
            icon_extension=str(form.get("icon_extension") or "").strip().lstrip(".").lower() or None,
            icon_image_path=icon_path,
            icon_image_url=icon_url,
            os_compatibility=[str(value) for value in form.getlist("os_tags")],
            category_id=_int_or_none(str(form.get("category_id") or "")),
            parent_id=_int_or_none(str(form.get("parent_id") or "")),
            is_active=False,
            is_draft=True,
            is_featured=_form_bool(form.get("is_featured")),
            is_hidden=_form_bool(form.get("is_hidden")),
            is_official_source=_form_bool(form.get("is_official_source"), True),
            tag_ids=[
                int(value)
                for value in form.getlist("tag_ids")
                if str(value).isdigit()
            ],
        )
        draft = await crud.update_download(session, draft, data)
    except HTTPException:
        await session.rollback()
        raise
    except (TypeError, ValueError) as exc:
        await session.rollback()
        return JSONResponse({"ok": False, "message": _download_form_error(request, exc)}, status_code=422)
    except Exception:
        await session.rollback()
        logger.exception("Draft autosave failed")
        return JSONResponse(
            {"ok": False, "message": translate(request, "draft_failed")}, status_code=500
        )
    finally:
        session.info.pop("audit_suppressed", None)

    return JSONResponse(
        {
            "ok": True,
            "draft_id": draft.id,
            "edit_url": f"/panel/downloads/{draft.id}/edit",
            "saved_at": datetime.now().astimezone().isoformat(),
        }
    )


# ---------------------------------------------------------------------------
# Download — Düzenle
# ---------------------------------------------------------------------------

@router.get("/downloads/{download_id}/edit", name="admin_download_edit")
async def download_edit_get(
    download_id: RecordId,
    request: Request,
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
):
    download = await crud.get_download_by_id(session, download_id)
    if not download:
        raise HTTPException(status_code=404, detail="Download bulunamadı.")
    categories = await crud.get_categories(session)
    tags = await crud.get_tags(session)
    all_downloads, _ = await crud.get_downloads_paginated(
        session, page=1, page_size=200, include_inactive=True
    )
    flash_message = request.session.pop("flash_message", None)
    file_size_val, file_size_unit = _deconstruct_file_size(download.file_size_bytes)

    return templates.TemplateResponse(
        request=request, name="admin/file_form.html",
        context={
            "request": request,
            "categories": categories,
            "tags": tags,
            "all_downloads": all_downloads,
            "edit_mode": True,
            "download": download,
            "draft_token": download.draft_token or secrets.token_urlsafe(24),
            "image_compression_enabled": (await crud.get_site_settings(session)).image_compression_enabled,
            "admin_user": _admin,
            "flash_message": flash_message,
            "file_size_val": file_size_val,
            "file_size_unit": file_size_unit,
        },
    )


@router.post("/downloads/{download_id}/edit", name="admin_download_edit_post")
async def download_edit_post(
    download_id: RecordId,
    request: Request,
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    short_description: Optional[str] = Form(None),
    gallery_images: Optional[str] = Form(None),
    version: Optional[str] = Form(None),
    is_latest_version: bool = Form(False),
    file_type: Optional[str] = Form(None),
    external_url: Optional[str] = Form(None),
    file_final_path: Optional[str] = Form(None),
    file_size_value: Optional[str] = Form(None),
    file_size_unit: str = Form("MB"),
    icon_type: Optional[str] = Form(None),
    icon_extension: Optional[str] = Form(None),
    icon_image_url: Optional[str] = Form(None),
    icon_image_final_path: Optional[str] = Form(None),
    icon_image_cleared: Optional[str] = Form(None),
    category_id: Optional[str] = Form(None),
    parent_id: Optional[str] = Form(None),
    os_tags: List[str] = Form(default_factory=list),
    is_active: bool = Form(False),
    is_hidden: bool = Form(False),
    submission_intent: str = Form("save"),
    is_featured: bool = Form(False),
    is_official_source: bool = Form(True),
    tag_ids: List[str] = Form(default_factory=list),
    upload_file: Optional[UploadFile] = File(None),
    icon_image_file: Optional[UploadFile] = File(None),
):
    download = await crud.get_download_by_id(session, download_id)
    if not download:
        raise HTTPException(status_code=404, detail="Download bulunamadı.")
    was_draft = download.is_draft

    # ── Dosya yükleme ────────────────────────────────────────────────────
    file_path: Optional[str] = _stored_download_path(file_final_path) or download.file_path
    if upload_file and upload_file.filename:
        file_path = await _save_upload(upload_file, session)

    # ── İkon görseli ──────────────────────────────────────────────────────
    # Öncelik: (1) kullanıcı görseli sildi  (2) AJAX ile önceden yüklenmiş/
    # indirilmiş yerel dosya yolu  (3) form ile birlikte gelen dosya.
    icon_img_path: Optional[str] = download.icon_image_path
    icon_img_url: Optional[str] = icon_image_url or None
    if icon_image_cleared == "1":
        icon_img_path = None
        icon_img_url = None
    elif icon_image_final_path:
        icon_img_path = icon_image_final_path
        icon_img_url = None
    elif icon_image_file and icon_image_file.filename:
        icon_img_path = await _save_icon_upload(icon_image_file, session)

    # ── Tip dönüşümleri (boş string → None) ─────────────────────────────
    cat_id      = _int_or_none(category_id)
    par_id      = _int_or_none(parent_id)
    size_bytes  = _parse_file_size_to_bytes(file_size_value, file_size_unit)
    tag_id_list = [int(t) for t in tag_ids if t and str(t).isdigit()]

    try:
        publishing_draft = was_draft and submission_intent == "publish"
        if publishing_draft:
            effective_type = FileType(file_type) if file_type else download.file_type
            if not (title or "").strip():
                raise ValueError("Başlık zorunludur.")
            if effective_type == FileType.external and not (external_url or "").strip():
                raise ValueError("Dış bağlantı zorunludur.")
            if effective_type == FileType.local and not (file_path or download.file_path):
                raise ValueError("Lokal dosya zorunludur.")
        data = DownloadUpdate(
            title=title,
            gallery_paths=_gallery_form_paths(gallery_images),
            description=description or None,
            short_description=short_description or None,
            version=None if is_latest_version and file_type == "external" else version or None,
            is_latest_version=is_latest_version and file_type == "external",
            file_type=FileType(file_type) if file_type else download.file_type,
            file_path=file_path or download.file_path,
            external_url=external_url or None,
            file_size_bytes=size_bytes,
            icon_type=IconType(icon_type) if icon_type else download.icon_type,
            icon_extension=(icon_extension or "").strip().lstrip(".").lower() or None,
            icon_image_path=icon_img_path,
            icon_image_url=icon_img_url,
            os_compatibility=os_tags,
            category_id=cat_id,
            parent_id=par_id,
            is_active=False if was_draft and not publishing_draft else is_active,
            is_draft=was_draft and not publishing_draft,
            is_hidden=is_hidden,
            is_featured=is_featured,
            is_official_source=is_official_source,
            tag_ids=tag_id_list,
        )
        await crud.update_download(session, download, data)
    except HTTPException:
        await session.rollback()
        raise
    except Exception as exc:
        await session.rollback()
        logger.error("Download update failed: error_type=%s", type(exc).__name__)
        download = await crud.get_download_by_id(session, download_id)
        if download is None:
            raise HTTPException(404)
        error_message = _download_form_error(request, exc)
        categories = await crud.get_categories(session)
        tags = await crud.get_tags(session)
        all_dl, _ = await crud.get_downloads_paginated(
            session, page=1, page_size=200, include_inactive=True
        )
        if _wants_json(request):
            return JSONResponse({"ok": False, "message": error_message}, status_code=422)
        return templates.TemplateResponse(
            request=request, name="admin/file_form.html",
            context={
                "request": request,
                "categories": categories,
                "tags": tags,
                "all_downloads": all_dl,
                "edit_mode": True,
                "download": download,
                "draft_token": download.draft_token or secrets.token_urlsafe(24),
                "file_size_val": file_size_value,
                "file_size_unit": file_size_unit,
                "error": error_message,
                "admin_user": _admin,
            },
            status_code=422,
        )

    if was_draft and not publishing_draft:
        request.session["flash_message"] = translate(request, "draft_saved")
        if _wants_json(request):
            return JSONResponse(
                {
                    "ok": True,
                    "message": translate(request, "draft_saved"),
                    "redirect_url": f"/panel/downloads/{download_id}/edit",
                }
            )
        return _redirect(f"/panel/downloads/{download_id}/edit")

    if publishing_draft:
        request.session["flash_message"] = (translate(request, "publication_submitted") if download.publication_pending
                                            else translate(request, "application_added").format(title=download.title))
        if _wants_json(request):
            return JSONResponse(
                {"ok": True, "message": request.session["flash_message"], "redirect_url": "/panel/downloads"}
            )
        return _redirect("/panel/downloads")
    request.session["flash_message"] = translate(request, "publication_submitted" if download.publication_pending else "changes_saved")
    if _wants_json(request):
        return JSONResponse(
            {
                "ok": True,
                "message": translate(request, "saved_response"),
                "redirect_url": f"/panel/downloads/{download_id}/edit",
            }
        )
    return _redirect(f"/panel/downloads/{download_id}/edit")


# ---------------------------------------------------------------------------
# Download — Sil
# ---------------------------------------------------------------------------

@router.post("/downloads/{download_id}/delete", name="admin_download_delete")
async def download_delete(
    download_id: RecordId,
    request: Request,
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
):
    download = await crud.get_download_by_id(session, download_id)
    if not download:
        raise HTTPException(status_code=404, detail="Download bulunamadı.")

    await crud.delete_download(session, download)
    request.session["flash_message"] = translate(request, "content_deleted").format(title=download.title)
    return _redirect(_same_admin_page(request, "/panel/downloads"))


# ---------------------------------------------------------------------------
# Download — Sürüm Geçmişi (otomatik; yalnızca düzeltme/silme, ekleme yok)
# ---------------------------------------------------------------------------

@router.post(
    "/downloads/{download_id}/version-history/{entry_id}/edit",
    name="admin_version_history_edit",
)
async def version_history_edit(
    download_id: RecordId,
    entry_id: RecordId,
    request: Request,
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
    version: str = Form(...),
):
    if await crud.get_download_by_id(session, download_id) is None:
        raise HTTPException(404)
    entry = await crud.get_version_history_entry(session, entry_id)
    if not entry or entry.download_id != download_id:
        raise HTTPException(status_code=404, detail="Sürüm geçmişi kaydı bulunamadı.")
    version = version.strip()
    if not version:
        raise HTTPException(status_code=422, detail="Sürüm boş olamaz.")
    await crud.update_version_history_entry(session, entry, version)
    request.session["flash_message"] = translate(request, "version_record_updated")
    return _redirect(f"/panel/downloads/{download_id}/edit")


@router.post(
    "/downloads/{download_id}/version-history/{entry_id}/delete",
    name="admin_version_history_delete",
)
async def version_history_delete(
    download_id: RecordId,
    entry_id: RecordId,
    request: Request,
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
):
    if await crud.get_download_by_id(session, download_id) is None:
        raise HTTPException(404)
    entry = await crud.get_version_history_entry(session, entry_id)
    if not entry or entry.download_id != download_id:
        raise HTTPException(status_code=404, detail="Sürüm geçmişi kaydı bulunamadı.")
    await crud.delete_version_history_entry(session, entry)
    request.session["flash_message"] = translate(request, "version_record_deleted")
    return _redirect(f"/panel/downloads/{download_id}/edit")


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------

@router.get("/categories", name="admin_categories")
async def categories_view(
    request: Request,
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
):
    await crud.ensure_required_category(session)
    categories = await crud.get_categories(session)
    counts = await crud.get_category_download_counts(session)
    flash_message = request.session.pop("flash_message", None)
    flash_type = request.session.pop("flash_type", "success")
    return templates.TemplateResponse(
        request=request, name="admin/categories.html",
        context={
            "request": request,
            "categories": categories,
            "category_counts": counts,
            "admin_user": _admin,
            "flash_message": flash_message,
            "flash_type": flash_type,
        },
    )


@router.post("/categories", name="admin_category_create")
async def category_create(
    request: Request,
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
    name: str = Form(...),
    description: Optional[str] = Form(None),
):
    try:
        data = CategoryCreate(name=name.strip(), description=description or None)
        category = await crud.create_category(session, data)
    except IntegrityError:
        await session.rollback()
        request.session["flash_type"] = "error"
        request.session["flash_message"] = translate(request, "category_duplicate")
    except ValueError:
        await session.rollback()
        request.session["flash_type"] = "error"
        request.session["flash_message"] = translate(request, "category_invalid")
    else:
        request.session["flash_type"] = "success"
        request.session["flash_message"] = translate(request, "category_added").format(
            name=category.name
        )
    return _redirect("/panel/categories")


@router.post("/categories/{category_id}/edit", name="admin_category_edit")
async def category_edit(
    category_id: RecordId,
    request: Request,
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
    name: str = Form(...),
    description: Optional[str] = Form(None),
):
    category = await crud.get_category_by_id(session, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Kategori bulunamadı.")
    try:
        data = CategoryUpdate(name=name.strip(), description=description or None)
        await crud.update_category(session, category, data)
    except IntegrityError:
        await session.rollback()
        request.session["flash_type"] = "error"
        request.session["flash_message"] = translate(request, "category_duplicate")
    except ValueError:
        await session.rollback()
        request.session["flash_type"] = "error"
        request.session["flash_message"] = translate(request, "category_invalid")
    else:
        request.session["flash_type"] = "success"
        request.session["flash_message"] = translate(request, "category_updated")
    return _redirect("/panel/categories")


@router.post("/categories/{category_id}/delete", name="admin_category_delete")
async def category_delete(
    category_id: RecordId,
    request: Request,
    target_category_id: Optional[RecordId] = Form(None),
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
):
    category = await crud.get_category_by_id(session, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Kategori bulunamadı.")
    if target_category_id is None:
        target_category_id = (await crud.ensure_required_category(session)).id
    try:
        moved = await crud.transfer_and_delete_categories(session, [category.id], target_category_id)
    except ValueError as exc:
        request.session["flash_type"] = "error"
        request.session["flash_message"] = system_message(request, str(exc))
    else:
        request.session["flash_type"] = "success"
        request.session["flash_message"] = translate(request, "category_deleted_transferred").format(count=moved)
    return _redirect("/panel/categories")


@router.post("/categories/{category_id}/move", name="admin_category_move")
async def category_move(
    category_id: RecordId, request: Request, target_category_id: RecordId = Form(...),
    session: AsyncSession = Depends(get_db), _admin: str = Depends(require_admin),
):
    await session.rollback()
    await session.execute(text("BEGIN IMMEDIATE"))
    await require_admin(request, request.cookies.get(SESSION_COOKIE), session)
    moved = await crud.move_category_contents(session, category_id, target_category_id)
    request.session["flash_type"] = "success"
    request.session["flash_message"] = translate(request, "category_moved").format(count=moved)
    return _redirect("/panel/categories")


@router.post("/categories/bulk-delete", name="admin_category_bulk_delete")
async def category_bulk_delete(
    request: Request,
    target_category_id: RecordId = Form(...),
    category_ids: List[RecordId] = Form(...),
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
):
    try:
        moved = await crud.transfer_and_delete_categories(session, category_ids, target_category_id)
    except ValueError as exc:
        request.session["flash_type"] = "error"
        request.session["flash_message"] = system_message(request, str(exc))
    else:
        request.session["flash_type"] = "success"
        request.session["flash_message"] = translate(request, "categories_deleted_transferred").format(count=moved)
    return _redirect("/panel/categories")


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------

@router.get("/tags", name="admin_tags")
async def tags_view(
    request: Request,
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
):
    tags = await crud.get_tags(session)
    flash_message = request.session.pop("flash_message", None)
    flash_type = request.session.pop("flash_type", "success")
    return templates.TemplateResponse(
        request=request, name="admin/tags.html",
        context={"request": request, "tags": tags, "admin_user": _admin, "flash_message": flash_message, "flash_type": flash_type},
    )


@router.post("/tags", name="admin_tag_create")
async def tag_create(
    request: Request,
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
    name: str = Form(...),
):
    try:
        data = TagCreate(name=name.strip())
        tag = await crud.create_tag(session, data)
    except IntegrityError:
        await session.rollback()
        request.session["flash_type"] = "error"
        request.session["flash_message"] = translate(request, "tag_duplicate")
    except ValueError:
        await session.rollback()
        request.session["flash_type"] = "error"
        request.session["flash_message"] = translate(request, "tag_invalid")
    else:
        request.session["flash_type"] = "success"
        request.session["flash_message"] = translate(request, "tag_added").format(
            name=tag.name
        )
    return _redirect("/panel/tags")


@router.post('/tags/inline', name='admin_tag_inline')
async def tag_create_inline(request: Request, name: str = Form(..., min_length=1, max_length=60),
                            session: AsyncSession = Depends(get_db), _admin: str = Depends(require_admin)):
    """Create/select an owned tag without leaving the application form."""
    from app.routers.users import _lock_actor
    await _lock_actor(request, session, request.state.admin_role)
    try:
        data = TagCreate(name=name.strip().lstrip('#').strip())
    except ValueError:
        raise HTTPException(422, translate(request, 'tag_invalid')) from None
    tag = await session.scalar(select(Tag).where(Tag.name == data.name, Tag.owner_id == request.state.admin_id))
    if tag is None:
        tag = await crud.create_tag(session, data)
    else:
        await session.commit()
    return {'id': tag.id, 'name': tag.name}


@router.post("/tags/{tag_id}/edit", name="admin_tag_edit")
async def tag_edit(
    tag_id: RecordId,
    request: Request,
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
    name: str = Form(...),
):
    from slugify import slugify
    tag = await crud.get_tag_by_id(session, tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="Tag bulunamadı.")
    try:
        clean_name = name.strip()
        TagCreate(name=clean_name)
        tag.name = clean_name
        tag.slug = await crud._unique_slug(session, Tag, slugify(clean_name, allow_unicode=False, separator="-"), exclude_id=tag.id)
        await session.commit()
        await session.refresh(tag)
    except IntegrityError:
        await session.rollback()
        request.session["flash_type"] = "error"
        request.session["flash_message"] = translate(request, "tag_duplicate")
    except ValueError:
        await session.rollback()
        request.session["flash_type"] = "error"
        request.session["flash_message"] = translate(request, "tag_invalid")
    else:
        request.session["flash_type"] = "success"
        request.session["flash_message"] = translate(request, "tag_updated")
    return _redirect("/panel/tags")


@router.post("/tags/{tag_id}/delete", name="admin_tag_delete")
async def tag_delete(
    tag_id: RecordId,
    request: Request,
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
):
    tag = await crud.get_tag_by_id(session, tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="Tag bulunamadı.")
    tag_name = tag.name
    await crud.delete_tag(session, tag)
    request.session["flash_type"] = "success"
    request.session["flash_message"] = translate(request, "tag_deleted").format(
        name=tag_name
    )
    return _redirect("/panel/tags")


@router.post("/tags/bulk-delete", name="admin_tag_bulk_delete")
async def tag_bulk_delete(
    request: Request,
    tag_ids: List[RecordId] = Form(...),
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
):
    try:
        count = await crud.bulk_delete_tags(session, tag_ids)
    except ValueError as exc:
        request.session["flash_type"] = "error"
        request.session["flash_message"] = system_message(request, str(exc))
    else:
        request.session["flash_type"] = "success"
        request.session["flash_message"] = translate(request, "tags_deleted").format(
            count=count
        )
    return _redirect("/panel/tags")


# ---------------------------------------------------------------------------
# Ayarlar — Menü Düzenleme
# ---------------------------------------------------------------------------

class _ReorderPayload(BaseModel):
    ids: List[RecordId]


class _StringOrderPayload(BaseModel):
    order: List[str]


@router.get("/settings", name="admin_settings")
async def settings_root_redirect(_admin: str = Depends(require_admin)):
    return _redirect("/panel/settings/general")


@router.get("/settings/general", name="admin_settings_general")
async def settings_general_view(
    request: Request,
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
):
    site_settings = await crud.get_site_settings(session)
    flash_message = request.session.pop("flash_message", None)
    flash_type = request.session.pop("flash_type", "success")
    return templates.TemplateResponse(
        request=request, name="admin/settings_general.html",
        context={
            "request": request,
            "site_settings": site_settings,
            "icon_colors": SITE_ICON_COLORS,
            "timezone_choices": TIMEZONE_CHOICES,
            "admin_user": _admin,
            "flash_message": flash_message,
            "flash_type": flash_type,
            "page_title": "Ayarlar",
        },
    )


@router.get("/settings/account", name="admin_settings_account_view")
async def settings_account_view(
    request: Request,
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
):
    site_settings = await crud.get_site_settings(session)
    flash_message = request.session.pop("flash_message", None)
    current_user = await session.get(User, request.state.admin_id)
    active_admins = await session.scalar(select(func.count()).select_from(User).where(
        User.role == "admin", User.is_active.is_(True), User.deleted_at.is_(None)))
    return templates.TemplateResponse(
        request=request, name="admin/settings_account.html",
        context={
            "request": request,
            "site_settings": site_settings,
            "effective_admin_username": current_user.username,
            "current_profile_icon": current_user.profile_icon,
            "can_close_account": current_user.role != "admin" or (active_admins or 0) > 1,
            "icon_colors": SITE_ICON_COLORS,
            "admin_user": _admin,
            "flash_message": flash_message,
            "page_title": "Ayarlar",
        },
    )


@router.get("/settings/menu", name="admin_settings_menu")
async def settings_menu_view(
    request: Request,
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
):
    navbar_items = await crud.get_menu_items(session, location="navbar")
    footer_items = await crud.get_menu_items(session, location="footer")
    categories = await crud.get_categories_ordered(session)
    category_counts = await crud.get_category_download_counts(session)
    tags = await crud.get_tags_ordered(session)
    pages = (await session.scalars(
        select(Page).where(Page.visibility == "public", Page.is_published.is_(True), Page.deleted_at.is_(None))
        .order_by(Page.title)
    )).all()
    site_settings = await crud.get_site_settings(session)
    sidebar_block_order = [
        b for b in site_settings.sidebar_block_order.split(",") if b
    ] or ["search", "categories", "tags"]
    flash_message = request.session.pop("flash_message", None)
    return templates.TemplateResponse(
        request=request, name="admin/settings_menu.html",
        context={
            "request": request,
            "navbar_items": navbar_items,
            "footer_items": footer_items,
            "categories": categories,
            "category_counts": category_counts,
            "tags": tags,
            "pages": pages,
            "sidebar_block_order": sidebar_block_order,
            "site_settings": site_settings,
            "icon_colors": SITE_ICON_COLORS,
            "admin_user": _admin,
            "flash_message": flash_message,
            "page_title": "Ayarlar",
            "navbar_limit": site_settings.navbar_limit,
            "footer_limit": site_settings.footer_limit,
        },
    )


@router.get("/settings/appearance", name="admin_settings_appearance")
async def settings_appearance_view(
    request: Request,
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
):
    site_settings = await crud.get_site_settings(session)
    try:
        hero_components = json.loads(site_settings.hero_components)
    except (TypeError, json.JSONDecodeError):
        hero_components = []
    return templates.TemplateResponse(
        request=request,
        name="admin/settings_appearance.html",
        context={
            "request": request,
            "site_settings": site_settings,
            "hero_components": hero_components,
            "admin_user": _admin,
            "flash_message": request.session.pop("flash_message", None),
            "page_title": "Görünüm",
        },
    )


@router.post("/settings/favicon", name="admin_settings_favicon")
async def settings_favicon_update(
    request: Request, session: AsyncSession = Depends(get_db), _admin: str = Depends(require_admin),
    favicon_file: Optional[UploadFile] = File(None), favicon_source: str = Form("file"),
    favicon_web_url: str = Form("", max_length=2048), clear_favicon: bool = Form(False),
):
    from app.routers.users import _lock_actor

    path: str | None = None
    if not clear_favicon:
        if favicon_source == "file" and favicon_file and favicon_file.filename:
            filename = f"{uuid.uuid4().hex[:12]}.png"
            destination = settings.upload_path / "icons" / filename
            def prepare(staged: Path) -> None:
                validate_raster_image_file(staged)
                make_square_icon(staged, staged, size=128)
            try:
                await save_upload(favicon_file, destination, validator=prepare,
                                  publisher=lambda staged, target: publish_media(session, staged, target))
            except ValueError as exc:
                raise HTTPException(400, translate(request, "favicon_invalid")) from exc
            path = f"/static/uploads/icons/{filename}"
        elif favicon_source == "url" and safe_http_url(favicon_web_url.strip()):
            token = uuid.uuid4().hex
            actor_info = dict(session.info)
            await session.commit()
            _icon_fetch_progress[token] = {"owner_id": request.state.admin_id, "percent": 0, "done": False, "error": None, "path": None}
            try:
                await _fetch_icon_with_timeout(favicon_web_url.strip(), token, _admin, actor_info, square_size=128)
                result = _icon_fetch_progress[token]
                if result.get("error") or not result.get("path"):
                    raise HTTPException(400, system_message(request, result.get("error") or translate(request, "favicon_invalid")))
                path = result["path"]
            finally:
                _icon_fetch_progress.pop(token, None)
        else:
            raise HTTPException(400, translate(request, "favicon_invalid"))
    await _lock_actor(request, session, request.state.admin_role)
    account = await crud.get_site_settings(session)
    old = account.favicon_path
    account.favicon_path = path
    add_event(session, "update", "site_settings", "Site favicon updated", account.id,
              {"favicon_path": [old, path]}, actor=request.state.admin_user)
    await session.commit()
    refresh_site_branding_globals(account)
    request.session["flash_message"] = translate(request, "favicon_saved")
    return _redirect("/panel/settings/appearance")


@router.post("/settings/appearance", name="admin_settings_appearance_update")
async def settings_appearance_update(
    request: Request,
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
    logo_mode: str = Form("icon_text"),
    logo_light_file: Optional[UploadFile] = File(None),
    logo_dark_file: Optional[UploadFile] = File(None),
    clear_logo_light: bool = Form(False),
    clear_logo_dark: bool = Form(False),
    hero_enabled: bool = Form(False),
    hero_background: str = Form("soft"),
    hero_image_file: Optional[UploadFile] = File(None),
    clear_hero_image: bool = Form(False),
    component_type: List[str] = Form([]),
    component_text: List[str] = Form([]),
):
    current = await crud.get_site_settings(session)
    logo_light = None if clear_logo_light else current.logo_light_path
    logo_dark = None if clear_logo_dark else current.logo_dark_path
    hero_image = None if clear_hero_image else current.hero_image_path
    if logo_light_file and logo_light_file.filename:
        logo_light = await _save_icon_upload(logo_light_file, session)
    if logo_dark_file and logo_dark_file.filename:
        logo_dark = await _save_icon_upload(logo_dark_file, session)
    if hero_image_file and hero_image_file.filename:
        hero_image = await _save_icon_upload(hero_image_file, session)

    allowed = {"eyebrow", "title", "description", "search", "stats"}
    components = []
    seen_singletons = set()
    for index, kind in enumerate(component_type):
        if kind not in allowed or kind in seen_singletons:
            continue
        seen_singletons.add(kind)
        text = component_text[index] if index < len(component_text) else ""
        components.append({"type": kind, "text": text.strip()[:300]})
    if not components:
        fallback_language = current.content_language if current.content_language in HERO_TEXT else "en"
        components = [{"type": "title", "text": HERO_TEXT[fallback_language][1]}]
    payload = AppearanceSettingsUpdate(
        logo_mode=logo_mode if logo_mode in {"icon_text", "image_text", "image"} else "icon_text",
        hero_enabled=hero_enabled,
        hero_background=hero_background if hero_background in {"soft", "mesh", "lines", "image"} else "soft",
        hero_components=json.dumps(components, ensure_ascii=False),
        navbar_limit=current.navbar_limit,
        footer_limit=current.footer_limit,
        sidebar_category_limit=current.sidebar_category_limit,
        sidebar_tag_limit=current.sidebar_tag_limit,
    )
    if payload.logo_mode in {"image", "image_text"} and not logo_light:
        request.session["flash_message"] = translate(request, "appearance_logo_required")
        return _redirect("/panel/settings/appearance")
    updated = await crud.update_appearance_settings(
        session,
        **payload.model_dump(),
        logo_light_path=logo_light,
        logo_dark_path=logo_dark,
        hero_image_path=hero_image,
    )
    refresh_site_branding_globals(updated)
    request.session["flash_message"] = translate(request, "appearance_updated")
    return _redirect("/panel/settings/appearance")


@router.post("/settings/menu-limits", name="admin_settings_menu_limits")
async def settings_menu_limits_update(
    request: Request,
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
    navbar_limit: int = Form(...),
    footer_limit: int = Form(...),
    sidebar_category_limit: int = Form(...),
    sidebar_tag_limit: int = Form(...),
):
    await crud.update_menu_limits(
        session, navbar_limit, footer_limit, sidebar_category_limit, sidebar_tag_limit
    )
    request.session["flash_message"] = translate(request, "menu_limits_updated")
    return _redirect("/panel/settings/menu")


@router.post("/settings/branding", name="admin_settings_branding")
async def settings_branding_update(
    request: Request,
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
    site_name: str = Form(...),
    site_icon: str = Form(...),
    theme_color: Optional[str] = Form(None),
    site_icon_color: Optional[str] = Form(None),
):
    current = await crud.get_site_settings(session)
    selected_theme = theme_color if theme_color in {"blue", "green", "red", "yellow", "cream", "amoled"} else current.theme_color
    data = SiteSettingsUpdate(
        site_name=site_name, site_icon=site_icon,
        site_icon_color=site_icon_color or (selected_theme if theme_color else current.site_icon_color), theme_color=selected_theme,
    )
    updated = await crud.update_site_settings(session, data)
    refresh_site_branding_globals(updated)
    request.session["flash_message"] = translate(request, "branding_updated")
    return _redirect("/panel/settings/general")


@router.post("/settings/theme", name="admin_settings_theme")
async def settings_theme_update(
    request: Request,
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
    theme_color: str = Form(...),
):
    if theme_color not in {"blue", "green", "red", "yellow", "cream", "amoled"}:
        raise HTTPException(status_code=422, detail=translate(request, "unsupported_theme"))
    current = await crud.get_site_settings(session)
    updated = await crud.update_site_settings(session, SiteSettingsUpdate(
        site_name=current.site_name,
        site_icon=current.site_icon,
        site_icon_color=theme_color,
        theme_color=theme_color,
    ))
    refresh_site_branding_globals(updated)
    request.session["flash_message"] = translate(request, "branding_updated")
    return _redirect("/panel/settings/appearance")


@router.post("/settings/seo", name="admin_settings_seo")
async def settings_seo_update(
    request: Request,
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
    seo_home_title: str = Form(""),
    seo_meta_description: str = Form(""),
):
    try:
        data = SeoSettingsUpdate(
            seo_home_title=seo_home_title,
            seo_meta_description=seo_meta_description,
        )
    except ValueError:
        request.session["flash_type"] = "error"
        request.session["flash_message"] = translate(request, "seo_settings_invalid")
    else:
        await crud.update_seo_settings(session, data)
        request.session["flash_type"] = "success"
        request.session["flash_message"] = translate(request, "seo_settings_updated")
    return _redirect("/panel/site-health#seo-settings")


@router.post("/settings/language", name="admin_settings_language")
async def settings_language_update(
    request: Request,
    language: str = Form(...),
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
):
    try:
        updated = await crud.update_site_language(session, language)
    except ValueError:
        request.session["flash_message"] = translate(request, "unsupported_language")
    else:
        refresh_site_branding_globals(updated)
        request.session["flash_message"] = translate(request, "language_updated")
    return _redirect("/panel/settings/general")


@router.post("/settings/timezone")
async def settings_timezone_update(
    request: Request, site_timezone: str = Form(...),
    session: AsyncSession = Depends(get_db), _admin: str = Depends(require_admin),
) -> RedirectResponse:
    try:
        zone = validate_timezone(site_timezone)
    except ValueError:
        request.session["flash_message"] = translate(request, "timezone_invalid")
        request.session["flash_type"] = "error"
    else:
        account = await crud.get_site_settings(session)
        account.site_timezone = zone
        await session.commit()
        refresh_site_branding_globals(account)
        request.session["flash_message"] = translate(request, "timezone_saved")
        request.session["flash_type"] = "success"
    return _redirect("/panel/settings/general")


@router.post("/settings/audit-log-limit", name="admin_settings_audit_log_limit")
async def settings_audit_log_limit_update(
    request: Request,
    max_records: int = Form(...),
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
):
    try:
        await crud.update_audit_log_max_records(session, max_records)
    except ValueError as exc:
        request.session["flash_message"] = system_message(request, str(exc))
    else:
        request.session["flash_message"] = translate(request, "audit_limit_updated")
    return _redirect("/panel/audit")


@router.post("/settings/account", name="admin_settings_account")
async def settings_account_update(
    request: Request,
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
    current_password: str = Form(...),
    new_username: Optional[str] = Form(None),
    new_password: Optional[str] = Form(None),
    new_password_confirm: Optional[str] = Form(None),
):
    # require_admin aynı oturumda okuma yaptı; kota kendi kısa işlemini kullanır.
    await session.rollback()
    attempt_id = await reserve_login_attempt(session, "account:" + get_request_ip(request))
    current_user = await session.get(User, request.state.admin_id)
    effective_hash = current_user.password_hash

    if not await verify_password_async(current_password, effective_hash):
        request.session["flash_message"] = translate(request, "wrong_current_password")
        return _redirect("/panel/settings/account")

    await clear_successful_attempt(session, attempt_id)

    new_username = (new_username or "").strip()
    new_password = new_password or ""
    new_password_confirm = new_password_confirm or ""

    if new_username and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{2,49}", new_username):
        request.session["flash_message"] = translate(request, "user_invalid")
        return _redirect("/panel/settings/account")

    if new_password and new_password != new_password_confirm:
        request.session["flash_message"] = translate(request, "passwords_mismatch")
        return _redirect("/panel/settings/account")

    if new_password and (len(new_password) < 12 or len(new_password.encode()) > 1024):
        request.session["flash_message"] = translate(request, "password_policy_failed")
        return _redirect("/panel/settings/account")

    password_hash = await hash_password_async(new_password) if new_password else None
    if new_username and new_username != current_user.username:
        existing = await session.scalar(select(User).where(User.username == new_username))
        if existing:
            request.session["flash_message"] = translate(request, "username_taken")
            return _redirect("/panel/settings/account")
        current_user.username = new_username
    if password_hash:
        current_user.password_hash = password_hash
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        request.session["flash_message"] = translate(request, "username_taken")
        return _redirect("/panel/settings/account")

    request.session["flash_message"] = translate(request, "account_updated" if new_username or new_password else "no_changes")
    return _redirect("/panel/settings/account")


@router.post("/settings/session-duration", name="admin_settings_session_duration")
async def settings_session_duration_update(
    request: Request,
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
    session_max_age_minutes: int = Form(...),
):
    minutes = max(5, min(int(session_max_age_minutes), 60 * 24 * 30))  # 5 dk – 30 gün arası
    await crud.update_session_max_age(session, minutes)
    request.session["flash_message"] = translate(request, "session_updated")
    return _redirect("/panel/settings/account")


@router.post("/settings/avatar", name="admin_settings_avatar")
async def settings_avatar_update(
    request: Request,
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
    admin_icon: str = Form(...),
    admin_icon_color: str | None = Form(None),
):
    # Old form submissions must no longer mutate shared branding or icon colors.
    from app.routers.account import update_profile_icon
    return await update_profile_icon(request, admin_icon, session)


@router.post("/settings/categories/reorder", name="admin_categories_reorder")
async def categories_reorder(
    payload: _ReorderPayload,
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
):
    await crud.reorder_categories(session, payload.ids)
    return {"ok": True}


@router.post("/settings/tags/reorder", name="admin_tags_reorder")
async def tags_reorder(
    payload: _ReorderPayload,
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
):
    await crud.reorder_tags(session, payload.ids)
    return {"ok": True}


@router.post("/settings/sidebar/reorder", name="admin_sidebar_reorder")
async def sidebar_reorder(
    payload: _StringOrderPayload,
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
):
    await crud.update_sidebar_block_order(session, payload.order)
    return {"ok": True}


async def _ensure_public_page_menu_target(request: Request, session: AsyncSession, url: str) -> None:
    path = unquote(urlsplit(url).path)
    if not path.startswith("/page/"):
        return
    page = await session.scalar(select(Page).where(Page.slug == path[6:]))
    if page and (page.visibility != "public" or not page.is_published or page.deleted_at is not None):
        raise HTTPException(status_code=422, detail=translate(request, "page_menu_unavailable"))


@router.post("/settings/menu", name="admin_menu_item_create")
async def menu_item_create(
    request: Request,
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
    label: str = Form(...),
    label_en: Optional[str] = Form(None),
    url: str = Form(...),
    icon: Optional[str] = Form(None),
    is_active: bool = Form(False),
    open_in_new_tab: bool = Form(False),
    location: str = Form("navbar"),
):
    try:
        url = normalize_navigation_url(url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await _ensure_public_page_menu_target(request, session, url)
    site_settings = await crud.get_site_settings(session)
    limit = site_settings.navbar_limit if location == "navbar" else site_settings.footer_limit
    if len(await crud.get_menu_items(session, location=location)) >= limit:
        request.session["flash_message"] = translate(request, "menu_limit_reached").format(count=limit)
        return _redirect("/panel/settings/menu")
    data = MenuItemCreate(
        label=label, label_en=label_en or None, url=url, icon=icon or None,
        is_active=is_active, open_in_new_tab=open_in_new_tab,
        location=location,
    )
    await crud.create_menu_item(session, data)
    request.session["flash_message"] = translate(request, "menu_item_added").format(label=label)
    return _redirect("/panel/settings/menu")


@router.post("/settings/menu/from-source", name="admin_menu_from_source")
async def menu_item_from_source(
    request: Request,
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
    source_type: str = Form(...),
    source_id: RecordId = Form(...),
    location: str = Form("navbar"),
):
    if location not in {"navbar", "footer"}:
        raise HTTPException(status_code=422, detail="Geçersiz menü konumu.")
    site_settings = await crud.get_site_settings(session)
    limit = site_settings.navbar_limit if location == "navbar" else site_settings.footer_limit
    items = await crud.get_menu_items(session, location=location)
    if len(items) >= limit:
        request.session["flash_message"] = translate(request, "menu_limit_reached").format(count=limit)
        return _redirect("/panel/settings/menu")
    if source_type == "category":
        source = await crud.get_category_by_id(session, source_id)
        label, url, icon = (source.name, f"/category/{source.slug}", "folder") if source else (None, None, None)
    elif source_type == "tag":
        source = await crud.get_tag_by_id(session, source_id)
        label, url, icon = (f"#{source.name}", f"/tag/{source.slug}", "tag") if source else (None, None, None)
    elif source_type == "page":
        source = await session.get(Page, source_id)
        if source and source.visibility == "public" and source.is_published and source.deleted_at is None:
            label, url, icon = source.title, f"/page/{source.slug}", "file-text"
        else:
            source = None
            label = url = icon = None
    else:
        source = None
        label = url = icon = None
    if not source:
        raise HTTPException(status_code=404, detail="Kaynak bulunamadı.")
    if any(item.url == url for item in items):
        request.session["flash_message"] = translate(request, "menu_source_duplicate")
        return _redirect("/panel/settings/menu")
    await crud.create_menu_item(session, MenuItemCreate(label=label, url=url, icon=icon, location=location))
    request.session["flash_message"] = translate(request, "menu_source_added").format(label=label)
    return _redirect("/panel/settings/menu")


@router.post("/settings/menu/{item_id}/edit", name="admin_menu_item_edit")
async def menu_item_edit(
    item_id: RecordId,
    request: Request,
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
    label: str = Form(...),
    label_en: Optional[str] = Form(None),
    url: str = Form(...),
    icon: Optional[str] = Form(None),
    is_active: bool = Form(False),
    open_in_new_tab: bool = Form(False),
):
    item = await crud.get_menu_item_by_id(session, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Menü öğesi bulunamadı.")
    try:
        url = normalize_navigation_url(url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await _ensure_public_page_menu_target(request, session, url)
    data = MenuItemUpdate(
        label=label, label_en=label_en or None, url=url, icon=icon or None,
        is_active=is_active, open_in_new_tab=open_in_new_tab,
    )
    await crud.update_menu_item(session, item, data)
    request.session["flash_message"] = translate(request, "menu_item_updated")
    return _redirect("/panel/settings/menu")


@router.post("/settings/menu/{item_id}/delete", name="admin_menu_item_delete")
async def menu_item_delete(
    item_id: RecordId,
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
):
    item = await crud.get_menu_item_by_id(session, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Menü öğesi bulunamadı.")
    await crud.delete_menu_item(session, item)
    return _redirect("/panel/settings/menu")


@router.post("/settings/menu/reorder", name="admin_menu_reorder")
async def menu_reorder(
    payload: _ReorderPayload,
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
):
    await crud.reorder_menu_items(session, payload.ids)
    return {"ok": True}

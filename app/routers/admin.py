"""
Admin router — şifre korumalı yönetim paneli.

Rotalar:
  GET  /admin/login                  → Giriş formu
  POST /admin/login                  → Kimlik doğrulama
  GET  /admin/logout                 → Çıkış
  GET  /admin                        → Dashboard (download listesi)
  GET  /admin/downloads/new          → Yeni dosya formu
  POST /admin/downloads/new          → Dosya oluştur
  GET  /admin/downloads/{id}/edit    → Düzenle formu
  POST /admin/downloads/{id}/edit    → Dosya güncelle
  POST /admin/downloads/{id}/delete  → Dosya sil
  GET  /admin/categories             → Kategori listesi
  POST /admin/categories             → Kategori oluştur
  POST /admin/categories/{id}/edit   → Kategori güncelle
  POST /admin/categories/{id}/delete → Kategori sil
  GET  /admin/tags                   → Tag listesi
  POST /admin/tags                   → Tag oluştur
  POST /admin/tags/{id}/edit         → Tag güncelle
  POST /admin/tags/{id}/delete       → Tag sil
  GET  /admin/media                  → Medya arşivi (resim + dosya)
  GET  /admin/settings/menu           → Menü düzenleme
  POST /admin/settings/menu           → Menü öğesi oluştur
  POST /admin/settings/menu/{id}/edit → Menü öğesi güncelle
  POST /admin/settings/menu/{id}/delete → Menü öğesi sil
  POST /admin/settings/menu/reorder   → Menü sırasını güncelle (AJAX)
"""

from __future__ import annotations

import asyncio
import logging
import mimetypes
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote

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
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.config import settings
from app.imaging import compress_image_file, make_square_icon
from app.dependencies import (
    create_admin_session_token,
    get_db,
    require_admin,
    verify_admin_password,
    SESSION_COOKIE,
)
from app.models import FileType, IconType
from app.schemas import (
    CategoryCreate,
    CategoryUpdate,
    DownloadCreate,
    DownloadUpdate,
    MenuItemCreate,
    MenuItemUpdate,
    TagCreate,
)
from app.templating import templates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

SESSION_MAX_AGE = 60 * 60 * 8  # 8 saat


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------

def _redirect(path: str) -> RedirectResponse:
    return RedirectResponse(url=path, status_code=status.HTTP_302_FOUND)


def _int_or_none(value: Optional[str]) -> Optional[int]:
    """Form'dan gelen boş string veya None → None, geçerli sayı → int."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        return int(s)
    except (ValueError, TypeError):
        return None


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



async def _save_upload(file: UploadFile) -> str:
    """Yüklenen dosyayı UPLOAD_DIR'e kaydeder, yolu döndürür."""
    upload_dir = settings.upload_path
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / file.filename
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    logger.info("Dosya yüklendi: %s", dest)
    return str(dest)


def _unique_icon_filename(original_name: str, fallback_ext: str = ".png") -> str:
    """Çakışmaları önlemek için orijinal ada kısa bir uuid ön eki ekler."""
    safe_name = Path(original_name or "").name
    ext = Path(safe_name).suffix or fallback_ext
    return f"{uuid.uuid4().hex[:12]}{ext}"


async def _save_icon_upload(file: UploadFile, compress: bool = True) -> str:
    """İkon görselini icons/ alt dizinine benzersiz bir adla kaydeder, web yolunu döndürür.

    `compress=False`: kaynağı zaten işlenmiş (ör. kırpma tuvalinden gelen) bir
    görsel ise gereksiz ikinci bir sıkıştırma turu uygulanmaz.
    """
    icons_dir = settings.upload_path / "icons"
    icons_dir.mkdir(parents=True, exist_ok=True)
    filename = _unique_icon_filename(file.filename)
    dest = icons_dir / filename
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    if compress:
        compress_image_file(dest)
    logger.info("İkon yüklendi: %s (sıkıştırma=%s)", dest, compress)
    return f"/static/uploads/icons/{filename}"


def _resolve_icon_path(path: str) -> Path:
    """Bir ikon web yolunu ('/static/uploads/icons/x.png') gerçek disk yoluna çevirir.
    Yalnızca dosya adı kullanılır — dizin gezinmesine (path traversal) izin verilmez."""
    return settings.upload_path / "icons" / Path(path or "").name


async def _replace_icon_upload(file: UploadFile, existing_path: str) -> str:
    """Var olan bir ikon dosyasının İÇERİĞİNİ, TAM OLARAK AYNI yol/link üzerinde
    değiştirir — dosya adı asla değişmez, sıkıştırma uygulanmaz (kaynak zaten
    işlenmiş kabul edilir)."""
    dest = _resolve_icon_path(existing_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    logger.info("İkon yerinde güncellendi (link değişmedi): %s", dest)
    return existing_path


def _delete_icon_file(path: str) -> None:
    """Verilen web yoluna karşılık gelen ikon dosyasını (varsa) diskten siler."""
    filename = Path(path or "").name
    if not filename:
        return
    full = settings.upload_path / "icons" / filename
    if full.exists() and full.is_file():
        try:
            full.unlink()
        except OSError as exc:
            logger.error("İkon silme hatası: %s", exc)


# İlerleme durumu: {token: {"percent": int, "done": bool, "error": str|None, "path": str|None}}
# Tek worker'lı geliştirme sunucusu için bellek-içi; çoklu worker'da paylaşılmaz.
_icon_fetch_progress: dict[str, dict] = {}


async def _fetch_icon_from_url(url: str, token: str) -> None:
    """Dış URL'deki görseli akış halinde indirip icons/ dizinine kaydeder, ilerlemeyi günceller."""
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            async with client.stream("GET", url) as resp:
                resp.raise_for_status()
                content_type = (resp.headers.get("content-type") or "").split(";")[0].strip()
                if not content_type.startswith("image/"):
                    raise ValueError("Bağlantı bir görsel dosyası döndürmüyor.")

                total = int(resp.headers.get("content-length") or 0)
                ext = mimetypes.guess_extension(content_type) or ".jpg"
                icons_dir = settings.upload_path / "icons"
                icons_dir.mkdir(parents=True, exist_ok=True)
                filename = f"{uuid.uuid4().hex[:12]}{ext}"
                dest = icons_dir / filename

                received = 0
                with dest.open("wb") as out:
                    async for chunk in resp.aiter_bytes(chunk_size=65536):
                        out.write(chunk)
                        received += len(chunk)
                        # İndirme %0-90 aralığını kapsar; kalanı sıkıştırma aşamasına ayrılır.
                        percent = min(90, int(received * 90 / total)) if total else 90
                        _icon_fetch_progress[token]["percent"] = percent

        _icon_fetch_progress[token].update({"percent": 92, "phase": "compressing"})
        compress_image_file(dest)
        _icon_fetch_progress[token].update(
            {"percent": 100, "done": True, "phase": "done", "path": f"/static/uploads/icons/{filename}"}
        )
        logger.info("Dış görsel indirildi: %s -> %s", url, dest)
    except Exception as exc:
        logger.error("Dış görsel indirme hatası (%s): %s", url, exc)
        _icon_fetch_progress[token].update({"done": True, "error": str(exc)})


# ---------------------------------------------------------------------------
# Medya Arşivi — sisteme yüklenmiş tüm resim ve dosyaların listesi
# ---------------------------------------------------------------------------

_IMAGE_EXTS = {"png", "jpg", "jpeg", "gif", "webp", "svg", "bmp", "ico"}

_MEDIA_ICON_MAP = {
    "zip": "archive", "rar": "archive", "7z": "archive", "tar": "archive", "gz": "archive",
    "pdf": "file-text", "txt": "file-text", "doc": "file-text", "docx": "file-text",
    "exe": "monitor", "msi": "monitor",
    "apk": "smartphone",
    "dmg": "apple", "pkg": "apple",
    "deb": "terminal", "rpm": "terminal",
    "mp4": "video", "mov": "video", "avi": "video", "mkv": "video",
    "mp3": "music", "wav": "music",
}


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


def _list_media_files(directory: Path, url_prefix: str) -> List[dict]:
    """Bir dizindeki tüm dosyaları (alt dizinler hariç) listeler."""
    items: List[dict] = []
    if directory.exists():
        for p in directory.iterdir():
            if not p.is_file():
                continue
            stat = p.stat()
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
                }
            )
    items.sort(key=lambda x: x["modified"], reverse=True)
    return items


@router.get("/media", name="admin_media")
async def media_view(
    request: Request,
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
):
    upload_root = settings.upload_path
    icons_dir = upload_root / "icons"

    images = _list_media_files(icons_dir, "/static/uploads/icons")
    files = _list_media_files(upload_root, "/static/uploads")

    # Link (path) hiçbir zaman değişmez; kullanıcı yalnızca görünen adı
    # düzenler. Bu, fiziksel dosya adından bağımsız ayrı bir alandır.
    all_paths = [item["url"] for item in images] + [item["url"] for item in files]
    display_names = await crud.get_media_display_names(session, all_paths)
    for item in images + files:
        item["display_name"] = display_names.get(item["url"], item["name"])

    flash_message = request.session.pop("flash_message", None)

    return templates.TemplateResponse(
        "admin/media.html",
        {
            "request": request,
            "images": images,
            "files": files,
            "admin_user": _admin,
            "flash_message": flash_message,
        },
    )


def _unique_upload_filename(original_name: str) -> str:
    """Çakışmaları önlemek için orijinal dosya adının sonuna kısa bir uuid ekler."""
    safe_name = Path(original_name or "dosya").name
    stem = Path(safe_name).stem or "dosya"
    ext = Path(safe_name).suffix
    return f"{stem}-{uuid.uuid4().hex[:8]}{ext}"


@router.post("/media/upload-file", name="admin_media_upload_file")
async def media_upload_file(
    _admin: str = Depends(require_admin),
    file: UploadFile = File(...),
):
    """Dosya Arşivi için genel amaçlı dosya yükleme (herhangi bir tür, orijinal haliyle saklanır)."""
    upload_dir = settings.upload_path
    upload_dir.mkdir(parents=True, exist_ok=True)
    filename = _unique_upload_filename(file.filename)
    dest = upload_dir / filename
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    logger.info("Dosya arşivine yüklendi: %s", dest)
    return {"path": f"/static/uploads/{quote(filename)}", "name": filename}


@router.post("/media/replace-file", name="admin_media_replace_file")
async def media_replace_file(
    _admin: str = Depends(require_admin),
    path: str = Form(...),
    file: UploadFile = File(...),
):
    """Dosya Arşivi'nde mevcut bir dosyanın İÇERİĞİNİ değiştirir; link/ad aynı kalır."""
    filename = Path(path or "").name
    if not filename:
        raise HTTPException(status_code=400, detail="Geçersiz yol.")
    dest = settings.upload_path / filename
    if not dest.exists():
        raise HTTPException(status_code=404, detail="Kaynak dosya bulunamadı.")
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    logger.info("Dosya yerinde güncellendi (link değişmedi): %s", dest)
    return {"path": path}


@router.post("/media/delete-file", name="admin_media_delete_file")
async def media_delete_file(
    _admin: str = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
    path: str = Form(...),
):
    """Dosya Arşivi'ndeki bir dosyayı (uploads kök dizininden) siler."""
    filename = Path(path or "").name
    if filename:
        full = settings.upload_path / filename
        if full.exists() and full.is_file():
            try:
                full.unlink()
            except OSError as exc:
                logger.error("Dosya silme hatası: %s", exc)
    await crud.delete_media_asset(session, path)
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
    await crud.set_media_display_name(session, path, display_name)
    return {"ok": True, "display_name": display_name.strip() or Path(path).name}


# ---------------------------------------------------------------------------
# İkon görseli — AJAX yükleme / dış URL indirme / ilerleme / silme
# ---------------------------------------------------------------------------

@router.post("/upload/icon-image", name="admin_upload_icon_image")
async def upload_icon_image(
    _admin: str = Depends(require_admin),
    file: UploadFile = File(...),
    replace_path: Optional[str] = Form(None),
    skip_compression: bool = Form(False),
):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Sadece görsel dosyaları yüklenebilir.")

    if replace_path:
        # Yerinde güncelleme: link/dosya adı asla değişmez, sıkıştırma uygulanmaz
        # (kaynak — kırpma tuvali çıktısı — zaten işlenmiş kabul edilir).
        path = await _replace_icon_upload(file, replace_path)
    else:
        path = await _save_icon_upload(file, compress=not skip_compression)
    return {"path": path}


@router.post("/upload/icon-image-url", name="admin_upload_icon_image_url")
async def upload_icon_image_url(
    _admin: str = Depends(require_admin),
    url: str = Form(...),
    token: str = Form(...),
):
    _icon_fetch_progress[token] = {
        "percent": 0, "done": False, "error": None, "path": None, "phase": "downloading",
    }
    asyncio.create_task(_fetch_icon_from_url(url, token))
    return {"started": True, "token": token}


@router.get("/upload/progress/{token}", name="admin_upload_progress")
async def upload_progress(token: str, _admin: str = Depends(require_admin)):
    data = _icon_fetch_progress.get(token)
    if not data:
        raise HTTPException(status_code=404, detail="Bilinmeyen işlem.")
    if data.get("done"):
        _icon_fetch_progress.pop(token, None)
    return data


@router.post("/upload/icon-image-delete", name="admin_upload_icon_image_delete")
async def delete_icon_image(
    _admin: str = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
    path: str = Form(...),
):
    _delete_icon_file(path)
    await crud.delete_media_asset(session, path)
    return {"deleted": True}


@router.post("/upload/icon-auto-crop", name="admin_upload_icon_auto_crop")
async def upload_icon_auto_crop(
    _admin: str = Depends(require_admin),
    path: str = Form(...),
    size: int = Form(256),
    in_place: bool = Form(False),
):
    """Mevcut bir ikon görselini otomatik olarak ortadan kare kırpıp yeniden boyutlandırır.

    `in_place=True`: sonucu KAYNAKLA AYNI dosya yoluna yazar (link asla değişmez).
    `in_place=False` (varsayılan): yeni, benzersiz adlı bir dosya oluşturur.
    """
    filename = Path(path or "").name
    src = settings.upload_path / "icons" / filename
    if not filename or not src.exists():
        raise HTTPException(status_code=404, detail="Kaynak görsel bulunamadı.")

    if in_place:
        dest = src
    else:
        dest = settings.upload_path / "icons" / f"{uuid.uuid4().hex[:12]}.png"

    try:
        make_square_icon(src, dest, size=max(32, min(int(size), 1024)))
    except Exception as exc:
        logger.error("Otomatik ikon kırpma hatası (%s): %s", src, exc)
        raise HTTPException(status_code=422, detail="Görsel işlenemedi.")

    return {"path": f"/static/uploads/icons/{dest.name}"}


# ---------------------------------------------------------------------------
# Login / Logout
# ---------------------------------------------------------------------------

@router.get("/login", name="admin_login")
async def login_get(request: Request):
    return templates.TemplateResponse("admin/login.html", {"request": request})


@router.post("/login", name="admin_login_post")
async def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    if username != settings.admin_username or not verify_admin_password(password):
        logger.warning("Başarısız admin giriş denemesi: username=%r", username)
        return templates.TemplateResponse(
            "admin/login.html",
            {"request": request, "error": "Kullanıcı adı veya şifre hatalı."},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    token = create_admin_session_token(username)
    response = _redirect("/admin")
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
    )
    logger.info("Admin girişi başarılı: username=%r", username)
    return response


@router.get("/logout", name="admin_logout")
async def logout():
    response = _redirect("/admin/login")
    response.delete_cookie(SESSION_COOKIE)
    return response


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@router.get("", name="admin_dashboard")
@router.get("/", include_in_schema=False)
async def dashboard(
    request: Request,
    page: int = 1,
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
):
    import math
    items, total = await crud.get_downloads_paginated(
        session, page=page, page_size=20, include_inactive=True
    )
    total_pages = max(1, math.ceil(total / 20))
    categories = await crud.get_categories(session)
    tags = await crud.get_tags(session)
    flash_message = request.session.pop("flash_message", None)

    return templates.TemplateResponse(
        "admin/dashboard.html",
        {
            "request": request,
            "downloads": items,
            "total": total,
            "page": page,
            "total_pages": total_pages,
            "categories": categories,
            "tags": tags,
            "admin_user": _admin,
            "flash_message": flash_message,
        },
    )


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
        "admin/file_form.html",
        {
            "request": request,
            "categories": categories,
            "tags": tags,
            "all_downloads": all_downloads,
            "edit_mode": False,
            "download": None,
            "admin_user": _admin,
            "flash_message": flash_message,
        },
    )


@router.post("/downloads/new", name="admin_download_new_post")
async def download_new_post(
    request: Request,
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
    title: str = Form(...),
    description: Optional[str] = Form(None),
    version: Optional[str] = Form(None),
    file_type: str = Form(...),
    external_url: Optional[str] = Form(None),
    file_size_value: Optional[str] = Form(None),
    file_size_unit: str = Form("MB"),
    icon_type: str = Form("auto"),
    icon_image_url: Optional[str] = Form(None),
    icon_image_final_path: Optional[str] = Form(None),
    category_id: Optional[str] = Form(None),
    parent_id: Optional[str] = Form(None),
    os_tags: List[str] = Form(default_factory=list),
    is_active: bool = Form(False),
    is_featured: bool = Form(False),
    tag_ids: List[str] = Form(default_factory=list),
    upload_file: Optional[UploadFile] = File(None),
    icon_image_file: Optional[UploadFile] = File(None),
):
    # ── Dosya yükleme ────────────────────────────────────────────────────
    file_path: Optional[str] = None
    if file_type == "local" and upload_file and upload_file.filename:
        file_path = await _save_upload(upload_file)

    # ── İkon görseli ──────────────────────────────────────────────────────
    # Öncelik: AJAX ile önceden yüklenmiş/indirilmiş yerel dosya yolu.
    icon_img_path: Optional[str] = None
    icon_img_url: Optional[str] = icon_image_url or None
    if icon_image_final_path:
        icon_img_path = icon_image_final_path
        icon_img_url = None
    elif icon_image_file and icon_image_file.filename:
        icon_img_path = await _save_icon_upload(icon_image_file)

    # ── Tip dönüşümleri (boş string → None) ─────────────────────────────
    cat_id     = _int_or_none(category_id)
    par_id     = _int_or_none(parent_id)
    size_bytes = _parse_file_size_to_bytes(file_size_value, file_size_unit)
    tag_id_list = [int(t) for t in tag_ids if t and str(t).isdigit()]

    try:
        data = DownloadCreate(
            title=title,
            description=description or None,
            version=version or None,
            file_type=FileType(file_type),
            file_path=file_path,
            external_url=external_url or None,
            file_size_bytes=size_bytes,
            icon_type=IconType(icon_type),
            icon_image_path=icon_img_path,
            icon_image_url=icon_img_url,
            os_compatibility=os_tags,
            category_id=cat_id,
            parent_id=par_id,
            is_active=is_active,
            is_featured=is_featured,
            tag_ids=tag_id_list,
        )
        download = await crud.create_download(session, data)
    except Exception as exc:
        await session.rollback()
        logger.error("Download oluşturma hatası: %s", exc)
        categories = await crud.get_categories(session)
        tags = await crud.get_tags(session)
        all_dl, _ = await crud.get_downloads_paginated(
            session, page=1, page_size=200, include_inactive=True
        )
        return templates.TemplateResponse(
            "admin/file_form.html",
            {
                "request": request,
                "categories": categories,
                "tags": tags,
                "all_downloads": all_dl,
                "edit_mode": False,
                "download": None,
                "file_size_val": file_size_value,
                "file_size_unit": file_size_unit,
                "error": str(exc),
                "admin_user": _admin,
            },
            status_code=422,
        )

    request.session["flash_message"] = f"\"{download.title}\" başarıyla eklendi."
    return _redirect("/admin")


# ---------------------------------------------------------------------------
# Download — Düzenle
# ---------------------------------------------------------------------------

@router.get("/downloads/{download_id}/edit", name="admin_download_edit")
async def download_edit_get(
    download_id: int,
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
        "admin/file_form.html",
        {
            "request": request,
            "categories": categories,
            "tags": tags,
            "all_downloads": all_downloads,
            "edit_mode": True,
            "download": download,
            "admin_user": _admin,
            "flash_message": flash_message,
            "file_size_val": file_size_val,
            "file_size_unit": file_size_unit,
        },
    )


@router.post("/downloads/{download_id}/edit", name="admin_download_edit_post")
async def download_edit_post(
    download_id: int,
    request: Request,
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    version: Optional[str] = Form(None),
    file_type: Optional[str] = Form(None),
    external_url: Optional[str] = Form(None),
    file_size_value: Optional[str] = Form(None),
    file_size_unit: str = Form("MB"),
    icon_type: Optional[str] = Form(None),
    icon_image_url: Optional[str] = Form(None),
    icon_image_final_path: Optional[str] = Form(None),
    icon_image_cleared: Optional[str] = Form(None),
    category_id: Optional[str] = Form(None),
    parent_id: Optional[str] = Form(None),
    os_tags: List[str] = Form(default_factory=list),
    is_active: bool = Form(False),
    is_featured: bool = Form(False),
    tag_ids: List[str] = Form(default_factory=list),
    upload_file: Optional[UploadFile] = File(None),
    icon_image_file: Optional[UploadFile] = File(None),
):
    download = await crud.get_download_by_id(session, download_id)
    if not download:
        raise HTTPException(status_code=404, detail="Download bulunamadı.")

    # ── Dosya yükleme ────────────────────────────────────────────────────
    file_path: Optional[str] = None
    if upload_file and upload_file.filename:
        file_path = await _save_upload(upload_file)

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
        icon_img_path = await _save_icon_upload(icon_image_file)

    # ── Tip dönüşümleri (boş string → None) ─────────────────────────────
    cat_id      = _int_or_none(category_id)
    par_id      = _int_or_none(parent_id)
    size_bytes  = _parse_file_size_to_bytes(file_size_value, file_size_unit)
    tag_id_list = [int(t) for t in tag_ids if t and str(t).isdigit()]

    try:
        data = DownloadUpdate(
            title=title,
            description=description or None,
            version=version or None,
            file_type=FileType(file_type) if file_type else None,
            file_path=file_path or download.file_path,
            external_url=external_url or None,
            file_size_bytes=size_bytes,
            icon_type=IconType(icon_type) if icon_type else None,
            icon_image_path=icon_img_path,
            icon_image_url=icon_img_url,
            os_compatibility=os_tags,
            category_id=cat_id,
            parent_id=par_id,
            is_active=is_active,
            is_featured=is_featured,
            tag_ids=tag_id_list,
        )
        await crud.update_download(session, download, data)
    except Exception as exc:
        await session.rollback()
        logger.error("Download güncelleme hatası: %s", exc)
        categories = await crud.get_categories(session)
        tags = await crud.get_tags(session)
        all_dl, _ = await crud.get_downloads_paginated(
            session, page=1, page_size=200, include_inactive=True
        )
        return templates.TemplateResponse(
            "admin/file_form.html",
            {
                "request": request,
                "categories": categories,
                "tags": tags,
                "all_downloads": all_dl,
                "edit_mode": True,
                "download": download,
                "file_size_val": file_size_value,
                "file_size_unit": file_size_unit,
                "error": str(exc),
                "admin_user": _admin,
            },
            status_code=422,
        )

    request.session["flash_message"] = "Değişiklikler başarıyla kaydedildi."
    return _redirect(f"/admin/downloads/{download_id}/edit")


# ---------------------------------------------------------------------------
# Download — Sil
# ---------------------------------------------------------------------------

@router.post("/downloads/{download_id}/delete", name="admin_download_delete")
async def download_delete(
    download_id: int,
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
):
    download = await crud.get_download_by_id(session, download_id)
    if not download:
        raise HTTPException(status_code=404, detail="Download bulunamadı.")

    await crud.delete_download(session, download)
    return _redirect("/admin")


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------

@router.get("/categories", name="admin_categories")
async def categories_view(
    request: Request,
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
):
    categories = await crud.get_categories(session)
    counts = await crud.get_category_download_counts(session)
    flash_message = request.session.pop("flash_message", None)
    return templates.TemplateResponse(
        "admin/categories.html",
        {
            "request": request,
            "categories": categories,
            "category_counts": counts,
            "admin_user": _admin,
            "flash_message": flash_message,
        },
    )


@router.post("/categories", name="admin_category_create")
async def category_create(
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
    name: str = Form(...),
    description: Optional[str] = Form(None),
):
    data = CategoryCreate(name=name, description=description or None)
    await crud.create_category(session, data)
    return _redirect("/admin/categories")


@router.post("/categories/{category_id}/edit", name="admin_category_edit")
async def category_edit(
    category_id: int,
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
    name: str = Form(...),
    description: Optional[str] = Form(None),
):
    category = await crud.get_category_by_id(session, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Kategori bulunamadı.")
    data = CategoryUpdate(name=name, description=description or None)
    await crud.update_category(session, category, data)
    return _redirect("/admin/categories")


@router.post("/categories/{category_id}/delete", name="admin_category_delete")
async def category_delete(
    category_id: int,
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
):
    category = await crud.get_category_by_id(session, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Kategori bulunamadı.")
    await crud.delete_category(session, category)
    return _redirect("/admin/categories")


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
    return templates.TemplateResponse(
        "admin/tags.html",
        {"request": request, "tags": tags, "admin_user": _admin, "flash_message": flash_message},
    )


@router.post("/tags", name="admin_tag_create")
async def tag_create(
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
    name: str = Form(...),
):
    data = TagCreate(name=name)
    await crud.create_tag(session, data)
    return _redirect("/admin/tags")


@router.post("/tags/{tag_id}/edit", name="admin_tag_edit")
async def tag_edit(
    tag_id: int,
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
    name: str = Form(...),
):
    from slugify import slugify
    tag = await crud.get_tag_by_id(session, tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="Tag bulunamadı.")
    tag.name = name
    tag.slug = slugify(name, allow_unicode=False, separator="-")
    await session.commit()
    await session.refresh(tag)
    return _redirect("/admin/tags")


@router.post("/tags/{tag_id}/delete", name="admin_tag_delete")
async def tag_delete(
    tag_id: int,
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
):
    tag = await crud.get_tag_by_id(session, tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="Tag bulunamadı.")
    await crud.delete_tag(session, tag)
    return _redirect("/admin/tags")


# ---------------------------------------------------------------------------
# Ayarlar — Menü Düzenleme
# ---------------------------------------------------------------------------

@router.get("/settings/menu", name="admin_settings_menu")
async def settings_menu_view(
    request: Request,
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
):
    menu_items = await crud.get_menu_items(session)
    flash_message = request.session.pop("flash_message", None)
    return templates.TemplateResponse(
        "admin/menu_editor.html",
        {
            "request": request,
            "menu_items": menu_items,
            "admin_user": _admin,
            "flash_message": flash_message,
        },
    )


@router.post("/settings/menu", name="admin_menu_item_create")
async def menu_item_create(
    request: Request,
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
    label: str = Form(...),
    url: str = Form(...),
    icon: Optional[str] = Form(None),
    is_active: bool = Form(False),
    open_in_new_tab: bool = Form(False),
):
    data = MenuItemCreate(
        label=label, url=url, icon=icon or None,
        is_active=is_active, open_in_new_tab=open_in_new_tab,
    )
    await crud.create_menu_item(session, data)
    request.session["flash_message"] = f"\"{label}\" menü öğesi eklendi."
    return _redirect("/admin/settings/menu")


@router.post("/settings/menu/{item_id}/edit", name="admin_menu_item_edit")
async def menu_item_edit(
    item_id: int,
    request: Request,
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
    label: str = Form(...),
    url: str = Form(...),
    icon: Optional[str] = Form(None),
    is_active: bool = Form(False),
    open_in_new_tab: bool = Form(False),
):
    item = await crud.get_menu_item_by_id(session, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Menü öğesi bulunamadı.")
    data = MenuItemUpdate(
        label=label, url=url, icon=icon or None,
        is_active=is_active, open_in_new_tab=open_in_new_tab,
    )
    await crud.update_menu_item(session, item, data)
    request.session["flash_message"] = "Menü öğesi güncellendi."
    return _redirect("/admin/settings/menu")


@router.post("/settings/menu/{item_id}/delete", name="admin_menu_item_delete")
async def menu_item_delete(
    item_id: int,
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
):
    item = await crud.get_menu_item_by_id(session, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Menü öğesi bulunamadı.")
    await crud.delete_menu_item(session, item)
    return _redirect("/admin/settings/menu")


class _MenuReorderPayload(BaseModel):
    ids: List[int]


@router.post("/settings/menu/reorder", name="admin_menu_reorder")
async def menu_reorder(
    payload: _MenuReorderPayload,
    session: AsyncSession = Depends(get_db),
    _admin: str = Depends(require_admin),
):
    await crud.reorder_menu_items(session, payload.ids)
    return {"ok": True}

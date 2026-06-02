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
"""

from __future__ import annotations

import logging
import shutil
from typing import List, Optional

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
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.config import settings
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


async def _save_upload(file: UploadFile) -> str:
    """Yüklenen dosyayı UPLOAD_DIR'e kaydeder, yolu döndürür."""
    upload_dir = settings.upload_path
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / file.filename
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    logger.info("Dosya yüklendi: %s", dest)
    return str(dest)


async def _save_icon_upload(file: UploadFile) -> str:
    """İkon görselini icons/ alt dizinine kaydeder, web yolunu döndürür."""
    icons_dir = settings.upload_path / "icons"
    icons_dir.mkdir(parents=True, exist_ok=True)
    dest = icons_dir / file.filename
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    logger.info("İkon yüklendi: %s", dest)
    return f"/static/uploads/icons/{file.filename}"


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
    # Boş string parse hatası vermemesi için str olarak al:
    file_size_bytes: Optional[str] = Form(None),
    icon_type: str = Form("auto"),
    icon_image_url: Optional[str] = Form(None),
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
    icon_img_path: Optional[str] = None
    if icon_image_file and icon_image_file.filename:
        icon_img_path = await _save_icon_upload(icon_image_file)

    # ── Tip dönüşümleri (boş string → None) ─────────────────────────────
    cat_id     = _int_or_none(category_id)
    par_id     = _int_or_none(parent_id)
    size_bytes = _int_or_none(file_size_bytes)
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
            icon_image_url=icon_image_url or None,
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
                "error": str(exc),
                "admin_user": _admin,
            },
            status_code=422,
        )

    return _redirect(f"/admin/downloads/{download.id}/edit")


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
    # Boş string parse hatası vermemesi için str olarak al:
    file_size_bytes: Optional[str] = Form(None),
    icon_type: Optional[str] = Form(None),
    icon_image_url: Optional[str] = Form(None),
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
    icon_img_path: Optional[str] = download.icon_image_path
    if icon_image_file and icon_image_file.filename:
        icon_img_path = await _save_icon_upload(icon_image_file)

    # ── Tip dönüşümleri (boş string → None) ─────────────────────────────
    cat_id      = _int_or_none(category_id)
    par_id      = _int_or_none(parent_id)
    size_bytes  = _int_or_none(file_size_bytes)
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
            icon_image_url=icon_image_url or None,
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
                "error": str(exc),
                "admin_user": _admin,
            },
            status_code=422,
        )

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
    return templates.TemplateResponse(
        "admin/categories.html",
        {
            "request": request,
            "categories": categories,
            "category_counts": counts,
            "admin_user": _admin,
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
    return templates.TemplateResponse(
        "admin/tags.html",
        {"request": request, "tags": tags, "admin_user": _admin},
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

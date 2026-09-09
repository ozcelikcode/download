"""
Public router — kullanıcıya açık tüm sayfalar.

Rotalar:
  GET  /                    → Anasayfa (paginated list)
  GET  /category/{slug}     → Kategori filtreli liste
  GET  /search              → Arama sonuçları
  GET  /download/{slug}     → Dosya detay sayfası
  GET  /dl/{slug}           → Gerçek indirme (redirect/stream)
"""

from __future__ import annotations

import logging
import json
import math
import mimetypes
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.config import settings
from app.checksums import file_checksum
from app.dependencies import get_db, get_optional_admin_username, get_request_ip
from app.i18n import translate
from app.models import FileType
from app.templating import templates

logger = logging.getLogger(__name__)

router = APIRouter(tags=["public"])

PAGE_SIZE = 12


@router.get("/language/{language}", name="set_language")
async def set_language(language: str, return_to: str = Query("/")) -> RedirectResponse:
    if language not in {"tr", "en"}:
        raise HTTPException(status_code=404, detail="Dil bulunamadı.")
    parsed = urlsplit(return_to)
    target = return_to if not parsed.scheme and not parsed.netloc and return_to.startswith("/") and "\\" not in return_to else "/"
    response = RedirectResponse(target, status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        "ui_language",
        language,
        max_age=365 * 24 * 60 * 60,
        samesite="lax",
        secure=settings.app_base_url.startswith("https://"),
    )
    return response


# ---------------------------------------------------------------------------
# Yardımcı: sidebar context (kategoriler + tag'lar her sayfada)
# ---------------------------------------------------------------------------

async def _sidebar_context(request: Request, session: AsyncSession) -> dict:
    categories = await crud.get_categories_ordered(session)
    tags = await crud.get_tags_ordered(session)
    counts = await crud.get_category_download_counts(session)
    site_settings = await crud.get_site_settings(session)
    menu_items = (await crud.get_menu_items(session, active_only=True, location="navbar"))[:site_settings.navbar_limit]
    footer_menu_items = (await crud.get_menu_items(session, active_only=True, location="footer"))[:site_settings.footer_limit]
    sidebar_block_order = [
        b for b in site_settings.sidebar_block_order.split(",") if b
    ] or ["search", "categories", "tags"]
    admin_username = get_optional_admin_username(request)
    try:
        hero_components = json.loads(site_settings.hero_components)
    except (TypeError, json.JSONDecodeError):
        hero_components = []
    return {
        "sidebar_categories": categories[:site_settings.sidebar_category_limit],
        "sidebar_tags": tags[:site_settings.sidebar_tag_limit],
        "total_categories": len(categories),
        "total_tags": len(tags),
        "category_counts": counts,
        "menu_items": menu_items,
        "footer_menu_items": footer_menu_items,
        "sidebar_block_order": sidebar_block_order,
        "is_admin": bool(admin_username),
        "admin_username": admin_username,
        "site_settings": site_settings,
        "hero_components": hero_components,
    }


# ---------------------------------------------------------------------------
# GET /
# ---------------------------------------------------------------------------

@router.get("/", name="index")
async def index(
    request: Request,
    page: int = Query(1, ge=1),
    session: AsyncSession = Depends(get_db),
):
    items, total = await crud.get_downloads_paginated(
        session, page=page, page_size=PAGE_SIZE
    )
    featured, _ = await crud.get_downloads_paginated(
        session, page=1, page_size=6, featured_only=True
    )
    total_pages = max(1, math.ceil(total / PAGE_SIZE))

    ctx = {
        "request": request,
        "downloads": items,
        "featured": featured,
        "total": total,
        "page": page,
        "page_size": PAGE_SIZE,
        "total_pages": total_pages,
        "current_category": None,
        "current_search": None,
        "page_title": translate(request, "all_downloads"),
        "meta_description": translate(request, "meta_default"),
    }
    ctx.update(await _sidebar_context(request, session))
    return templates.TemplateResponse(request=request, name="index.html", context=ctx)


# ---------------------------------------------------------------------------
# GET /category/{slug}
# ---------------------------------------------------------------------------

@router.get("/category/{slug}", name="category")
async def category_view(
    slug: str,
    request: Request,
    page: int = Query(1, ge=1),
    session: AsyncSession = Depends(get_db),
):
    category = await crud.get_category_by_slug(session, slug)
    if not category:
        raise HTTPException(status_code=404, detail="Kategori bulunamadı.")

    items, total = await crud.get_downloads_paginated(
        session, page=page, page_size=PAGE_SIZE, category_slug=slug
    )
    total_pages = max(1, math.ceil(total / PAGE_SIZE))

    ctx = {
        "request": request,
        "downloads": items,
        "featured": [],
        "total": total,
        "page": page,
        "page_size": PAGE_SIZE,
        "total_pages": total_pages,
        "current_category": category,
        "current_search": None,
        "page_title": category.name,
        "meta_description": category.description or f"{category.name} {translate(request, 'category_meta')}",
    }
    ctx.update(await _sidebar_context(request, session))
    return templates.TemplateResponse(request=request, name="index.html", context=ctx)


# ---------------------------------------------------------------------------
# GET /search
# ---------------------------------------------------------------------------

@router.get("/search", name="search")
async def search(
    request: Request,
    q: str = Query("", alias="q"),
    page: int = Query(1, ge=1),
    session: AsyncSession = Depends(get_db),
):
    q = q.strip()
    items, total = await crud.get_downloads_paginated(
        session,
        page=page,
        page_size=PAGE_SIZE,
        search=q if q else None,
    )
    total_pages = max(1, math.ceil(total / PAGE_SIZE))

    ctx = {
        "request": request,
        "downloads": items,
        "featured": [],
        "total": total,
        "page": page,
        "page_size": PAGE_SIZE,
        "total_pages": total_pages,
        "current_category": None,
        "current_search": q,
        "page_title": f'"{q}" {translate(request, "search_results")}' if q else translate(request, "search_page"),
        "meta_description": f"{q} {translate(request, 'search_meta')}" if q else translate(request, "search_meta_default"),
    }
    ctx.update(await _sidebar_context(request, session))
    return templates.TemplateResponse(request=request, name="index.html", context=ctx)


# ---------------------------------------------------------------------------
# GET /tag/{slug}
# ---------------------------------------------------------------------------

@router.get("/tag/{slug}", name="tag")
async def tag_view(
    slug: str,
    request: Request,
    page: int = Query(1, ge=1),
    session: AsyncSession = Depends(get_db),
):
    tag = await crud.get_tag_by_slug(session, slug)
    if not tag:
        raise HTTPException(status_code=404, detail="Etiket bulunamadı.")

    items, total = await crud.get_downloads_paginated(
        session, page=page, page_size=PAGE_SIZE, tag_slug=slug
    )
    total_pages = max(1, math.ceil(total / PAGE_SIZE))

    ctx = {
        "request": request,
        "downloads": items,
        "featured": [],
        "total": total,
        "page": page,
        "page_size": PAGE_SIZE,
        "total_pages": total_pages,
        "current_category": None,
        "current_tag": tag,
        "current_search": None,
        "page_title": f"#{tag.name}",
        "meta_description": f"{tag.name} {translate(request, 'tag_meta')}",
    }
    ctx.update(await _sidebar_context(request, session))
    return templates.TemplateResponse(request=request, name="index.html", context=ctx)


# ---------------------------------------------------------------------------
# GET /download/{slug}
# ---------------------------------------------------------------------------

@router.get("/download/{slug}", name="detail")
async def detail(
    slug: str,
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    download = await crud.get_download_by_slug(session, slug)
    if not download:
        raise HTTPException(status_code=404, detail="İndirme bulunamadı.")

    ctx = {
        "request": request,
        "download": download,
        "page_title": f"{download.title} {download.version or ''}".strip(),
        "meta_description": (download.description or f"{download.title} — ücretsiz indir.")[:160],
        "current_category": download.category,
        "current_search": None,
        "version_timeline": _build_version_timeline(download),
        "sha256": await file_checksum(session, download.file_path) if download.file_type == FileType.local else None,
    }
    ctx.update(await _sidebar_context(request, session))

    return templates.TemplateResponse(request=request, name="detail.html", context=ctx)


def _build_version_timeline(download) -> list:
    """
    Detay sayfasındaki "Sürüm Geçmişi" kutusu için birleşik zaman çizgisi.

    İki farklı kaynağı tek listede birleştirir:
    - Manuel bağlantılı sürümler (ayrı sayfası olan, `parent_id` ile
      ilişkilendirilmiş eski/yeni büyük sürüm kayıtları) → tıklanabilir.
    - Otomatik sürüm geçmişi (aynı kaydın "Sürüm" alanı admin panelinden
      değiştirildiğinde otomatik kaydedilen eski değerler) → aynı sayfa,
      yalnızca bilgi amaçlı.

    Şu an görüntülenen kayıt her zaman listenin başında sabit durur.
    """
    root = download.parent if download.parent else download

    entries = [{
        "version": download.version or download.title,
        "is_latest": download.is_latest_version,
        "date": download.updated_at,
        "url": None,
        "is_current": True,
    }]

    for v in root.versions:
        if v.id == download.id:
            continue
        entries.append({
            "version": v.version or v.title,
            "is_latest": v.is_latest_version,
            "date": v.created_at,
            "url": f"/download/{v.slug}",
            "is_current": False,
        })

    if root.id != download.id:
        entries.append({
            "version": root.version or root.title,
            "is_latest": root.is_latest_version,
            "date": root.created_at,
            "url": f"/download/{root.slug}",
            "is_current": False,
        })

    for h in download.version_history:
        entries.append({
            "version": h.version,
            "is_latest": False,
            "date": h.changed_at,
            "url": None,
            "is_current": False,
        })

    current = entries[0]
    rest = sorted(entries[1:], key=lambda e: e["date"], reverse=True)
    return [current] + rest


# ---------------------------------------------------------------------------
# GET /dl/{slug}  — gerçek indirme
# ---------------------------------------------------------------------------

@router.get("/dl/{slug}", name="do_download")
async def do_download(
    slug: str,
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    download = await crud.get_download_by_slug(session, slug)
    if not download:
        raise HTTPException(status_code=404, detail="İndirme bulunamadı.")

    ip = get_request_ip(request)
    ua = request.headers.get("user-agent", "")

    # Rate limit kontrolü
    allowed = await crud.check_rate_limit(
        session, ip, max_per_hour=settings.rate_limit_downloads_per_hour
    )
    if not allowed:
        logger.warning("Rate limit aşıldı: ip=%s download_id=%d", ip, download.id)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Saatlik indirme limitine ulaştınız. Lütfen bekleyiniz.",
        )

    # Yalnızca sunulabilecek dosyalar sayacı ve saatlik kotayı tüketir.
    file_path = None
    if download.file_type == FileType.local:
        file_path = Path(download.file_path) if download.file_path else None
        if file_path is None or not file_path.is_file():
            logger.error("Dosya bulunamadı: %s", download.file_path)
            raise HTTPException(status_code=404, detail="Dosya sunucuda bulunamadı.")
    elif not download.external_url:
        logger.error("Dış bağlantı bulunamadı: download_id=%d", download.id)
        raise HTTPException(status_code=404, detail="İndirme bağlantısı bulunamadı.")

    # Log yaz + sayacı artır
    await crud.create_download_log(session, download.id, ip, ua[:500])
    await crud.increment_download_count(session, download.id)

    logger.info("İndirme başlatıldı: slug=%r ip=%s", slug, ip)

    if download.file_type == FileType.external:
        # Dış bağlantıya yönlendir
        return RedirectResponse(
            url=download.external_url,
            status_code=status.HTTP_302_FOUND,
        )

    # Lokal dosya akışı
    media_type, _ = mimetypes.guess_type(str(file_path))
    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type=media_type or "application/octet-stream",
    )

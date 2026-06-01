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
import math
import mimetypes
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.config import settings
from app.dependencies import get_db, get_request_ip
from app.models import FileType
from app.templating import templates

logger = logging.getLogger(__name__)

router = APIRouter(tags=["public"])

PAGE_SIZE = 12


# ---------------------------------------------------------------------------
# Yardımcı: sidebar context (kategoriler + tag'lar her sayfada)
# ---------------------------------------------------------------------------

async def _sidebar_context(session: AsyncSession) -> dict:
    categories = await crud.get_categories(session)
    tags = await crud.get_tags(session)
    counts = await crud.get_category_download_counts(session)
    return {
        "sidebar_categories": categories,
        "sidebar_tags": tags,
        "category_counts": counts,
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
        "page_title": "Tüm İndirmeler",
        "meta_description": "Ücretsiz yazılım, araç ve belgeleri indirin.",
    }
    ctx.update(await _sidebar_context(session))
    return templates.TemplateResponse("index.html", ctx)


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
        "meta_description": category.description or f"{category.name} kategorisindeki indirmeler.",
    }
    ctx.update(await _sidebar_context(session))
    return templates.TemplateResponse("index.html", ctx)


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
        "page_title": f'"{q}" için arama sonuçları' if q else "Arama",
        "meta_description": f"{q} için indirme sonuçları." if q else "İndirme arama.",
    }
    ctx.update(await _sidebar_context(session))
    return templates.TemplateResponse("index.html", ctx)


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
        "meta_description": f"{tag.name} etiketli indirmeler.",
    }
    ctx.update(await _sidebar_context(session))
    return templates.TemplateResponse("index.html", ctx)


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
    }
    ctx.update(await _sidebar_context(session))

    return templates.TemplateResponse("detail.html", ctx)


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
    file_path = Path(download.file_path)
    if not file_path.exists():
        logger.error("Dosya bulunamadı: %s", file_path)
        raise HTTPException(status_code=404, detail="Dosya sunucuda bulunamadı.")

    media_type, _ = mimetypes.guess_type(str(file_path))
    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type=media_type or "application/octet-stream",
    )

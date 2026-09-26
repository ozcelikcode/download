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
from datetime import datetime
from urllib.parse import quote
from xml.etree import ElementTree
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.config import settings
from app.checksums import file_checksum
from app.content_security import normalize_http_url, rich_text_to_plain_text
from app.dependencies import get_db, get_optional_admin_username, get_request_ip
from app.i18n import translate
from app.models import Category, Download, DownloadTag, FileType, Tag
from app.seo import inspect_public_base_url
from app.schemas import PublicDownloadFilters
from app.templating import templates

logger = logging.getLogger(__name__)

router = APIRouter(tags=["public"])

PAGE_SIZE = 12
_SITEMAP_NAMESPACE = "http://www.sitemaps.org/schemas/sitemap/0.9"


@router.get("/robots.txt", include_in_schema=False)
async def robots_txt() -> PlainTextResponse:
    """Arama motorlarına herkese açık sayfaları ve sitemap konumunu bildir."""
    lines = ["User-agent: *", "Allow: /", "Disallow: /admin", "Disallow: /dl/"]
    base_url, _, _ = inspect_public_base_url()
    if base_url:
        lines.append(f"Sitemap: {base_url}/sitemap.xml")
    return PlainTextResponse("\n".join(lines) + "\n")


@router.get("/sitemap.xml", include_in_schema=False)
async def sitemap_xml(session: AsyncSession = Depends(get_db)) -> Response:
    """Yalnızca herkese açık içerik ve gezinme sayfaları için sitemap üret."""
    base_url, _, _ = inspect_public_base_url()
    if not base_url:
        return PlainTextResponse(
            "APP_BASE_URL geçerli bir HTTP/HTTPS adresi olmalıdır.\n",
            status_code=503,
        )

    root = ElementTree.Element("urlset", xmlns=_SITEMAP_NAMESPACE)

    def add_url(path: str, last_modified: datetime | None = None) -> None:
        url_node = ElementTree.SubElement(root, "url")
        ElementTree.SubElement(url_node, "loc").text = f"{base_url}{path}"
        if last_modified:
            ElementTree.SubElement(url_node, "lastmod").text = last_modified.date().isoformat()

    add_url("/")
    categories = (
        await session.execute(
            select(Category.slug, Category.created_at)
            .join(Download, Download.category_id == Category.id)
            .where(
                Download.parent_id.is_(None),
                Download.is_active.is_(True),
                Download.is_draft.is_(False),
            )
            .distinct()
            .order_by(Category.slug)
        )
    ).all()
    for category in categories:
        add_url(f"/category/{quote(category.slug, safe='')}", category.created_at)

    tags = (
        await session.scalars(
            select(Tag.slug)
            .join(DownloadTag, DownloadTag.tag_id == Tag.id)
            .join(Download, Download.id == DownloadTag.download_id)
            .where(
                Download.parent_id.is_(None),
                Download.is_active.is_(True),
                Download.is_draft.is_(False),
            )
            .distinct()
            .order_by(Tag.slug)
        )
    ).all()
    for slug in tags:
        add_url(f"/tag/{quote(slug, safe='')}")

    downloads = (
        await session.execute(
            select(Download.slug, Download.updated_at)
            .where(Download.is_active.is_(True), Download.is_draft.is_(False))
            .order_by(Download.slug)
        )
    ).all()
    for download in downloads:
        add_url(f"/download/{quote(download.slug, safe='')}", download.updated_at)

    return Response(
        content=ElementTree.tostring(root, encoding="utf-8", xml_declaration=True),
        media_type="application/xml",
    )


def _public_list_filters(
    sort: str = Query("newest", pattern="^(newest|popular|title)$"),
    os: str = Query("", pattern="^(|windows|macos|linux|android|ios|web)$"),
    source: str = Query("", pattern="^(|local|external)$"),
    trust: str = Query("", pattern="^(|official|third_party)$"),
) -> PublicDownloadFilters:
    return PublicDownloadFilters(sort=sort, os=os, source=source, trust=trust)


def _filter_context(filters: PublicDownloadFilters, search: str = "") -> dict:
    params = filters.model_dump()
    if search:
        params["q"] = search
    return {
        "filters": filters,
        "filter_params": params,
        "has_filters": filters.is_active,
    }


def _private_download_file(value: str | None) -> Path | None:
    """Yalnızca özel indirme deposundaki normal dosyaların sunulmasına izin ver."""
    if not value:
        return None
    path = Path(value).resolve()
    root = settings.download_path.resolve()
    if path == root or not path.is_relative_to(root) or not path.is_file():
        return None
    return path


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
    filters: PublicDownloadFilters = Depends(_public_list_filters),
    session: AsyncSession = Depends(get_db),
):
    items, total = await crud.get_downloads_paginated(
        session,
        page=page,
        page_size=PAGE_SIZE,
        file_type_filter=filters.source or None,
        os_filter=filters.os or None,
        official_filter=filters.trust or None,
        sort=filters.sort,
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
        "noindex": page > 1 or filters.is_active,
    }
    ctx.update(_filter_context(filters))
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
    filters: PublicDownloadFilters = Depends(_public_list_filters),
    session: AsyncSession = Depends(get_db),
):
    category = await crud.get_category_by_slug(session, slug)
    if not category:
        raise HTTPException(status_code=404, detail="Kategori bulunamadı.")

    items, total = await crud.get_downloads_paginated(
        session,
        page=page,
        page_size=PAGE_SIZE,
        category_slug=slug,
        file_type_filter=filters.source or None,
        os_filter=filters.os or None,
        official_filter=filters.trust or None,
        sort=filters.sort,
    )
    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    category_meta_description = (category.description or "").strip() or (
        f"{category.name} {translate(request, 'category_meta')}"
    )

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
        "meta_description": category_meta_description[:160],
        "noindex": page > 1 or filters.is_active,
    }
    ctx.update(_filter_context(filters))
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
    filters: PublicDownloadFilters = Depends(_public_list_filters),
    session: AsyncSession = Depends(get_db),
):
    q = q.strip()
    items, total = await crud.get_downloads_paginated(
        session,
        page=page,
        page_size=PAGE_SIZE,
        search=q if q else None,
        file_type_filter=filters.source or None,
        os_filter=filters.os or None,
        official_filter=filters.trust or None,
        sort=filters.sort,
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
        "meta_description": (
            f"{q} {translate(request, 'search_meta')}" if q else translate(request, "search_meta_default")
        )[:160],
        "noindex": True,
    }
    ctx.update(_filter_context(filters, q))
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
    filters: PublicDownloadFilters = Depends(_public_list_filters),
    session: AsyncSession = Depends(get_db),
):
    tag = await crud.get_tag_by_slug(session, slug)
    if not tag:
        raise HTTPException(status_code=404, detail="Etiket bulunamadı.")

    items, total = await crud.get_downloads_paginated(
        session,
        page=page,
        page_size=PAGE_SIZE,
        tag_slug=slug,
        file_type_filter=filters.source or None,
        os_filter=filters.os or None,
        official_filter=filters.trust or None,
        sort=filters.sort,
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
        "noindex": page > 1 or filters.is_active,
    }
    ctx.update(_filter_context(filters))
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

    local_file = (
        _private_download_file(download.file_path)
        if download.file_type == FileType.local
        else None
    )
    related_downloads = await crud.get_related_downloads(session, download)

    ctx = {
        "request": request,
        "download": download,
        "page_title": f"{download.title} {download.version or ''}".strip(),
        "meta_description": (
            (download.short_description or "").strip()
            or rich_text_to_plain_text(download.description)
            or f"{download.title} — ücretsiz indir."
        )[:160],
        "current_category": download.category,
        "current_search": None,
        "version_timeline": _build_version_timeline(download),
        "related_downloads": related_downloads,
        "download_filename": local_file.name if local_file else None,
        "sha256": (
            await file_checksum(session, str(local_file))
            if local_file
            else None
        ),
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
    download_id = download.id
    download_type = download.file_type

    # Yalnızca sunulabilecek dosyalar sayacı ve saatlik kotayı tüketir.
    file_path = None
    external_url = None
    if download_type == FileType.local:
        file_path = _private_download_file(download.file_path)
        if file_path is None:
            logger.error("Dosya bulunamadı: %s", download.file_path)
            raise HTTPException(status_code=404, detail="Dosya sunucuda bulunamadı.")
    else:
        try:
            external_url = normalize_http_url(download.external_url)
        except ValueError:
            logger.error("Güvensiz dış bağlantı engellendi: download_id=%d", download_id)
            raise HTTPException(status_code=404, detail="İndirme bağlantısı geçersiz.")
        if external_url is None:
            logger.error("Dış bağlantı bulunamadı: download_id=%d", download_id)
            raise HTTPException(status_code=404, detail="İndirme bağlantısı bulunamadı.")

    allowed = await crud.record_download_if_allowed(
        session,
        download_id,
        ip,
        ua[:500],
        max_per_hour=settings.rate_limit_downloads_per_hour,
    )
    if not allowed:
        logger.warning("Rate limit aşıldı: ip=%s download_id=%d", ip, download_id)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Saatlik indirme limitine ulaştınız. Lütfen bekleyiniz.",
        )

    logger.info("İndirme başlatıldı: slug=%r ip=%s", slug, ip)

    if download_type == FileType.external:
        # Dış bağlantıya yönlendir
        return RedirectResponse(
            url=external_url,
            status_code=status.HTTP_302_FOUND,
        )

    # Lokal dosya akışı
    media_type, _ = mimetypes.guess_type(str(file_path))
    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type=media_type or "application/octet-stream",
    )

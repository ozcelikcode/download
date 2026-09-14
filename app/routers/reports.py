"""Admin bağlantı raporu ve kalıcı işlem geçmişi."""

import json
import math
from datetime import datetime, timezone

import anyio
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import and_, func, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import ACTION_LABELS, ENTITY_LABELS, FIELD_LABELS
from app.dependencies import get_db, require_admin
from app.link_checks import check_link
from app.i18n import ui_language
from app.models import AuditLog, Download, FileType, LinkCheck
from app.security import require_csrf
from app.templating import templates

router = APIRouter(prefix="/admin", tags=["reports"], dependencies=[Depends(require_csrf), Depends(require_admin)])
PAGE_SIZE = 20
STATUSES = {"unchecked": "Kontrol edilmedi", "ok": "Erişilebilir", "broken": "Kırık", "restricted": "Erişim sınırlı", "error": "Kontrol hatası", "blocked": "Engellendi"}
STATUSES_EN = {"unchecked": "Not checked", "ok": "Available", "broken": "Broken", "restricted": "Restricted", "error": "Check failed", "blocked": "Blocked"}
ENTITY_LABELS_EN = {"login": "Login security", "downloads": "Content", "categories": "Category", "tags": "Tag", "menu_items": "Menu", "site_settings": "Settings", "media_assets": "Media", "download_version_history": "Version"}
ACTION_LABELS_EN = {"create": "Created", "update": "Updated", "delete": "Deleted", "replace": "File replaced", "crop": "Image cropped", "reorder": "Reordered", "bulk": "Bulk action", "transfer": "Transferred", "error": "Error", "login": "Signed in"}
FIELD_LABELS_EN = {
    "ip_address": "IP address", "name": "Name", "title": "Title", "slug": "URL slug", "description": "Description",
    "short_description": "Short description", "position": "Position", "version": "Version", "file_type": "Source type",
    "file_path": "File path", "external_url": "Download URL", "file_size_bytes": "File size (bytes)", "icon_type": "Icon type",
    "thumbnail_path": "Thumbnail", "icon_image_path": "Icon file", "icon_image_url": "Icon URL", "icon_extension": "File extension",
    "os_compatibility": "Operating systems", "category_id": "Category", "parent_id": "Related version", "is_active": "Published",
    "is_draft": "Draft", "is_featured": "Featured", "is_official_source": "Official source", "is_latest_version": "Latest version link",
    "label": "Label", "url": "URL", "icon": "Icon", "open_in_new_tab": "Open in new tab", "location": "Menu location",
    "site_name": "Site name", "site_language": "Site language", "site_icon": "Site icon", "site_icon_color": "Icon color",
    "sidebar_block_order": "Sidebar order", "theme_color": "Color theme", "logo_mode": "Logo layout", "logo_light_path": "Light logo",
    "logo_dark_path": "Dark logo", "hero_enabled": "Hero visibility", "hero_background": "Hero background", "hero_image_path": "Hero image",
    "hero_components": "Hero components", "navbar_limit": "Navbar limit", "footer_limit": "Footer limit",
    "sidebar_category_limit": "Sidebar category limit", "sidebar_tag_limit": "Sidebar tag limit", "admin_username": "Admin username",
    "admin_password_hash": "Admin password", "admin_icon": "Admin icon", "admin_icon_color": "Admin icon color",
    "session_max_age_minutes": "Session duration (minutes)", "path": "Media path", "display_name": "Display name",
    "uploaded_by": "Uploaded by", "download_id": "Content", "changed_at": "Changed at",
}


async def _check_downloads(session: AsyncSession, items: list[tuple[int, str]]) -> None:
    # En fazla dört kısa istek aynı anda; büyük dosyaların gövdesi okunmaz.
    limiter = anyio.CapacityLimiter(4)
    results = []

    async def run(download_id: int, url: str) -> None:
        async with limiter:
            result = await check_link(url)
            results.append((download_id, url, result))

    async with anyio.create_task_group() as group:
        for download_id, url in items:
            group.start_soon(run, download_id, url)
    for download_id, url, result in results:
        # Kontrol sürerken silinen/değiştirilen kayda eski sonuç yazılmaz.
        current = await session.scalar(select(Download.external_url).where(Download.id == download_id, Download.file_type == FileType.external))
        if current != url:
            continue
        values = {"url": url, **result.model_dump(), "checked_at": datetime.now(timezone.utc)}
        statement = insert(LinkCheck).values(download_id=download_id, **values)
        await session.execute(statement.on_conflict_do_update(index_elements=[LinkCheck.download_id], set_=values))
    await session.commit()


@router.get("/links", name="admin_links")
async def links(request: Request, page: int = Query(1, ge=1), state: str = Query("all", pattern="^(all|unchecked|ok|broken|restricted|error|blocked)$"), session: AsyncSession = Depends(get_db), admin: str = Depends(require_admin)) -> HTMLResponse:
    query = select(Download, LinkCheck).outerjoin(LinkCheck, and_(LinkCheck.download_id == Download.id, LinkCheck.url == Download.external_url)).where(Download.file_type == FileType.external)
    if state != "all":
        query = query.where(func.coalesce(LinkCheck.status, "unchecked") == state)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    rows = (await session.execute(query.order_by(Download.id.desc()).offset((page-1)*PAGE_SIZE).limit(PAGE_SIZE))).all()
    return templates.TemplateResponse(request=request, name="admin/links.html", context={
        "request": request, "admin_user": admin, "rows": rows, "statuses": STATUSES_EN if ui_language(request) == "en" else STATUSES,
        "state": state, "page": page, "total": total, "total_pages": max(1, math.ceil(total/PAGE_SIZE)),
    })


@router.post("/links/check", name="admin_links_check")
async def check_page(page: int = Query(1, ge=1), session: AsyncSession = Depends(get_db)) -> RedirectResponse:
    rows = (await session.execute(select(Download.id, Download.external_url).where(Download.file_type == FileType.external).order_by(Download.id.desc()).offset((page-1)*PAGE_SIZE).limit(PAGE_SIZE))).all()
    await session.rollback()  # Ağ kontrolü sırasında SQLite okuma işlemi açık tutulmaz.
    await _check_downloads(session, [(r.id, r.external_url or "") for r in rows])
    return RedirectResponse(f"/admin/links?page={page}", status_code=303)


@router.post("/links/{download_id}/check", name="admin_link_check")
async def check_one(download_id: int, session: AsyncSession = Depends(get_db)) -> RedirectResponse:
    row = (await session.execute(select(Download.id, Download.external_url).where(Download.id == download_id, Download.file_type == FileType.external))).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Dış bağlantı bulunamadı.")
    await session.rollback()
    await _check_downloads(session, [(row.id, row.external_url or "")])
    return RedirectResponse("/admin/links", status_code=303)


@router.get("/audit", name="admin_audit")
async def audit_view(request: Request, page: int = Query(1, ge=1), entity: str = "", level: str = "", session: AsyncSession = Depends(get_db), admin: str = Depends(require_admin)) -> HTMLResponse:
    query = select(AuditLog)
    if entity:
        query = query.where(AuditLog.entity == entity)
    if level in {"success", "error", "critical"}:
        query = query.where(AuditLog.level == level)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    rows = (await session.scalars(query.order_by(AuditLog.id.desc()).offset((page-1)*PAGE_SIZE).limit(PAGE_SIZE))).all()
    return templates.TemplateResponse(request=request, name="admin/audit.html", context={
        "request": request, "admin_user": admin, "rows": rows,
        "changes": {row.id: json.loads(row.changes) for row in rows},
        "entities": ENTITY_LABELS_EN if ui_language(request) == "en" else ENTITY_LABELS,
        "actions": ACTION_LABELS_EN if ui_language(request) == "en" else ACTION_LABELS,
        "fields": FIELD_LABELS_EN if ui_language(request) == "en" else FIELD_LABELS,
        "entity": entity, "level": level,
        "page": page, "total": total, "total_pages": max(1, math.ceil(total/PAGE_SIZE)),
    })

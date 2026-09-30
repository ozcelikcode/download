"""Standalone public pages and administrator-only page management."""

from __future__ import annotations

import math
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.audit import add_event
from app.content_security import rich_text_to_plain_text, sanitize_rich_text
from app.dependencies import SESSION_COOKIE, authenticated_user, get_db, require_admin
from app.i18n import translate
from app.models import MenuItem, Page
from app.page_schemas import PageInput
from app.routers.public import _sidebar_context
from app.security import require_csrf
from app.templating import templates


public_router = APIRouter(tags=["pages"])
admin_router = APIRouter(
    prefix="/admin/pages",
    tags=["admin-pages"],
    dependencies=[Depends(require_csrf), Depends(require_admin)],
)
PAGE_SIZE = 20


def _redirect(path: str) -> RedirectResponse:
    return RedirectResponse(path, status_code=303)


def _protected_headers(response) -> None:
    response.headers["Cache-Control"] = "private, no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = "img-src 'self' data:; object-src 'none'; frame-src 'none'; base-uri 'self'"


@public_router.get("/page/{slug}", name="page_view")
async def view_page(
    slug: str, request: Request, session: AsyncSession = Depends(get_db)
):
    page = await session.scalar(select(Page).where(Page.slug == slug))
    if page is None or page.deleted_at is not None:
        raise HTTPException(status_code=404, headers={"Cache-Control": "no-store"})
    settings = await crud.get_site_settings(session)
    user = await authenticated_user(request.cookies.get(SESSION_COOKIE, ""), settings, session)
    can_preview = user is not None and (user.role == "admin" or (user.role == "manager" and page.visibility == "public"))
    if (page.visibility == "private" or not page.is_published) and not can_preview:
        raise HTTPException(status_code=404, headers={"Cache-Control": "no-store"})
    body = sanitize_rich_text(page.body_html) or ""
    context = await _sidebar_context(request, session, settings)
    context.update({
        "is_admin": can_preview,
        "page": page,
        "safe_body": body,
        "page_title": page.title,
        "meta_description": rich_text_to_plain_text(body)[:160],
        "noindex": page.visibility == "private" or not page.is_published,
        "robots_directive": "noindex,nofollow,noarchive",
        "suppress_canonical": page.visibility == "private" or not page.is_published,
        "current_category": None,
        "current_search": None,
    })
    response = templates.TemplateResponse(request=request, name="page.html", context=context)
    if page.visibility == "private" or not page.is_published:
        _protected_headers(response)
    return response


@admin_router.get("")
async def list_pages(
    request: Request,
    page: int = Query(1, ge=1),
    session: AsyncSession = Depends(get_db),
):
    allowed = [Page.deleted_at.is_(None)]
    if request.state.admin_role != "admin":
        allowed.append(Page.visibility == "public")
    total = await session.scalar(select(func.count(Page.id)).where(*allowed)) or 0
    rows = (await session.scalars(
        select(Page).where(*allowed).order_by(Page.updated_at.desc(), Page.id.desc())
        .offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)
    )).all()
    response = templates.TemplateResponse(request=request, name="admin/pages.html", context={
        "pages": rows, "page": page, "total_pages": max(1, math.ceil(total / PAGE_SIZE)),
        "total": total, "admin_user": request.state.admin_user,
        "flash_message": request.session.pop("flash_message", None),
        "page_title": translate(request, "pages"),
    })
    _protected_headers(response)
    return response


def _editor_response(request: Request, page: Page | None, *, error: str | None = None, status_code: int = 200):
    response = templates.TemplateResponse(request=request, name="admin/page_form.html", context={
        "page": page, "error": error, "page_title": translate(request, "edit_page" if page else "new_page"),
        "admin_user": request.state.admin_user,
        "flash_message": request.session.pop("flash_message", None),
    }, status_code=status_code)
    _protected_headers(response)
    return response


@admin_router.get("/new")
async def new_page(request: Request):
    return _editor_response(request, None)


@admin_router.post("")
async def create_page(
    request: Request,
    title: str = Form(...),
    slug: str = Form(""),
    body_html: str = Form(""),
    visibility: str = Form("public"),
    is_published: bool = Form(False),
    session: AsyncSession = Depends(get_db),
):
    if visibility == "private" and request.state.admin_role != "admin":
        raise HTTPException(status_code=403, detail=translate(request, "permission_denied"))
    raw = dict(title=title, slug=slug, body_html=sanitize_rich_text(body_html) or "", visibility=visibility, is_published=is_published)
    try:
        data = PageInput.model_validate(raw)
    except ValidationError:
        return _editor_response(request, Page(**raw), error=translate(request, "page_invalid"), status_code=422)
    if await session.scalar(select(Page.id).where(Page.slug == data.slug)):
        return _editor_response(request, Page(**raw), error=translate(request, "page_slug_taken"), status_code=422)
    page = Page(**data.model_dump())
    session.add(page)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return _editor_response(request, Page(**raw), error=translate(request, "page_slug_taken"), status_code=422)
    request.session["flash_message"] = translate(request, "page_saved")
    return _redirect(f"/admin/pages/{page.id}/edit")


@admin_router.get("/{page_id}/edit")
async def edit_page(
    page_id: int, request: Request, session: AsyncSession = Depends(get_db)
):
    page = await session.get(Page, page_id)
    if page is None or page.deleted_at is not None or (page.visibility == "private" and request.state.admin_role != "admin"):
        raise HTTPException(status_code=404)
    return _editor_response(request, page)


@admin_router.post("/{page_id}/edit")
async def update_page(
    page_id: int,
    request: Request,
    title: str = Form(...),
    slug: str = Form(""),
    body_html: str = Form(""),
    visibility: str = Form("public"),
    is_published: bool = Form(False),
    session: AsyncSession = Depends(get_db),
):
    page = await session.get(Page, page_id)
    if page is None or page.deleted_at is not None or (page.visibility == "private" and request.state.admin_role != "admin"):
        raise HTTPException(status_code=404)
    if visibility == "private" and request.state.admin_role != "admin":
        raise HTTPException(status_code=403, detail=translate(request, "permission_denied"))
    raw = dict(title=title, slug=slug, body_html=sanitize_rich_text(body_html) or "", visibility=visibility, is_published=is_published)
    try:
        data = PageInput.model_validate(raw)
    except ValidationError:
        return _editor_response(request, Page(id=page_id, **raw), error=translate(request, "page_invalid"), status_code=422)
    existing = await session.scalar(select(Page.id).where(Page.slug == data.slug, Page.id != page_id))
    if existing:
        return _editor_response(request, Page(id=page_id, **raw), error=translate(request, "page_slug_taken"), status_code=422)
    old_slug = page.slug
    for key, value in data.model_dump().items():
        setattr(page, key, value)
    if old_slug != page.slug:
        for item in (await session.scalars(select(MenuItem).where(MenuItem.url == f"/page/{old_slug}"))).all():
            item.url = f"/page/{page.slug}"
    if page.visibility == "private" or not page.is_published:
        for item in (await session.scalars(select(MenuItem).where(MenuItem.url == f"/page/{page.slug}"))).all():
            item.is_active = False
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return _editor_response(request, Page(id=page_id, **raw), error=translate(request, "page_slug_taken"), status_code=422)
    request.session["flash_message"] = translate(request, "page_saved")
    return _redirect(f"/admin/pages/{page_id}/edit")


@admin_router.post("/{page_id}/delete")
async def delete_page(
    page_id: int, request: Request, session: AsyncSession = Depends(get_db)
):
    page = await session.get(Page, page_id)
    if page is None or page.deleted_at is not None or (page.visibility == "private" and request.state.admin_role != "admin"):
        raise HTTPException(status_code=404)
    for item in (await session.scalars(select(MenuItem).where(MenuItem.url == f"/page/{page.slug}"))).all():
        item.is_active = False
    session.info["audit_suppressed"] = True
    page.deleted_at = datetime.now(timezone.utc)
    page.is_published = False
    add_event(session, "trash", "pages", page.title, entity_id=page.id)
    await session.commit()
    request.session["flash_message"] = translate(request, "page_trashed")
    return _redirect("/admin/pages")


@admin_router.get("/trash")
async def page_trash(
    request: Request, page: int = Query(1, ge=1), session: AsyncSession = Depends(get_db)
):
    allowed = [Page.deleted_at.is_not(None)]
    if request.state.admin_role != "admin":
        allowed.append(Page.visibility == "public")
    total = await session.scalar(select(func.count(Page.id)).where(*allowed)) or 0
    rows = (await session.scalars(
        select(Page).where(*allowed).order_by(Page.deleted_at.desc(), Page.id.desc())
        .offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)
    )).all()
    response = templates.TemplateResponse(request=request, name="admin/page_trash.html", context={
        "pages": rows, "page": page, "total_pages": max(1, math.ceil(total / PAGE_SIZE)),
        "admin_user": request.state.admin_user,
        "flash_message": request.session.pop("flash_message", None),
    })
    _protected_headers(response)
    return response


@admin_router.post("/{page_id}/restore")
async def restore_page(
    page_id: int, request: Request, session: AsyncSession = Depends(get_db)
):
    page = await session.get(Page, page_id)
    if page is None or page.deleted_at is None or (page.visibility == "private" and request.state.admin_role != "admin"):
        raise HTTPException(status_code=404)
    session.info["audit_suppressed"] = True
    page.deleted_at = None
    add_event(session, "restore", "pages", page.title, entity_id=page.id)
    await session.commit()
    request.session["flash_message"] = translate(request, "page_restored")
    return _redirect("/admin/pages/trash")


@admin_router.post("/{page_id}/purge")
async def purge_page(
    page_id: int, request: Request, session: AsyncSession = Depends(get_db)
):
    page = await session.get(Page, page_id)
    if page is None or page.deleted_at is None or (page.visibility == "private" and request.state.admin_role != "admin"):
        raise HTTPException(status_code=404)
    session.info["audit_suppressed"] = True
    add_event(session, "purge", "pages", page.title, entity_id=page.id)
    await session.delete(page)
    await session.commit()
    request.session["flash_message"] = translate(request, "page_deleted")
    return _redirect("/admin/pages/trash")

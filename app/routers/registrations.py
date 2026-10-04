"""Bounded public applications and password-confirmed staff approval."""

from __future__ import annotations

import math

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import add_event
from app import crud
from app.database import get_db
from app.dependencies import get_request_ip, hash_password_async, require_admin
from app.i18n import translate
from app.models import RegistrationRequest, User
from app.routers.users import USERNAME_PATTERN, _confirm_password, _lock_actor
from app.security import require_csrf, reserve_login_attempt, require_secure_password_transport
from app.templating import templates
from app.routers.public import _sidebar_context

router = APIRouter(dependencies=[Depends(require_csrf)])
PAGE_SIZE = 20
MAX_PENDING = 500


async def application_page(request: Request, session: AsyncSession, *, error: str | None = None, received: bool = False, status_code: int = 200) -> Response:
    account = await crud.get_site_settings(session)
    context = await _sidebar_context(request, session, account)
    context.update({
        "error": translate(request, error) if error else None, "received": received,
        "hide_sidebar": True, "noindex": True, "robots_directive": "noindex,nofollow",
        "suppress_canonical": True, "page_title": translate(request, "registration_title"),
    })
    return templates.TemplateResponse(request=request, name="admin/register.html", context=context, status_code=status_code)


@router.get("/register")
async def register_get(request: Request, received: bool = False, session: AsyncSession = Depends(get_db)) -> Response:
    return await application_page(request, session, received=received and request.session.get("registration_submitted") is True)


@router.post("/register")
async def apply(request: Request, username: str = Form(...), password: str = Form(...),
                password_confirmation: str = Form(...), session: AsyncSession = Depends(get_db)) -> Response:
    # Count every submission; no raw client address or password enters a log or row.
    request.session.pop("registration_submitted", None)
    require_secure_password_transport(request)
    try:
        await reserve_login_attempt(session, "registration:" + get_request_ip(request))
    except HTTPException as exc:
        if exc.status_code != 429:
            raise
        response = await application_page(request, session, error="registration_rate_limited", status_code=429)
        response.headers.update(exc.headers or {})
        return response
    username = username.strip()
    if not USERNAME_PATTERN.fullmatch(username) or not 12 <= len(password) or len(password.encode()) > 1024 or password != password_confirmation:
        return await application_page(request, session, error="registration_invalid", status_code=422)
    digest = await hash_password_async(password)
    await session.rollback()
    await session.execute(text("BEGIN IMMEDIATE"))
    count = await session.scalar(select(func.count()).select_from(RegistrationRequest)) or 0
    if count >= MAX_PENDING:
        await session.rollback()
        return await application_page(request, session, error="registration_unavailable", status_code=503)
    existing = await session.scalar(select(User.id).where(User.username == username))
    pending = await session.scalar(select(RegistrationRequest.id).where(RegistrationRequest.username == username))
    # Do not reveal whether the conflict is an account or an application.
    if existing is not None or pending is not None:
        await session.rollback()
        request.session.pop("registration_submitted", None)
        return await application_page(request, session, error="registration_username_unavailable", status_code=409)
    session.add(RegistrationRequest(username=username, password_hash=digest))
    add_event(session, "create", "users", "Registration application received", actor="anonymous")
    await session.commit()
    request.session["registration_submitted"] = True
    return RedirectResponse("/register?received=true", status_code=303)


@router.get("/admin/registrations", dependencies=[Depends(require_admin)])
async def requests(request: Request, page: int = Query(1, ge=1), session: AsyncSession = Depends(get_db)) -> Response:
    if request.state.admin_role not in {"admin", "manager"}:
        raise HTTPException(403)
    total = await session.scalar(select(func.count()).select_from(RegistrationRequest)) or 0
    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    if page > total_pages:
        return RedirectResponse(f"/admin/registrations?page={total_pages}", status_code=303)
    rows = (await session.scalars(select(RegistrationRequest).order_by(RegistrationRequest.created_at, RegistrationRequest.id)
                                  .offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE))).all()
    return templates.TemplateResponse(request=request, name="admin/registrations.html", context={
        "applicants": rows, "page": page, "pages": total_pages,
        "admin_user": request.state.admin_user,
        "flash_message": request.session.pop("flash_message", None),
        "flash_type": request.session.pop("flash_type", "success"),
    })


@router.post("/admin/registrations/{request_id}", dependencies=[Depends(require_admin)])
async def review(request_id: int, request: Request, action: str = Form(...), current_password: str = Form(...),
                 session: AsyncSession = Depends(get_db)) -> Response:
    role = request.state.admin_role
    if role not in {"admin", "manager"} or action not in {"approve", "reject"}:
        raise HTTPException(403)
    require_secure_password_transport(request)
    if not await _confirm_password(request, session, current_password):
        request.session["flash_message"] = translate(request, "wrong_current_password")
        request.session["flash_type"] = "error"
        return RedirectResponse("/admin/registrations", status_code=303)
    await _lock_actor(request, session, role)
    applicant = await session.get(RegistrationRequest, request_id)
    if applicant is None:
        raise HTTPException(404)
    key = "registration_rejected"
    if action == "approve":
        if await session.scalar(select(User.id).where(User.username == applicant.username)) is not None:
            await session.rollback()
            request.session["flash_message"] = translate(request, "registration_conflict")
            request.session["flash_type"] = "error"
            return RedirectResponse("/admin/registrations", status_code=303)
        session.add(User(username=applicant.username, password_hash=applicant.password_hash, role="editor", is_verified=False))
        key = "registration_approved"
    add_event(session, "create" if action == "approve" else "delete", "users", "Registration approved" if action == "approve" else "Registration rejected",
              changes={"username": [None, applicant.username]}, actor=request.state.admin_user)
    await session.delete(applicant)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        key = "registration_conflict"
    request.session["flash_message"] = translate(request, key)
    request.session["flash_type"] = "error" if key == "registration_conflict" else "success"
    return RedirectResponse("/admin/registrations", status_code=303)

"""Global sign-in with rate-limited, CSRF-protected staff authentication."""

import logging

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.audit import add_event
from app.config import settings
from app.database import get_db
from app.dependencies import (
    SESSION_COOKIE, DUMMY_PASSWORD_HASH, create_admin_session_token,
    get_request_ip, hash_password_async, verify_password_async,
)
from app.i18n import translate
from app.models import User
from app.security import clear_successful_attempt, require_csrf, reserve_login_attempt, require_secure_password_transport
from app.templating import templates

logger = logging.getLogger(__name__)
router = APIRouter(tags=["authentication"], dependencies=[Depends(require_csrf)])


@router.get("/login", name="login")
async def login_get(request: Request) -> Response:
    return templates.TemplateResponse(request=request, name="admin/login.html", context={"request": request})


@router.post("/login", name="login_post")
async def login_post(
    request: Request,
    session: AsyncSession = Depends(get_db),
    username: str = Form(...),
    password: str = Form(...),
) -> Response:
    require_secure_password_transport(request)
    ip = get_request_ip(request)
    try:
        attempt_id = await reserve_login_attempt(session, ip)
    except HTTPException as exc:
        if exc.status_code == 429:
            add_event(session, "error", "login", "Login attempt limit reached",
                      actor="anonymous", level="critical")
            await session.commit()
            logger.warning("Login attempt limit reached")
        raise
    site_settings = await crud.get_site_settings(session)
    user = await session.scalar(select(User).where(User.username == username, User.is_active.is_(True), User.deleted_at.is_(None)))
    # Always perform a memory-hard check, including for unknown accounts.
    effective_hash = user.password_hash if user else DUMMY_PASSWORD_HASH
    password_valid = await verify_password_async(password, effective_hash)
    if user is None or not password_valid:
        logger.warning("Failed staff login attempt")
        add_event(session, "error", "login", "Failed staff login attempt", actor="anonymous", level="critical")
        await session.commit()
        return templates.TemplateResponse(
            request=request, name="admin/login.html",
            context={"request": request, "error": translate(request, "invalid_credentials")},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    if not user.password_hash.startswith("scrypt$"):
        user.password_hash = await hash_password_async(password)
        await session.commit()
    await clear_successful_attempt(session, attempt_id)
    request.session.clear()
    add_event(session, "login", "login", "Staff session opened", actor=username)
    await session.commit()
    token = create_admin_session_token(user.username, user.password_hash, site_settings.session_generation, user_id=user.id)
    response = RedirectResponse("/admin", status_code=302)
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=max(1, site_settings.session_max_age_minutes) * 60,
        httponly=True,
        samesite="strict",
        secure=settings.app_base_url.startswith("https://"),
    )
    logger.info("Staff login succeeded: user_id=%d", user.id)
    return response



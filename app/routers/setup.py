"""Sunucu sahibi doğrulamalı kurulum ve iki aşamalı veri sıfırlama."""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
import time

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app import crud
from app.config import settings
from app.database import get_db
from app.dependencies import (SESSION_COOKIE, credential_stamp, get_request_ip,
                              hash_admin_password, require_admin, verify_admin_password)
from app.i18n import translate
from app.lifecycle import get_lifecycle, reset_site, reset_storage_roots
from app.models import Download, MediaAsset, MenuItem
from app.security import require_csrf, reserve_login_attempt, clear_successful_attempt
from app.seo import inspect_public_base_url
from app.setup_schemas import InstallationForm, ResetAuthorization, ResetConfirmation
from app.templating import refresh_site_branding_globals, templates

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_csrf)])
MAINTENANCE_PATH = "/admin/settings/maintenance"
CONFIRM_SECONDS = 5 * 60


def setup_available() -> bool:
    return len(settings.setup_token) >= 32


def deployment_checks(request: Request) -> list[tuple[str, bool]]:
    _, status, _ = inspect_public_base_url()
    local = status == "info"
    try:
        roots = reset_storage_roots()
        writable = all(os.access(root if root.exists() else root.parent, os.W_OK) for root in roots)
    except ValueError:
        writable = False
    return [
        ("setup_key_ready", setup_available()),
        ("setup_domain_ready", status in {"ok", "info"}),
        ("setup_https_ready", local or request.url.scheme == "https"),
        ("setup_debug_ready", local or not settings.debug),
        ("setup_storage_ready", writable),
    ]


def setup_page(request: Request, error: str | None = None, status_code: int = 200):
    language = request.query_params.get("lang", "tr")
    request.state.ui_language = language if language in {"tr", "en"} else "tr"
    return templates.TemplateResponse(request=request, name="setup.html", context={
        "public_url": settings.app_base_url, "checks": deployment_checks(request),
        "error": translate(request, error) if error else None,
    }, status_code=status_code)


@router.get("/setup")
async def installation(request: Request, session: AsyncSession = Depends(get_db)):
    if (await get_lifecycle(session)).installed:
        return RedirectResponse("/admin/login", status_code=303)
    return setup_page(request)


@router.post("/setup")
async def install(request: Request, session: AsyncSession = Depends(get_db)):
    state = await get_lifecycle(session)
    if state.installed:
        return RedirectResponse("/admin/login", status_code=303)
    await session.rollback()
    attempt = await reserve_login_attempt(session, "setup:" + get_request_ip(request))
    form = await request.form()
    supplied = str(form.get("setup_token", ""))
    if not setup_available() or not secrets.compare_digest(supplied.encode(), settings.setup_token.encode()):
        return setup_page(request, "setup_key_invalid", 403)
    if not all(ok for _, ok in deployment_checks(request)):
        return setup_page(request, "setup_checks_failed", 422)
    try:
        data = InstallationForm.model_validate(dict(form))
    except ValidationError:
        return setup_page(request, "setup_invalid", 422)
    password_hash = await run_in_threadpool(hash_admin_password, data.password)
    state = await get_lifecycle(session)
    account = await crud.get_site_settings(session)
    account.site_name = data.site_name
    account.site_language = data.language
    account.admin_username = data.username
    account.admin_password_hash = password_hash
    account.session_generation = secrets.token_hex(32)
    # Eski başlangıç migration'ının örnek menüsü yeni kurulumda kalmasın.
    await session.execute(delete(MenuItem))
    state.installed = True
    await session.commit()
    await clear_successful_attempt(session, attempt)
    refresh_site_branding_globals(account)
    request.session.clear()
    response = RedirectResponse("/admin/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    logger.info("Site kurulumu tamamlandı")
    return response


async def maintenance_page(request: Request, session: AsyncSession, error: str | None = None,
                           status_code: int = 200, challenge: dict | None = None):
    account = await crud.get_site_settings(session)
    return templates.TemplateResponse(request=request, name="admin/settings_maintenance.html", context={
        "site_settings": account, "public_url": settings.app_base_url,
        "admin_user": account.admin_username or settings.admin_username,
        "content_count": await session.scalar(select(func.count()).select_from(Download)),
        "media_count": await session.scalar(select(func.count()).select_from(MediaAsset)),
        "error": translate(request, error) if error else None,
        "challenge": challenge, "can_uninstall": setup_available(),
    }, status_code=status_code)


@router.get(MAINTENANCE_PATH)
async def maintenance(request: Request, session: AsyncSession = Depends(get_db),
                      _admin: str = Depends(require_admin)):
    request.session.pop("reset_challenge", None)
    return await maintenance_page(request, session)


@router.post(MAINTENANCE_PATH + "/authorize")
async def authorize_reset(request: Request, session: AsyncSession = Depends(get_db),
                          _admin: str = Depends(require_admin)):
    request.session.pop("reset_challenge", None)
    await session.rollback()
    attempt = await reserve_login_attempt(session, "reset:" + get_request_ip(request))
    try:
        data = ResetAuthorization.model_validate(dict(await request.form()))
    except ValidationError:
        return await maintenance_page(request, session, "reset_invalid", 422)
    account = await crud.get_site_settings(session)
    password_hash = account.admin_password_hash or settings.admin_password_hash
    if not await run_in_threadpool(verify_admin_password, data.password, password_hash):
        logger.warning("Sıfırlama için parola doğrulanamadı")
        return await maintenance_page(request, session, "wrong_current_password", 403)
    if data.action == "uninstall" and not setup_available():
        return await maintenance_page(request, session, "reset_key_required", 422)
    if data.action != "settings":
        try:
            reset_storage_roots()
        except ValueError:
            return await maintenance_page(request, session, "reset_storage_unsafe", 422)
    await clear_successful_attempt(session, attempt)
    challenge = {
        "action": data.action, "site_name": account.site_name,
        "stamp": credential_stamp(_admin, password_hash),
        "generation": account.session_generation,
        "expires": int(time.time()) + CONFIRM_SECONDS, "nonce": secrets.token_urlsafe(32),
        "session": hashlib.sha256(request.cookies.get(SESSION_COOKIE, "").encode()).hexdigest(),
    }
    request.session["reset_challenge"] = challenge
    return await maintenance_page(request, session, challenge=challenge)


@router.post(MAINTENANCE_PATH + "/confirm")
async def confirm_reset(request: Request, session: AsyncSession = Depends(get_db),
                        _admin: str = Depends(require_admin)):
    challenge = request.session.pop("reset_challenge", None)
    try:
        data = ResetConfirmation.model_validate(dict(await request.form()))
    except ValidationError:
        return await maintenance_page(request, session, "reset_invalid", 422)
    account = await crud.get_site_settings(session)
    password_hash = account.admin_password_hash or settings.admin_password_hash
    if not challenge or (
        challenge.get("expires", 0) < time.time()
        or challenge.get("action") not in {"settings", "full", "uninstall"}
        or challenge.get("site_name") != account.site_name
        or challenge.get("stamp") != credential_stamp(_admin, password_hash)
        or challenge.get("generation") != account.session_generation
        or challenge.get("session") != hashlib.sha256(request.cookies.get(SESSION_COOKIE, "").encode()).hexdigest()
        or not secrets.compare_digest(data.nonce.encode(), challenge.get("nonce", "").encode())
        or data.confirmation != account.site_name
    ):
        return await maintenance_page(request, session, "reset_confirmation_failed", 403)
    action = challenge["action"]
    if action == "uninstall" and not setup_available():
        return await maintenance_page(request, session, "reset_key_required", 422)
    try:
        fresh = await reset_site(session, action)
    except (OSError, ValueError):
        await session.rollback()
        logger.exception("Sıfırlama tamamlanamadı; veri temizliği durumu korunuyor")
        return await maintenance_page(request, session, "reset_failed", 503)
    refresh_site_branding_globals(fresh)
    if action != "settings":
        from app.routers.admin import _icon_fetch_progress
        _icon_fetch_progress.clear()
    request.session.clear()
    response = RedirectResponse("/setup" if action == "uninstall" else "/admin/login?reset=done", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    logger.info("Site bakım işlemi tamamlandı: %s", action)
    return response

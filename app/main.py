"""
FastAPI uygulama fabrikası.
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exception_handlers import http_exception_handler
from starlette.exceptions import HTTPException
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app import crud
from app.audit import add_event
from app.config import settings
from app.database import AsyncSessionLocal, engine
from app.i18n import translate, system_message
from app.routers import admin, pages, public, reports, setup, users
from app.lifecycle import LifecycleMiddleware, finish_pending_reset, single_worker_guard, reset_storage_roots
from app.storage import migrate_legacy_local_downloads
from app.security import SecurityHeadersMiddleware
from app.templating import refresh_site_branding_globals, templates

# ---------------------------------------------------------------------------
# Logging yapılandırması
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)
_recent_public_errors: dict[tuple[str, int], float] = {}


async def _record_public_error(request: Request, code: int, error_type: str = "") -> None:
    """Bound anonymous diagnostics without storing URLs, addresses, or request bodies."""
    route = request.scope.get("route")
    pattern = getattr(route, "path", "<unmatched>")
    if pattern.startswith("/static/"):
        return
    key = (f"{request.method} {pattern}", code)
    now = time.monotonic()
    if code != 500 and now - _recent_public_errors.get(key, 0) < 300:
        return
    if len(_recent_public_errors) > 100:
        _recent_public_errors.clear()
    _recent_public_errors[key] = now
    try:
        async with AsyncSessionLocal() as session:
            add_event(session, "error", "request", f"{key[0]} → {code}",
                      changes={"status": [None, code], "error_type": [None, error_type or "HTTPError"]},
                      actor="anonymous", level="error")
            await session.commit()
    except Exception:
        logger.exception("Anonymous error event could not be recorded")


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    with single_worker_guard():
        reset_storage_roots()
        settings.upload_path
        settings.download_path
        async with AsyncSessionLocal() as session:
            await finish_pending_reset(session)
            migrated = await migrate_legacy_local_downloads(session)
            if migrated:
                logger.info("%d eski yerel indirme özel depoya taşındı", migrated)
            site_settings = await crud.get_site_settings(session)
            refresh_site_branding_globals(site_settings)
        logger.info("✅ %s başlatıldı", settings.app_name)
        try:
            yield
        finally:
            await engine.dispose()
            logger.info("⛔ Uygulama kapatıldı.")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title=settings.app_name,
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.app_secret_key,
    session_cookie="session",
    max_age=60 * 60 * 8,
    same_site="lax",
    https_only=settings.app_base_url.startswith("https://"),
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.add_middleware(LifecycleMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.include_router(setup.router)
app.include_router(public.router)
app.include_router(pages.public_router)
app.include_router(admin.router)
app.include_router(pages.admin_router)
app.include_router(reports.router)
app.include_router(users.router)


# ---------------------------------------------------------------------------
# Hata işleyicileri
# ---------------------------------------------------------------------------
@app.exception_handler(HTTPException)
async def localized_http_error(request: Request, exc: HTTPException):
    detail = exc.detail
    if isinstance(detail, str):
        detail = system_message(request, detail)
    elif isinstance(detail, dict) and isinstance(detail.get("message"), str):
        detail = {**detail, "message": system_message(request, detail["message"])}
    return await http_exception_handler(
        request, HTTPException(exc.status_code, detail=detail, headers=exc.headers)
    )


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    await _record_public_error(request, 404)
    return templates.TemplateResponse(
        request=request, name="errors/404.html",
        context={
            "request": request,
            "page_title": translate(request, "not_found"),
            "meta_description": translate(request, "not_found_text"),
            "sidebar_categories": [],
            "sidebar_tags": [],
            "category_counts": {},
            "current_category": None,
            "current_search": None,
        },
        status_code=status.HTTP_404_NOT_FOUND,
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(500)
async def server_error_handler(request: Request, exc):
    logger.error("Unhandled request error: %s", type(exc).__name__, exc_info=exc)
    await _record_public_error(request, 500, type(exc).__name__)
    return templates.TemplateResponse(
        request=request, name="errors/500.html",
        context={
            "request": request,
            "page_title": translate(request, "server_error"),
            "meta_description": translate(request, "server_error_text"),
            "sidebar_categories": [],
            "sidebar_tags": [],
            "category_counts": {},
            "current_category": None,
            "current_search": None,
        },
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


@app.exception_handler(429)
async def rate_limit_handler(request: Request, exc):
    if request.url.path == "/admin/login":
        return templates.TemplateResponse(
            request=request, name="admin/login.html",
            context={"request": request, "error": translate(request, "login_rate_limited")},
            status_code=429, headers=getattr(exc, "headers", None),
        )
    return templates.TemplateResponse(
        request=request, name="errors/429.html",
        context={
            "request": request,
            "page_title": translate(request, "too_many"),
            "meta_description": translate(request, "limit_reached"),
            "sidebar_categories": [],
            "sidebar_tags": [],
            "category_counts": {},
            "current_category": None,
            "current_search": None,
        },
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
    )

"""CSRF protection, anonymous client quotas, and security headers."""

import hashlib
import hmac
import secrets
import ipaddress
from pathlib import PurePosixPath
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import LoginAttempt
from app.config import settings
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Scope, Receive, Send, Message

LOGIN_LIMIT = 5
LOGIN_WINDOW_SECONDS = 15 * 60


def require_secure_password_transport(request: Request) -> None:
    """Allow HTTPS; unencrypted password submission is local-development only."""
    if request.url.scheme == "https":
        return
    try:
        address = ipaddress.ip_address(request.client.host if request.client else "")
        if address.is_loopback:
            return
    except ValueError:
        pass
    from app.i18n import translate
    raise HTTPException(400, detail=translate(request, "registration_https_required"))


def client_key(address: str, *, context: str = "client") -> str:
    """Stable keyed digest for quotas; never persist a raw network address."""
    return hmac.new(settings.app_secret_key.encode(), f"{context}\0{address}".encode(), hashlib.sha256).hexdigest()


class SecurityHeadersMiddleware:
    """Akış/parçalı yüklemeleri sarmalayan ek görevler oluşturmadan başlık ekle."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def secure_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Content-Type-Options"] = "nosniff"
                headers["X-Frame-Options"] = "DENY"
                if "referrer-policy" not in headers:
                    headers["Referrer-Policy"] = "same-origin"
                path = scope["path"]
                if path.startswith(("/panel", "/setup")) or path in {"/login", "/register"}:
                    headers["Cache-Control"] = "no-store"
                    headers["X-Robots-Tag"] = "noindex, nofollow"
                if path.startswith("/static/uploads/") and PurePosixPath(path).suffix.lower() in {
                    ".css", ".htm", ".html", ".js", ".mjs", ".svg", ".svgz", ".xhtml", ".xml",
                }:
                    headers["Content-Disposition"] = "attachment"
                    headers["Content-Security-Policy"] = "sandbox; default-src 'none'"
                if settings.app_base_url.startswith("https://"):
                    headers["Strict-Transport-Security"] = "max-age=31536000"
            await send(message)

        await self.app(scope, receive, secure_send)


def csrf_token(request: Request) -> str:
    if "session" not in request.scope:
        return ""
    if "csrf_token" not in request.session:
        request.session["csrf_token"] = secrets.token_urlsafe(32)
    return request.session["csrf_token"]


async def require_csrf(request: Request) -> None:
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    expected = request.session.get("csrf_token")
    submitted = request.headers.get("x-csrf-token")
    if submitted is None:
        content_type = request.headers.get("content-type", "")
        if content_type.startswith(("application/x-www-form-urlencoded", "multipart/form-data")):
            submitted = (await request.form()).get("csrf_token")
    if not expected or not isinstance(submitted, str) or not secrets.compare_digest(expected, submitted):
        from app.i18n import translate
        raise HTTPException(status_code=403, detail=translate(request, "csrf_failed"))


async def reserve_login_attempt(session: AsyncSession, ip: str) -> int:
    """Denemeyi parola kontrolünden önce sayar; eşzamanlı worker'lar kotayı paylaşır."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=LOGIN_WINDOW_SECONDS)
    key = client_key(ip, context="login")
    # Bu işlem login rotasının ilk DB işlemidir. Yazma kilidi, sayım ve
    # eklemeyi tek bir SQLite işlemi içinde seri hale getirir.
    await session.execute(text("BEGIN IMMEDIATE"))
    await session.execute(delete(LoginAttempt).where(LoginAttempt.attempted_at < cutoff))
    count = await session.scalar(select(func.count()).select_from(LoginAttempt).where(LoginAttempt.client_key == key))
    if count >= LOGIN_LIMIT:
        oldest = await session.scalar(select(func.min(LoginAttempt.attempted_at)).where(LoginAttempt.client_key == key))
        await session.rollback()
        if oldest.tzinfo is None:
            oldest = oldest.replace(tzinfo=timezone.utc)
        # Zaman yuvarlaması pencerenin tam başında 901 üretmesin.
        retry = min(LOGIN_WINDOW_SECONDS, max(1, int((oldest + timedelta(seconds=LOGIN_WINDOW_SECONDS) - now).total_seconds()) + 1))
        raise HTTPException(status_code=429, detail="Çok fazla giriş denemesi. Daha sonra tekrar deneyin.", headers={"Retry-After": str(retry)})
    attempt = LoginAttempt(client_key=key, attempted_at=now)
    session.add(attempt)
    await session.commit()
    return attempt.id


async def clear_successful_attempt(session: AsyncSession, attempt_id: int) -> None:
    await session.execute(delete(LoginAttempt).where(LoginAttempt.id == attempt_id))
    await session.commit()

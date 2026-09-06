"""Oturuma bağlı CSRF doğrulaması ve SQLite üzerinde giriş denemesi sınırı."""

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import LoginAttempt

LOGIN_LIMIT = 5
LOGIN_WINDOW_SECONDS = 15 * 60


def csrf_token(request: Request) -> str:
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
        raise HTTPException(status_code=403, detail="Güvenlik doğrulaması başarısız. Sayfayı yenileyip tekrar deneyin.")


async def reserve_login_attempt(session: AsyncSession, ip: str) -> int:
    """Denemeyi parola kontrolünden önce sayar; eşzamanlı worker'lar kotayı paylaşır."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=LOGIN_WINDOW_SECONDS)
    # Bu işlem login rotasının ilk DB işlemidir. Yazma kilidi, sayım ve
    # eklemeyi tek bir SQLite işlemi içinde seri hale getirir.
    await session.execute(text("BEGIN IMMEDIATE"))
    await session.execute(delete(LoginAttempt).where(LoginAttempt.attempted_at < cutoff))
    count = await session.scalar(select(func.count()).select_from(LoginAttempt).where(LoginAttempt.ip_address == ip))
    if count >= LOGIN_LIMIT:
        oldest = await session.scalar(select(func.min(LoginAttempt.attempted_at)).where(LoginAttempt.ip_address == ip))
        await session.rollback()
        if oldest.tzinfo is None:
            oldest = oldest.replace(tzinfo=timezone.utc)
        # Zaman yuvarlaması pencerenin tam başında 901 üretmesin.
        retry = min(LOGIN_WINDOW_SECONDS, max(1, int((oldest + timedelta(seconds=LOGIN_WINDOW_SECONDS) - now).total_seconds()) + 1))
        raise HTTPException(status_code=429, detail="Çok fazla giriş denemesi. Daha sonra tekrar deneyin.", headers={"Retry-After": str(retry)})
    attempt = LoginAttempt(ip_address=ip, attempted_at=now)
    session.add(attempt)
    await session.commit()
    return attempt.id


async def clear_successful_attempt(session: AsyncSession, attempt_id: int) -> None:
    await session.execute(delete(LoginAttempt).where(LoginAttempt.id == attempt_id))
    await session.commit()

"""
FastAPI bağımlılıkları (Dependencies).

- get_db          : Async DB session (database.py'den yeniden ihraç)
- get_request_ip  : İstemci IP'sini güvenli şekilde okur
- require_admin   : Admin oturumu doğrulaması
"""

from __future__ import annotations

import logging
from typing import Optional

import bcrypt
from fastapi import Cookie, Depends, HTTPException, Request, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db  # noqa: F401 — re-export

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Session imzalama
# ---------------------------------------------------------------------------
_serializer = URLSafeTimedSerializer(settings.app_secret_key)
SESSION_COOKIE = "admin_session"
SESSION_MAX_AGE = 60 * 60 * 8  # 8 saat


def create_admin_session_token(username: str) -> str:
    return _serializer.dumps({"u": username}, salt="admin-session")


def verify_admin_session_token(token: str) -> Optional[str]:
    """
    Geçerli token → username döndürür.
    Geçersiz/süresi dolmuş → None.
    """
    try:
        data = _serializer.loads(token, salt="admin-session", max_age=SESSION_MAX_AGE)
        return data.get("u")
    except (BadSignature, SignatureExpired):
        return None


# ---------------------------------------------------------------------------
# Admin kimlik doğrulama
# ---------------------------------------------------------------------------
def verify_admin_password(plain: str) -> bool:
    """
    .env'deki ADMIN_PASSWORD_HASH ile verilen plain şifreyi karşılaştırır.
    Hash yoksa (placeholder) her zaman False döner.
    """
    stored_hash = settings.admin_password_hash.strip()
    if not stored_hash or "placeholder" in stored_hash:
        logger.warning(
            "ADMIN_PASSWORD_HASH .env'de ayarlanmamış! Admin girişi devre dışı."
        )
        return False
    try:
        return bcrypt.checkpw(plain.encode(), stored_hash.encode())
    except Exception as exc:
        logger.error("bcrypt doğrulama hatası: %s", exc)
        return False


async def require_admin(
    request: Request,
    admin_session: Optional[str] = Cookie(None, alias=SESSION_COOKIE),
) -> str:
    """
    Admin oturumu zorunlu kılan bağımlılık.
    Geçersiz oturumda login sayfasına yönlendirir.
    """
    if not admin_session:
        raise HTTPException(
            status_code=status.HTTP_302_FOUND,
            headers={"Location": "/admin/login"},
        )
    username = verify_admin_session_token(admin_session)
    if not username:
        raise HTTPException(
            status_code=status.HTTP_302_FOUND,
            headers={"Location": "/admin/login"},
        )
    return username


# ---------------------------------------------------------------------------
# IP adresi çözümleme
# ---------------------------------------------------------------------------
def get_request_ip(request: Request) -> str:
    """
    Proxy arkasındaki gerçek IP'yi döndürür.
    X-Forwarded-For → X-Real-IP → doğrudan bağlantı sırasına göre.
    """
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Virgülle ayrılmış liste — ilk eleman gerçek istemci IP'si
        return forwarded_for.split(",")[0].strip()

    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()

    if request.client:
        return request.client.host

    return "unknown"

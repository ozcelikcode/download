"""
FastAPI bağımlılıkları (Dependencies).

- get_db          : Async DB session (database.py'den yeniden ihraç)
- get_request_ip  : İstemci IP'sini güvenli şekilde okur
- require_admin   : Admin oturumu doğrulaması
"""

from __future__ import annotations

import logging
import hashlib
import hmac
import secrets
from typing import Optional

import bcrypt
from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import settings
from app.database import get_db  # noqa: F401 — re-export
from app.models import SiteSettings
from app import audit  # noqa: F401 — işlem geçmişi olaylarını kaydeder

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Session imzalama
# ---------------------------------------------------------------------------
_serializer = URLSafeTimedSerializer(settings.app_secret_key)
SESSION_COOKIE = "admin_session"


def credential_stamp(username: str, password_hash: str) -> str:
    return hmac.new(settings.app_secret_key.encode(), (username + "\0" + password_hash).encode(), hashlib.sha256).hexdigest()


def create_admin_session_token(username: str, password_hash: str | None = None, generation: str = "") -> str:
    stamp = credential_stamp(username, settings.admin_password_hash if password_hash is None else password_hash)
    return _serializer.dumps({"u": username, "v": stamp, "g": generation, "nonce": secrets.token_urlsafe(16)}, salt="admin-session")


# ---------------------------------------------------------------------------
# Admin kimlik doğrulama
# ---------------------------------------------------------------------------
def verify_admin_password(plain: str, stored_hash: Optional[str] = None) -> bool:
    """
    Verilen plain şifreyi bcrypt hash ile karşılaştırır.
    `stored_hash` verilmezse (ör. eski çağrı yerleri) .env'deki
    ADMIN_PASSWORD_HASH kullanılır. Hash yoksa (placeholder) her zaman False döner.
    """
    effective_hash = (stored_hash or settings.admin_password_hash).strip()
    if not effective_hash or "placeholder" in effective_hash:
        logger.warning(
            "Admin şifre hash'i ayarlanmamış! Admin girişi devre dışı."
        )
        return False
    try:
        if len(plain.encode()) > 1024:
            return False
        if effective_hash.startswith("scrypt$"):
            _, salt, digest = effective_hash.split("$")
            derived = hashlib.scrypt(plain.encode(), salt=bytes.fromhex(salt), n=131072, r=8, p=1, maxmem=256*1024*1024)
            return secrets.compare_digest(derived.hex(), digest)
        if len(plain.encode()) > 72:
            return False
        return bcrypt.checkpw(plain.encode(), effective_hash.encode())
    except (ValueError, TypeError):
        logger.error("Yönetici parola özeti doğrulanamadı")
        return False


def hash_admin_password(plain: str) -> str:
    """Rastgele salt ile bellek maliyetli scrypt parola özeti üretir."""
    if len(plain.encode()) > 1024:
        raise ValueError("Parola çok uzun")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(plain.encode(), salt=salt, n=131072, r=8, p=1, maxmem=256*1024*1024)
    return f"scrypt${salt.hex()}${digest.hex()}"


async def require_admin(
    request: Request,
    admin_session: Optional[str] = Cookie(None, alias=SESSION_COOKIE),
    session: AsyncSession = Depends(get_db),
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
    from app.crud import get_site_settings
    account = await get_site_settings(session)
    username = authenticated_username(admin_session, account)
    if not username:
        raise HTTPException(
            status_code=status.HTTP_302_FOUND,
            headers={"Location": "/admin/login"},
        )
    session.info["audit_actor"] = username
    return username


def authenticated_username(token: str, account: SiteSettings) -> Optional[str]:
    try:
        data = _serializer.loads(token, salt="admin-session", max_age=max(1, account.session_max_age_minutes) * 60)
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(data, dict):
        return None
    username = account.admin_username or settings.admin_username
    password_hash = account.admin_password_hash or settings.admin_password_hash
    if (
        data.get("u") != username
        or not secrets.compare_digest(str(data.get("v", "")), credential_stamp(username, password_hash))
        or not secrets.compare_digest(str(data.get("g", "")), account.session_generation)
    ):
        return None
    return username


def get_optional_admin_username(request: Request, account: SiteSettings) -> Optional[str]:
    """
    `require_admin`'in aksine hiçbir şeyi zorunlu kılmaz — sadece geçerli bir
    admin oturumu varsa kullanıcı adını, yoksa None döndürür. Herkese açık
    sayfalarda (navbar'da admin durumu, indirme sayfasında admin aksiyonları)
    kullanılır. İmza, süre, güncel hesap bilgileri ve oturum kuşağı doğrulanır.
    """
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    return authenticated_username(token, account)


# ---------------------------------------------------------------------------
# IP adresi çözümleme
# ---------------------------------------------------------------------------
def get_request_ip(request: Request) -> str:
    """Uvicorn'un güvenilir proxy kontrolünden geçmiş istemci adresi.

    Ham yönlendirme başlıkları istemci tarafından değiştirilebilir; burada
    tekrar yorumlanmaları indirme kotasının atlatılmasına yol açar.
    """
    if request.client:
        return request.client.host

    return "unknown"

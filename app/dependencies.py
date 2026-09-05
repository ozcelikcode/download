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
from sqlalchemy.ext.asyncio import AsyncSession
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import settings
from app.database import get_db  # noqa: F401 — re-export
from app import audit  # noqa: F401 — işlem geçmişi olaylarını kaydeder

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Session imzalama
# ---------------------------------------------------------------------------
_serializer = URLSafeTimedSerializer(settings.app_secret_key)
SESSION_COOKIE = "admin_session"
# Varsayılan; Ayarlar'dan değiştirilip DB'den yüklenince refresh_session_max_age
# ile güncellenir (bkz. app/main.py lifespan, app/routers/admin.py Ayarlar kaydı).
SESSION_MAX_AGE = 60 * 60 * 8  # 8 saat


def refresh_session_max_age(minutes: int) -> None:
    """Admin oturum süresini (dakika) DB'deki güncel değere göre ayarlar."""
    global SESSION_MAX_AGE
    SESSION_MAX_AGE = max(1, int(minutes)) * 60


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
        return bcrypt.checkpw(plain.encode(), effective_hash.encode())
    except Exception as exc:
        logger.error("bcrypt doğrulama hatası: %s", exc)
        return False


def hash_admin_password(plain: str) -> str:
    """Yeni bir admin şifresini bcrypt ile hash'ler (Ayarlar'dan şifre değişimi için)."""
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


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
    username = verify_admin_session_token(admin_session)
    if not username:
        raise HTTPException(
            status_code=status.HTTP_302_FOUND,
            headers={"Location": "/admin/login"},
        )
    session.info["audit_actor"] = username
    return username


def get_optional_admin_username(request: Request) -> Optional[str]:
    """
    `require_admin`'in aksine hiçbir şeyi zorunlu kılmaz — sadece geçerli bir
    admin oturumu varsa kullanıcı adını, yoksa None döndürür. Herkese açık
    sayfalarda (navbar'da admin durumu, indirme sayfasında admin aksiyonları)
    kullanılır. İmza doğrulaması `verify_admin_session_token` ile aynıdır,
    yalnızca çerez varlığına bakılmaz — sahte/geçersiz çerez admin sayılmaz.
    """
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    return verify_admin_session_token(token)


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

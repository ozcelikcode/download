"""Password-confirmed self closure without deleting owned site data."""

import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import add_event
from app.database import get_db
from app.dependencies import SESSION_COOKIE, require_admin
from app.i18n import translate
from app.models import User
from app.routers.users import _confirm_password, _lock_actor
from app.security import require_csrf, require_secure_password_transport

router = APIRouter(prefix="/panel/account", dependencies=[Depends(require_csrf), Depends(require_admin)])


def denied(request: Request, key: str) -> RedirectResponse:
    request.session["flash_message"] = translate(request, key)
    request.session["flash_type"] = "error"
    return RedirectResponse("/panel/settings/account", status_code=303)


@router.post("/close")
async def close_account(
    request: Request, current_password: str = Form(...),
    confirmation: str = Form(...), acknowledged: bool = Form(False),
    session: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    require_secure_password_transport(request)
    if not acknowledged or confirmation != request.state.admin_user:
        return denied(request, "account_close_confirmation")
    if not await _confirm_password(request, session, current_password):
        return denied(request, "wrong_current_password")
    await _lock_actor(request, session, request.state.admin_role)
    user = await session.get(User, request.state.admin_id)
    if user.role == "admin":
        count = await session.scalar(select(func.count()).select_from(User).where(
            User.role == "admin", User.is_active.is_(True), User.deleted_at.is_(None)))
        if (count or 0) <= 1:
            await session.rollback()
            return denied(request, "last_admin_required")
    # Retain only the identity anchor needed by content foreign keys. User IDs
    # are never reused, so a later signup cannot inherit another user's work.
    user.username = f"closed-{user.id}-{secrets.token_hex(6)}"
    user.password_hash = ""
    user.is_active = False
    user.is_verified = False
    user.deleted_at = datetime.now(timezone.utc)
    user.deletion_requested_by = None
    add_event(session, "delete", "users", "Account closed", user.id, actor="anonymous")
    await session.commit()
    request.session.clear()
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response

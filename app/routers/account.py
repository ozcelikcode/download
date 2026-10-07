"""Private profile photos and password-confirmed account closure."""

import os
import secrets
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import add_event
from app.database import get_db
from app.dependencies import SESSION_COOKIE, require_admin
from app.i18n import translate
from app.models import MediaAsset, User
from app.profile_photos import PHOTO_UPLOAD_LIMIT, valid_profile_icon, photo_path, prepare_photo
from app.storage_quota import publish_media
from app.uploads import save_upload
from app.routers.users import _confirm_password, _lock_actor
from app.security import require_csrf, require_secure_password_transport

router = APIRouter(prefix="/panel/account", dependencies=[Depends(require_csrf), Depends(require_admin)])


def denied(request: Request, key: str) -> RedirectResponse:
    request.session["flash_message"] = translate(request, key)
    request.session["flash_type"] = "error"
    return RedirectResponse("/panel/settings/account", status_code=303)


@router.get("/photo")
async def account_photo(request: Request) -> FileResponse:
    try:
        path = photo_path(request.state.admin_id)
    except ValueError as exc:
        raise HTTPException(404) from exc
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, media_type="image/webp", headers={
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
    })


@router.post("/icon")
async def update_profile_icon(request: Request, icon: str = Form(...),
                              session: AsyncSession = Depends(get_db)) -> RedirectResponse:
    icon = icon.strip()
    if not valid_profile_icon(icon):
        return denied(request, "profile_icon_invalid")
    await _lock_actor(request, session, request.state.admin_role)
    user = await session.get(User, request.state.admin_id)
    user.profile_icon = icon
    add_event(session, "update", "users", "Profile icon updated", user.id)
    await session.commit()
    request.session["flash_message"] = translate(request, "profile_icon_updated")
    return RedirectResponse("/panel/settings/account", status_code=303)


@router.post("/photo")
async def update_photo(request: Request, photo: UploadFile = File(...),
                       session: AsyncSession = Depends(get_db)) -> RedirectResponse:
    try:
        await save_upload(photo, photo_path(request.state.admin_id), validator=prepare_photo,
                          max_bytes=PHOTO_UPLOAD_LIMIT,
                          publisher=lambda staged, target: publish_media(session, staged, target))
    except ValueError:
        return denied(request, "photo_invalid")
    add_event(session, "update", "users", "Profile photo updated", request.state.admin_id)
    await session.commit()
    request.session["flash_message"] = translate(request, "photo_saved")
    request.session["flash_type"] = "success"
    return RedirectResponse("/panel/settings/account", status_code=303)


@router.post("/photo/remove")
async def remove_photo(request: Request, session: AsyncSession = Depends(get_db)) -> RedirectResponse:
    await _lock_actor(request, session, request.state.admin_role)
    try:
        path = photo_path(request.state.admin_id)
    except ValueError:
        await session.rollback()
        return denied(request, "photo_invalid")
    asset = await session.scalar(select(MediaAsset).where(
        MediaAsset.path == f"/static/uploads/icons/.profiles/{request.state.admin_id}.webp",
        MediaAsset.owner_id == request.state.admin_id))
    recovery: Path | None = None
    try:
        if path.is_file():
            fd, name = tempfile.mkstemp(prefix=".replace-", suffix=".part", dir=path.parent)
            os.close(fd)
            recovery = Path(name)
            path.replace(recovery)
        if asset is not None:
            await session.delete(asset)
        add_event(session, "update", "users", "Profile photo removed", request.state.admin_id)
        await session.commit()
    except BaseException:
        await session.rollback()
        if recovery is not None:
            recovery.replace(path)
        raise
    else:
        if recovery is not None:
            recovery.unlink(missing_ok=True)
    request.session["flash_message"] = translate(request, "photo_removed")
    request.session["flash_type"] = "success"
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

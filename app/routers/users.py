"""Staff accounts with explicit role boundaries and reviewed deletions."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import add_event
from app.database import get_db
from app.dependencies import SESSION_COOKIE, authenticated_user, get_request_ip, hash_password_async, require_admin, verify_password_async
from app.i18n import translate
from app.models import User
from app.security import clear_successful_attempt, require_csrf, reserve_login_attempt
from app.templating import templates


router = APIRouter(prefix="/admin/users", dependencies=[Depends(require_csrf), Depends(require_admin)])
USERNAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{2,49}\Z")
ROLES = {"admin", "manager", "editor"}


def _back(request: Request, key: str, *, error: bool = False) -> RedirectResponse:
    request.session["flash_message"] = translate(request, key)
    request.session["flash_type"] = "error" if error else "success"
    return RedirectResponse("/admin/users", status_code=303)


def _forbid(request: Request) -> None:
    if request.state.admin_role != "admin":
        raise HTTPException(403, detail=translate(request, "permission_denied"))


async def _confirm_password(request: Request, session: AsyncSession, password: str) -> bool:
    await session.rollback()
    attempt_id = await reserve_login_attempt(session, f"users:{request.state.admin_id}:{get_request_ip(request)}")
    actor = await session.get(User, request.state.admin_id)
    if actor is None or not await verify_password_async(password, actor.password_hash):
        add_event(session, "error", "users", "Account operation rejected: password mismatch", actor="anonymous", level="critical")
        await session.commit()
        return False
    await clear_successful_attempt(session, attempt_id)
    return True


async def _lock_actor(request: Request, session: AsyncSession, role: str, *, durable: bool = False) -> None:
    """Revalidate the acting account after acquiring the account mutation lock."""
    from app.crud import get_site_settings

    await session.rollback()
    if durable:
        await session.execute(text("PRAGMA synchronous=FULL"))
    await session.execute(text("BEGIN IMMEDIATE"))
    account = await get_site_settings(session)
    actor = await authenticated_user(request.cookies.get(SESSION_COOKIE, ""), account, session)
    if actor is None or actor.role != role:
        await session.rollback()
        raise HTTPException(403, detail=translate(request, "permission_denied"))
    request.state.admin_user = actor.username


@router.get("")
async def list_users(request: Request, session: AsyncSession = Depends(get_db)):
    users = (await session.scalars(select(User).order_by(User.is_active.desc(), User.username))).all()
    return templates.TemplateResponse(request=request, name="admin/users.html", context={
        "request": request, "users": users, "admin_user": request.state.admin_user,
        "staff_role": request.state.admin_role,
        "flash_message": request.session.pop("flash_message", None),
        "flash_type": request.session.pop("flash_type", "success"),
    })


@router.post("")
async def create_user(
    request: Request, session: AsyncSession = Depends(get_db),
    username: str = Form(...), password: str = Form(...), role: str = Form(...),
    current_password: str = Form(...),
):
    _forbid(request)
    username = username.strip()
    if not USERNAME_PATTERN.fullmatch(username) or role not in ROLES or len(password) < 12 or len(password.encode()) > 1024:
        return _back(request, "user_invalid", error=True)
    if not await _confirm_password(request, session, current_password):
        return _back(request, "wrong_current_password", error=True)
    if await session.scalar(select(User.id).where(User.username == username)) is not None:
        return _back(request, "username_taken", error=True)
    digest = await hash_password_async(password)
    await _lock_actor(request, session, "admin")
    user = User(username=username, password_hash=digest, role=role)
    try:
        session.add(user)
        await session.flush()
        add_event(session, "create", "users", username, entity_id=user.id, actor=request.state.admin_user)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return _back(request, "username_taken", error=True)
    return _back(request, "user_created")


@router.post("/{user_id}/role")
async def change_role(
    user_id: int, request: Request, session: AsyncSession = Depends(get_db),
    role: str = Form(...), current_password: str = Form(...),
):
    _forbid(request)
    if role not in ROLES:
        return _back(request, "user_invalid", error=True)
    if not await _confirm_password(request, session, current_password):
        return _back(request, "wrong_current_password", error=True)
    await _lock_actor(request, session, "admin")
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        await session.rollback()
        raise HTTPException(404)
    if user.role == "admin" and role != "admin":
        count = await session.scalar(select(func.count()).select_from(User).where(User.role == "admin", User.is_active.is_(True)))
        if count <= 1:
            await session.rollback()
            return _back(request, "last_admin_required", error=True)
    old_role = user.role
    user.role = role
    if role != old_role:
        user.is_verified = False
    add_event(session, "update", "users", user.username, entity_id=user.id, changes={"role": [old_role, role]}, actor=request.state.admin_user)
    await session.commit()
    return _back(request, "user_updated")


@router.post("/{user_id}/verification")
async def verify_editor(
    user_id: int, request: Request, session: AsyncSession = Depends(get_db),
    current_password: str = Form(...), verified: bool = Form(False),
):
    role = request.state.admin_role
    if role not in {"admin", "manager"}:
        raise HTTPException(403)
    if not await _confirm_password(request, session, current_password):
        return _back(request, "wrong_current_password", error=True)
    await _lock_actor(request, session, role)
    user = await session.get(User, user_id)
    if user is None or not user.is_active or user.role != "editor":
        raise HTTPException(404)
    old = user.is_verified
    user.is_verified = verified
    add_event(session, "update", "users", "Editor verification updated", user.id,
              {"is_verified": [old, verified]}, actor=request.state.admin_user)
    await session.commit()
    return _back(request, "verification_saved")


@router.post("/{user_id}/request-delete")
async def request_delete(user_id: int, request: Request, session: AsyncSession = Depends(get_db)):
    if request.state.admin_role != "manager":
        raise HTTPException(403, detail=translate(request, "permission_denied"))
    await _lock_actor(request, session, "manager")
    user = await session.get(User, user_id)
    if user is None or not user.is_active or user.role != "editor":
        await session.rollback()
        raise HTTPException(403, detail=translate(request, "permission_denied"))
    if user.deletion_requested_by is not None:
        await session.rollback()
        return _back(request, "user_already_pending", error=True)
    user.deletion_requested_by = request.state.admin_id
    add_event(session, "update", "users", user.username, entity_id=user.id, changes={"status": ["active", "pending"]}, actor=request.state.admin_user)
    await session.commit()
    return _back(request, "user_delete_requested")


@router.post("/{user_id}/delete")
async def delete_user(
    user_id: int, request: Request, session: AsyncSession = Depends(get_db),
    current_password: str = Form(...),
):
    _forbid(request)
    if not await _confirm_password(request, session, current_password):
        return _back(request, "wrong_current_password", error=True)
    await _lock_actor(request, session, "admin")
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        await session.rollback()
        raise HTTPException(404)
    if user.role == "admin":
        count = await session.scalar(select(func.count()).select_from(User).where(User.role == "admin", User.is_active.is_(True)))
        if count <= 1:
            await session.rollback()
            return _back(request, "last_admin_required", error=True)
    user.is_active = False
    user.deleted_at = datetime.now(timezone.utc)
    user.deletion_requested_by = None
    add_event(session, "delete", "users", user.username, entity_id=user.id, actor=request.state.admin_user)
    await session.commit()
    return _back(request, "user_deleted")


@router.post("/{user_id}/reject-delete")
async def reject_delete(user_id: int, request: Request, session: AsyncSession = Depends(get_db)):
    _forbid(request)
    await _lock_actor(request, session, "admin")
    user = await session.get(User, user_id)
    if user is None or user.deletion_requested_by is None or not user.is_active:
        raise HTTPException(404)
    user.deletion_requested_by = None
    add_event(session, "update", "users", user.username, entity_id=user.id, changes={"status": ["pending", "active"]}, actor=request.state.admin_user)
    await session.commit()
    return _back(request, "user_delete_rejected")

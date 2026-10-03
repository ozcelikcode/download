"""Administrator-only encrypted backups and bounded, reviewed imports."""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app import backups, crud, maintenance_jobs
from app.audit import add_event
from app.backup_restore import restore_site
from app.config import settings
from app.database import get_db
from app.dependencies import SESSION_COOKIE, require_admin
from app.i18n import translate
from app.models import BackupPolicy, User
from app.routers.users import _confirm_password, _lock_actor
from app.security import require_csrf
from app.templating import templates, refresh_site_branding_globals
from app.trash_retention import RETENTION_DAYS

router = APIRouter(prefix="/admin", dependencies=[Depends(require_csrf), Depends(require_admin)])
logger = logging.getLogger(__name__)


def admin_only(request: Request) -> None:
    if request.state.admin_role != "admin":
        raise HTTPException(403)


def redirect(request: Request, key: str, *, error: bool = False, target: str = "/admin/backups"):
    request.session["flash_message"] = translate(request, key)
    request.session["flash_type"] = "error" if error else "success"
    return RedirectResponse(target, status_code=303)


async def authorize(request: Request, session: AsyncSession, password: str, *, durable: bool = False) -> bool:
    admin_only(request)
    if not await _confirm_password(request, session, password):
        return False
    await _lock_actor(request, session, "admin", durable=durable)
    return True


def signer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.app_secret_key, salt="backup-import-v1")


def file_digest(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


async def review_stage(request: Request, session: AsyncSession, token: str) -> Path:
    try:
        payload = signer().loads(token, max_age=900)
        account = await crud.get_site_settings(session)
        if payload["actor"] != request.state.admin_id or payload["generation"] != account.session_generation:
            raise backups.BackupError("backup_missing")
        stage = backups.stage_path(payload["stage"])
        digest = await run_in_threadpool(file_digest, stage / "incoming.zip")
        if digest != payload["digest"]:
            raise backups.BackupError("backup_invalid")
        return stage
    except (BadSignature, KeyError, TypeError, OSError) as exc:
        raise backups.BackupError("backup_missing") from exc


@router.get("/backups")
async def backup_page(request: Request, stage: str = "", session: AsyncSession = Depends(get_db)):
    admin_only(request)
    policy = await session.get(BackupPolicy, 1)
    account = await crud.get_site_settings(session)
    preview = None
    if stage:
        try:
            directory = await review_stage(request, session, stage)
            manifest, data = await run_in_threadpool(backups.validate_archive, directory)
            preview = {"token": stage, "manifest": manifest, "contents": len(data["downloads"]), "users": len(data["users"])}
        except backups.BackupError as exc:
            request.session["flash_message"] = translate(request, str(exc))
            request.session["flash_type"] = "error"
    files = await run_in_threadpool(backups.list_backups)
    return templates.TemplateResponse(request=request, name="admin/backups.html", context={
        "admin_user": request.state.admin_user, "policy": policy, "site_settings": account,
        "backups": [{"name": f.name, "bytes": f.stat().st_size} for f in files],
        "intervals": backups.INTERVALS, "preview": preview, "size_limit": backups.size_limit(),
        "flash_message": request.session.pop("flash_message", None),
        "flash_type": request.session.pop("flash_type", "success"),
    })


@router.post("/backups/key")
async def configure_key(request: Request, public_key: str = Form(...), current_password: str = Form(...),
                        recovery_saved: bool = Form(False), session: AsyncSession = Depends(get_db)):
    if not await authorize(request, session, current_password):
        return redirect(request, "wrong_current_password", error=True)
    policy = await session.get(BackupPolicy, 1)
    if not recovery_saved or (policy and policy.public_key):
        return redirect(request, "backup_invalid", error=True)
    try:
        backups.public_key(public_key)
    except backups.BackupError as exc:
        return redirect(request, str(exc), error=True)
    policy = policy or BackupPolicy(id=1)
    policy.public_key = public_key
    session.add(policy)
    add_event(session, "update", "settings", "Backup recovery public key configured", actor=request.state.admin_user)
    await session.commit()
    return redirect(request, "backup_saved")


@router.post("/backups/schedule")
async def schedule(request: Request, interval_days: int = Form(...), enabled: bool = Form(False),
                   current_password: str = Form(...), session: AsyncSession = Depends(get_db)):
    if not await authorize(request, session, current_password):
        return redirect(request, "wrong_current_password", error=True)
    policy = await session.get(BackupPolicy, 1)
    if not policy or not policy.public_key:
        return redirect(request, "backup_key_required", error=True)
    if interval_days not in backups.INTERVALS:
        return redirect(request, "backup_invalid", error=True)
    policy.interval_days, policy.enabled = interval_days, enabled
    add_event(session, "update", "settings", "Backup schedule updated", changes={"interval_days": [None, interval_days], "enabled": [None, enabled]}, actor=request.state.admin_user)
    await session.commit()
    maintenance_jobs.wake.set()
    return redirect(request, "backup_saved")


@router.post("/backups/manual")
async def manual(request: Request, current_password: str = Form(...), session: AsyncSession = Depends(get_db)):
    if not await authorize(request, session, current_password):
        return redirect(request, "wrong_current_password", error=True)
    policy = await session.get(BackupPolicy, 1)
    if not policy or not policy.public_key:
        return redirect(request, "backup_key_required", error=True)
    policy.requested = True
    add_event(session, "create", "settings", "Manual encrypted backup requested", actor=request.state.admin_user)
    await session.commit()
    maintenance_jobs.wake.set()
    return redirect(request, "backup_queued")


@router.get("/backups/status")
async def backup_status(request: Request, session: AsyncSession = Depends(get_db)):
    admin_only(request)
    policy = await session.get(BackupPolicy, 1)
    files = await run_in_threadpool(backups.list_backups)
    return JSONResponse({"requested": bool(policy and policy.requested), "latest": files[0].name if files else None,
                         "error": bool(policy and policy.error_code)}, headers={"Cache-Control": "no-store"})


@router.get("/backups/download/{name}")
async def download(request: Request, name: str):
    admin_only(request)
    files = await run_in_threadpool(backups.list_backups)
    found = next((f for f in files if f.name == name), None)
    if found is None:
        raise HTTPException(404)
    return FileResponse(found, filename=name, media_type="application/octet-stream", headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.post("/backups/delete")
async def delete(request: Request, name: str = Form(...), current_password: str = Form(...),
                 session: AsyncSession = Depends(get_db)):
    if not await authorize(request, session, current_password):
        return redirect(request, "wrong_current_password", error=True)
    try:
        await run_in_threadpool(backups.delete_backup, name)
    except backups.BackupError as exc:
        return redirect(request, str(exc), error=True)
    add_event(session, "purge", "settings", "Historical encrypted backup deleted", actor=request.state.admin_user)
    await session.commit()
    return redirect(request, "backup_deleted")


@router.post("/backups/import")
async def import_backup(request: Request, current_password: str = Form(...), file: UploadFile = File(...),
                        session: AsyncSession = Depends(get_db)):
    admin_only(request)
    stage = None
    try:
        if not await authorize(request, session, current_password):
            return JSONResponse({"error": translate(request, "wrong_current_password")}, status_code=403)
        policy = await session.get(BackupPolicy, 1)
        if not policy or not policy.public_key:
            raise backups.BackupError("backup_key_required")
        account = await crud.get_site_settings(session)
        generation = account.session_generation
        await session.rollback()  # Do not hold a database write lock during a large upload.
        stage = await run_in_threadpool(backups.new_stage)
        size, digest = 0, hashlib.sha256()
        with (stage / "incoming.zip").open("xb") as output:
            os.chmod(output.name, 0o600)
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > backups.size_limit():
                    raise backups.BackupError("backup_too_large")
                digest.update(chunk)
                await run_in_threadpool(output.write, chunk)
        await run_in_threadpool(backups.validate_archive, stage)
        token = signer().dumps({"actor": request.state.admin_id, "generation": generation, "stage": stage.name, "digest": digest.hexdigest()})
        return JSONResponse({"redirect_url": "/admin/backups?stage=" + token})
    except backups.BackupError as exc:
        if stage is not None:
            await run_in_threadpool(backups.remove_stage, stage)
        return JSONResponse({"error": translate(request, str(exc))}, status_code=422)
    except Exception as exc:
        if stage is not None:
            await run_in_threadpool(backups.remove_stage, stage)
        logger.error("Backup import failed: error_type=%s", type(exc).__name__)
        return JSONResponse({"error": translate(request, "backup_failed")}, status_code=503)
    finally:
        await file.close()


@router.post("/backups/restore")
async def restore(request: Request, token: str = Form(...), confirmation: str = Form(...),
                  current_password: str = Form(...), irreversible: bool = Form(False),
                  session: AsyncSession = Depends(get_db)):
    if not await authorize(request, session, current_password, durable=True):
        return redirect(request, "wrong_current_password", error=True)
    account = await crud.get_site_settings(session)
    if not irreversible or confirmation != account.site_name:
        return redirect(request, "reset_confirmation_failed", error=True)
    policy = await session.get(BackupPolicy, 1)
    if not policy or not policy.public_key:
        return redirect(request, "backup_key_required", error=True)
    try:
        stage = await review_stage(request, session, token)
        actor = await session.get(User, request.state.admin_id)
        await run_in_threadpool(backups.create_backup, policy.public_key)
        await restore_site(session, stage, actor)
    except backups.BackupError as exc:
        return redirect(request, str(exc), error=True)
    except Exception as exc:
        logger.error("Backup restore failed: error_type=%s", type(exc).__name__)
        return redirect(request, "backup_failed", error=True)
    session.expunge_all()
    account = await crud.get_site_settings(session)
    refresh_site_branding_globals(account)
    request.session.clear()
    response = RedirectResponse("/admin/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response


@router.post("/settings/maintenance/retention")
async def retention(request: Request, days: int = Form(...), current_password: str = Form(...),
                    session: AsyncSession = Depends(get_db)):
    target = "/admin/settings/maintenance"
    if not await authorize(request, session, current_password):
        return redirect(request, "wrong_current_password", error=True, target=target)
    if days != 0 and days not in RETENTION_DAYS:
        return redirect(request, "backup_invalid", error=True, target=target)
    account = await crud.get_site_settings(session)
    old = account.trash_retention_days
    account.trash_retention_days = days or None
    add_event(session, "update", "settings", "Trash retention updated", changes={"trash_retention_days": [old, days or None]}, actor=request.state.admin_user)
    await session.commit()
    maintenance_jobs.wake.set()
    return redirect(request, "retention_saved", target=target)

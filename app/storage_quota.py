"""Personal storage limits with SQLite-serialized, staged media publication."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from urllib.parse import quote

import anyio
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import credential_stamp
from app.media import media_path
from app.models import MediaAsset, SiteSettings, User

QUOTA_CHOICES = (64, 128, 256, 512, 1024, 2048, 4096, 8192, 16384, 32768)
MEBIBYTE = 1024 * 1024
QUOTA_EXCEEDED = "Your media storage quota is full. Remove unused files or contact an administrator."


def validate_quota(value: int | None, *, optional: bool = False) -> None:
    if optional and value is None:
        return
    if type(value) is not int or value not in QUOTA_CHOICES:
        raise ValueError("Invalid media quota")


def quota_bytes(user: User, account: SiteSettings) -> int | None:
    if user.role == "admin":
        return None
    value = user.media_quota_mb
    if value is None:
        value = getattr(account, f"{user.role}_media_quota_mb")
    validate_quota(value)
    return value * MEBIBYTE


def _file_sizes(values: list[str]) -> dict[Path, int]:
    sizes = {}
    for value in values:
        path = media_path(value)
        if path is not None and path not in sizes:
            try:
                if path.is_file():
                    sizes[path] = path.stat().st_size
            except FileNotFoundError:
                continue  # A concurrent media removal is not stored usage.
    return sizes


async def usage_bytes(session: AsyncSession, owner_id: int) -> int:
    values = list(await session.scalars(select(MediaAsset.path).where(MediaAsset.owner_id == owner_id)
                                      .execution_options(include_all_owners=True)))
    sizes = await anyio.to_thread.run_sync(_file_sizes, values)
    return sum(sizes.values())


def _web_path(destination: Path) -> str:
    if destination.is_relative_to(settings.download_path.resolve()):
        return f"/panel/media/files/{quote(destination.name)}"
    return "/static/uploads/" + destination.relative_to(settings.upload_path.resolve()).as_posix()


async def publish_media(session: AsyncSession, staged: Path, destination: Path) -> None:
    """Check fresh permissions and quota before replacing any public/private file.

    SQLite's write lock covers the quota check, media ownership, promotion, and
    commit. Network streaming and image processing happen before this lock.
    Existing files are retained until both promotion and commit succeed.
    """
    if session.new or session.dirty or session.deleted:
        raise RuntimeError("Media publication requires a clean transaction")
    await session.commit()  # End the read snapshot without expiring route objects.
    await session.execute(text("BEGIN IMMEDIATE"))
    backup: Path | None = None
    promoted = False
    committed = False
    destination = destination.resolve()
    try:
        actor = await session.get(User, session.info.get("actor_id"), populate_existing=True) if session.info.get("actor_id") else None
        account = await session.scalar(select(SiteSettings).execution_options(populate_existing=True))
        if actor is None or not actor.is_active or actor.deleted_at is not None or account is None:
            raise HTTPException(403, "Forbidden")
        if (session.info.get("authenticated_credential") != credential_stamp(actor.username, actor.password_hash)
                or session.info.get("authenticated_generation") != account.session_generation
                or session.info.get("staff_role") != actor.role):
            raise HTTPException(403, "Forbidden")
        session.info["verified_editor"] = actor.is_verified
        assets = list(await session.scalars(select(MediaAsset).execution_options(include_all_owners=True))) if destination.exists() else []
        matching = [asset for asset in assets if media_path(asset.path) == destination]
        if destination.exists():
            from app.ownership import require_owned_media
            await require_owned_media(session, _web_path(destination), mutation=True)
        owner_ids = {asset.owner_id for asset in matching if asset.owner_id is not None} if matching else {actor.id}
        old_size = destination.stat().st_size if destination.is_file() else 0
        new_size = staged.stat().st_size
        for owner_id in owner_ids:
            owner = await session.get(User, owner_id, populate_existing=True)
            if owner is None:
                raise HTTPException(403, "Forbidden")
            limit = quota_bytes(owner, account)
            used = await usage_bytes(session, owner_id)
            credited_size = old_size if any(asset.owner_id == owner_id for asset in matching) else 0
            if limit is not None and used + new_size - credited_size > limit and new_size > credited_size:
                raise HTTPException(413, QUOTA_EXCEEDED)
        if not matching:
            session.add(MediaAsset(path=_web_path(destination), uploaded_by=actor.username))
        else:
            for asset in matching:
                asset.sha256 = None
                asset.checksum_size = None
                asset.checksum_mtime_ns = None
        await session.flush()
        if destination.exists():
            fd, name = tempfile.mkstemp(prefix=".replace-", suffix=".part", dir=destination.parent)
            os.close(fd)
            backup = Path(name)
            try:
                destination.replace(backup)
            except BaseException:
                backup.unlink(missing_ok=True)
                backup = None
                raise
        staged.replace(destination)
        promoted = True
        await session.commit()
        committed = True
    except BaseException:
        try:
            await session.rollback()
        finally:
            if promoted:
                destination.unlink(missing_ok=True)
            if backup is not None:
                backup.replace(destination)
                backup = None
        raise
    finally:
        # If filesystem recovery itself fails, retain the old bytes for repair.
        if backup is not None and committed:
            backup.unlink(missing_ok=True)

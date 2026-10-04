"""Transactional database restore with a crash-recoverable media swap."""

from datetime import datetime, timezone
from pathlib import Path
import secrets

from sqlalchemy import Boolean, DateTime, Enum, Integer, String, Table, delete, insert, text, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app import backups
from app.database import Base
from app.models import User, SiteSettings
from app.audit import add_event


def typed_rows(table: Table, rows: list[dict]) -> list[dict]:
    result = []
    for row in rows:
        converted = {}
        for column in table.columns:
            value = row[column.name]
            if value is None:
                if not column.nullable:
                    raise backups.BackupError("backup_invalid")
            elif isinstance(column.type, Boolean):
                if value not in (0, 1) or not isinstance(value, (bool, int)):
                    raise backups.BackupError("backup_invalid")
                value = bool(value)
            elif isinstance(column.type, Integer):
                if not isinstance(value, int) or isinstance(value, bool) or not -(2**63) <= value < 2**63:
                    raise backups.BackupError("backup_invalid")
            elif isinstance(column.type, DateTime):
                if not isinstance(value, str):
                    raise backups.BackupError("backup_invalid")
                try:
                    value = datetime.fromisoformat(value)
                except ValueError as exc:
                    raise backups.BackupError("backup_invalid") from exc
            elif isinstance(column.type, String):
                if not isinstance(value, str) or (column.type.length and len(value) > column.type.length):
                    raise backups.BackupError("backup_invalid")
                if isinstance(column.type, Enum) and value not in column.type.enums:
                    raise backups.BackupError("backup_invalid")
            converted[column.name] = value
        result.append(converted)
    return result


async def restore_site(session: AsyncSession, stage: Path, actor: User) -> None:
    """Caller holds the exclusive site gate and has freshly verified the administrator."""
    manifest, data = await run_in_threadpool(backups.validate_archive, stage)
    tables = [t for t in Base.metadata.sorted_tables if t.name != "backup_policy"]
    rows = {table.name: typed_rows(table, data[table.name]) for table in tables}
    # Keep the authenticating administrator usable, without exposing/importing a secret key.
    username, password_hash = actor.username, actor.password_hash
    users = rows["users"]
    recovered_admin = next((user for user in users if user["username"] == username), None)
    if recovered_admin is None:
        recovered_admin = {"id": max((u["id"] for u in users), default=0) + 1, "username": username,
                           "password_hash": password_hash, "role": "admin", "is_active": True, "is_verified": False,
                           "deletion_requested_by": None, "media_quota_mb": None,
                           "created_at": datetime.now(timezone.utc), "deleted_at": None}
        users.append(recovered_admin)
    recovered_admin.update(password_hash=password_hash, role="admin", is_active=True, deleted_at=None, deletion_requested_by=None)
    account = rows["site_settings"][0]
    account.update(session_generation=secrets.token_hex(32), restore_marker=stage.name)
    rows["site_lifecycle"][0].update(installed=True, pending_reset=None, purge_roots=None)
    source_root = Path(manifest.get("download_root", ""))
    if not source_root.is_absolute():
        raise backups.BackupError("backup_invalid")
    for item in rows["downloads"]:
        if item["file_path"]:
            old = Path(item["file_path"])
            if old.is_absolute():
                if not old.is_relative_to(source_root) or ".." in old.parts:
                    raise backups.BackupError("backup_invalid")
                item["file_path"] = str(backups.settings.download_path.resolve() / old.relative_to(source_root))
    session.info["audit_suppressed"] = True
    session.info.pop("actor_id", None)
    await session.execute(text("PRAGMA defer_foreign_keys=ON"))
    try:
        # Validate constraints in the current SQLite transaction before replacing media.
        for table in reversed(tables):
            await session.execute(delete(table))
        for table in tables:
            if rows[table.name]:
                await session.execute(insert(table), rows[table.name])
        if (await session.execute(text("PRAGMA foreign_key_check"))).first() is not None:
            raise backups.BackupError("backup_invalid")
        add_event(session, "restore", "settings", "Site restored from an encrypted backup", actor=username)
        await run_in_threadpool(backups.install_media, stage)
        await session.commit()
    except Exception:
        await session.rollback()
        marker = await session.scalar(select(SiteSettings.restore_marker))
        await run_in_threadpool(backups.recover_restore, marker)
        raise
    finally:
        session.info.pop("audit_suppressed", None)
    await run_in_threadpool(backups.recover_restore, stage.name)

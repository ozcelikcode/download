"""Opt-in retention for ordinary trash; pending editorial deletion is never bypassed."""

from datetime import datetime, timedelta, timezone
import math

from sqlalchemy import delete, select, or_, union
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.selectable import CompoundSelect

from app.audit import add_event
from app.models import Download, Page, SiteSettings

RETENTION_DAYS = (15, 30, 60, 90, 120, 240, 360)


def pending_families() -> CompoundSelect:
    return union(
        select(Download.id).where(Download.deletion_pending.is_(True)),
        select(Download.parent_id).where(Download.deletion_pending.is_(True), Download.parent_id.is_not(None)),
    )


async def protected_trash_ids(session: AsyncSession, ids: list[int]) -> set[int]:
    family = pending_families()
    return set(await session.scalars(select(Download.id).where(
        Download.id.in_(ids), or_(Download.id.in_(family), Download.parent_id.in_(family)),
    )))


def expires_at(deleted_at: datetime, days: int | None) -> str | None:
    if days not in RETENTION_DAYS:
        return None
    utc = deleted_at.replace(tzinfo=timezone.utc) if deleted_at.tzinfo is None else deleted_at.astimezone(timezone.utc)
    return (utc + timedelta(days=days)).isoformat()


def days_remaining(deleted_at: datetime, days: int) -> int:
    expiry = expires_at(deleted_at, days)
    if expiry is None:
        return 0
    seconds = (datetime.fromisoformat(expiry) - datetime.now(timezone.utc)).total_seconds()
    return max(0, math.ceil(seconds / 86400))


async def purge_expired_trash(session: AsyncSession, now: datetime | None = None) -> int:
    days = await session.scalar(select(SiteSettings.trash_retention_days))
    if days not in RETENTION_DAYS:
        return 0
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=days)
    session.info["audit_suppressed"] = True
    # Do not purge a parent with a pending deletion anywhere in its version family.
    pending_family = pending_families()
    try:
        result = await session.execute(delete(Download).where(
            Download.deleted_at <= cutoff, Download.deletion_pending.is_(False),
            Download.id.not_in(pending_family),
            or_(Download.parent_id.is_(None), Download.parent_id.not_in(pending_family)),
        ))
        count = result.rowcount
        result = await session.execute(delete(Page).where(Page.deleted_at <= cutoff))
        count += result.rowcount
        if count:
            add_event(session, "purge", "trash", "Expired trash removed", changes={"count": [None, count]}, actor="system")
        await session.commit()
        return count
    finally:
        session.info.pop("audit_suppressed", None)

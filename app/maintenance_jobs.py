"""One in-process scheduler; missed intervals are caught up on the next startup."""

import asyncio
from datetime import datetime, timedelta, timezone
import logging

from starlette.concurrency import run_in_threadpool

from app import backups
from app.database import AsyncSessionLocal
from app.lifecycle import request_gate
from app.models import BackupPolicy, SiteLifecycle
from app.trash_retention import purge_expired_trash

logger = logging.getLogger(__name__)
wake = asyncio.Event()


async def tick() -> None:
    async with request_gate.enter(exclusive=True):
        async with AsyncSessionLocal() as session:
            await run_in_threadpool(backups.clean_stages)
            state = await session.get(SiteLifecycle, 1)
            if state is None or not state.installed or state.pending_reset:
                return
            await purge_expired_trash(session)
            policy = await session.get(BackupPolicy, 1)
            if policy is None or not policy.public_key:
                return
            now = datetime.now(timezone.utc)
            last = policy.last_success.replace(tzinfo=timezone.utc) if policy.last_success else None
            due = policy.requested or (policy.enabled and (last is None or now - last >= timedelta(days=policy.interval_days)))
            attempted = policy.last_attempt.replace(tzinfo=timezone.utc) if policy.last_attempt else None
            if not due or (not policy.requested and attempted and now - attempted < timedelta(minutes=10)):
                return
            policy.requested = False
            policy.last_attempt = now
            policy.error_code = None
            pem = policy.public_key
            await session.commit()
            try:
                await run_in_threadpool(backups.create_backup, pem)
                policy.last_success, policy.error_code = now, None
                logger.info("Encrypted site backup completed")
            except Exception as exc:
                policy.error_code = str(exc) if isinstance(exc, backups.BackupError) else "backup_failed"
                logger.error("Site backup failed: error_type=%s", type(exc).__name__)
            await session.commit()


async def run() -> None:
    while True:
        wake.clear()
        try:
            # Cancellation waits for the protected operation to finish, including disk writes.
            operation = asyncio.create_task(tick())
            try:
                await asyncio.shield(operation)
            except asyncio.CancelledError:
                await operation
                raise
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Maintenance job failed: error_type=%s", type(exc).__name__)
        try:
            await asyncio.wait_for(wake.wait(), timeout=60)
        except TimeoutError:
            pass

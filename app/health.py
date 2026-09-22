"""Admin dashboard için içerik ve depolama sağlık denetimleri."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.media import media_usage
from app.models import Download, FileType, LinkCheck
from app.schemas import AdminHealthSummary

logger = logging.getLogger(__name__)

_IGNORED_STORAGE_NAMES = {".gitkeep"}


def _storage_files(root: Path) -> list[Path]:
    """Kök dışına çıkan sembolik bağlantıları izlemeden gerçek dosyaları döndür."""
    root = root.resolve()
    try:
        candidates = root.rglob("*")
        files: list[Path] = []
        for candidate in candidates:
            if candidate.name in _IGNORED_STORAGE_NAMES or candidate.name.startswith(".upload-"):
                continue
            try:
                resolved = candidate.resolve()
                if resolved.is_relative_to(root) and resolved.is_file():
                    files.append(resolved)
            except OSError as exc:
                logger.warning("Depolama girdisi okunamadı: path=%s error=%s", candidate, exc)
        return files
    except OSError as exc:
        logger.warning("Depolama dizini taranamadı: path=%s error=%s", root, exc)
        return []


def _scan_filesystem(
    local_paths: Iterable[str | None],
    used_paths: set[Path],
) -> tuple[int, int, int, int]:
    """Eksik yerel kayıtları, kullanılmayan medyayı ve depo boyutunu hesapla."""
    private_root = settings.download_path.resolve()
    icon_root = (settings.upload_path / "icons").resolve()

    missing_local_files = 0
    for value in local_paths:
        if not value:
            missing_local_files += 1
            continue
        try:
            candidate = Path(value).resolve()
            if (
                candidate == private_root
                or not candidate.is_relative_to(private_root)
                or not candidate.is_file()
            ):
                missing_local_files += 1
        except OSError:
            missing_local_files += 1

    private_files = _storage_files(private_root)
    icon_files = _storage_files(icon_root)
    normalized_usage = {path.resolve() for path in used_paths}
    unused_media = sum(
        path not in normalized_usage for path in (*private_files, *icon_files)
    )

    private_storage_bytes = 0
    for path in private_files:
        try:
            private_storage_bytes += path.stat().st_size
        except OSError as exc:
            logger.warning("Dosya boyutu okunamadı: path=%s error=%s", path, exc)

    return (
        missing_local_files,
        unused_media,
        private_storage_bytes,
        len(private_files),
    )


async def get_admin_health(session: AsyncSession) -> AdminHealthSummary:
    """Dashboard için veritabanı ve dosya sistemi sağlık özetini üret."""
    broken_links = await session.scalar(
        select(func.count()).select_from(LinkCheck).where(LinkCheck.status == "broken")
    )
    uncategorized_content = await session.scalar(
        select(func.count()).select_from(Download).where(
            Download.parent_id.is_(None),
            Download.category_id.is_(None),
            Download.is_draft.is_(False),
        )
    )
    local_paths = list(
        (
            await session.scalars(
                select(Download.file_path).where(
                    Download.parent_id.is_(None),
                    Download.file_type == FileType.local,
                    Download.is_draft.is_(False),
                )
            )
        ).all()
    )
    used_paths = set((await media_usage(session)).keys())
    missing, unused, storage_bytes, file_count = await run_in_threadpool(
        _scan_filesystem, local_paths, used_paths
    )

    return AdminHealthSummary(
        broken_links=broken_links or 0,
        missing_local_files=missing,
        unused_media=unused,
        uncategorized_content=uncategorized_content or 0,
        private_storage_bytes=storage_bytes,
        private_file_count=file_count,
    )

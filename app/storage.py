"""Yerel indirme dosyalarının özel depoda tutulması ve eski yolların taşınması."""

from __future__ import annotations

import hashlib
import logging
import shutil
from pathlib import Path
from urllib.parse import quote

import anyio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Download, FileType, MediaAsset

logger = logging.getLogger(__name__)


def _private_target(source: Path, private_root: Path) -> Path:
    preferred = private_root / source.name
    if not preferred.exists():
        return preferred
    suffix = hashlib.sha256(str(source).encode()).hexdigest()[:8]
    candidate = private_root / f"{source.stem}-legacy-{suffix}{source.suffix}"
    counter = 2
    while candidate.exists():
        candidate = private_root / f"{source.stem}-legacy-{suffix}-{counter}{source.suffix}"
        counter += 1
    return candidate


async def _update_media_asset_path(
    session: AsyncSession, source: Path, target: Path, public_root: Path
) -> None:
    relative_source = source.relative_to(public_root).as_posix()
    old_web_path = f"/static/uploads/{quote(relative_source, safe='/')}"
    new_web_path = f"/admin/media/files/{quote(target.name)}"
    old_asset = await session.scalar(select(MediaAsset).where(MediaAsset.path == old_web_path))
    new_asset = await session.scalar(select(MediaAsset).where(MediaAsset.path == new_web_path))
    if old_asset is None:
        return
    if new_asset is None:
        old_asset.path = new_web_path
        return
    if not new_asset.display_name:
        new_asset.display_name = old_asset.display_name
    if not new_asset.uploaded_by:
        new_asset.uploaded_by = old_asset.uploaded_by
    await session.delete(old_asset)


async def migrate_legacy_local_downloads(session: AsyncSession) -> int:
    """Statik dizindeki eski yerel indirmeleri özel depoya idempotent biçimde taşır."""
    public_root = settings.upload_path.resolve()
    icons_root = (public_root / "icons").resolve()
    private_root = settings.download_path.resolve()
    downloads = list(
        (
            await session.scalars(
                select(Download).where(
                    Download.file_type == FileType.local,
                    Download.file_path.is_not(None),
                )
            )
        ).all()
    )
    legacy_files = [
        path.resolve()
        for path in public_root.rglob("*")
        if path.is_file() and not path.resolve().is_relative_to(icons_root)
    ]
    migrated: dict[Path, Path] = {}
    updated = 0

    # Veritabanında henüz kullanılmayan arşiv dosyaları da statik web
    # kökünde kalmamalı; aksi halde URL'sini bilen herkes bunları indirebilir.
    for source in legacy_files:
        target = _private_target(source, private_root)
        await anyio.to_thread.run_sync(shutil.move, str(source), str(target))
        migrated[source] = target
        await _update_media_asset_path(session, source, target, public_root)
        logger.info("Eski arşiv dosyası özel depoya taşındı: %s -> %s", source, target)

    for download in downloads:
        source = Path(download.file_path or "").resolve()
        if not source.is_relative_to(public_root) or source.is_relative_to(icons_root):
            continue

        target = migrated.get(source)
        if target is None:
            # Dosya daha önce taşınmış, fakat DB yolu eski kalmış olabilir.
            target = private_root / source.name
            if not target.is_file():
                logger.warning("Eski yerel indirme dosyası bulunamadı: %s", source)
                continue
            migrated[source] = target

        download.file_path = str(target)
        await _update_media_asset_path(session, source, target, public_root)
        updated += 1

    if migrated or updated:
        await session.commit()
    return updated

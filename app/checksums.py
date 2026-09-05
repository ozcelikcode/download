"""Yerel dosyaların SHA-256 özeti; dosya değişince önbellek yenilenir."""

import hashlib
import logging
from pathlib import Path
from urllib.parse import quote, unquote

import anyio
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.media import media_path
from app.models import MediaAsset

logger = logging.getLogger(__name__)


def _hash_file(path: Path) -> tuple[str, int, int]:
    for _ in range(2):
        before = path.stat()
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        after = path.stat()
        if (before.st_ino, before.st_size, before.st_mtime_ns) == (after.st_ino, after.st_size, after.st_mtime_ns):
            return digest, after.st_size, after.st_mtime_ns
    raise OSError("Özet hesaplanırken dosya değişti.")


async def file_checksum(session: AsyncSession, value: str | None) -> str | None:
    path = media_path(value)
    if path is None or not path.is_file():
        return None
    url = "/static/uploads/" + quote(path.relative_to(settings.upload_path.resolve()).as_posix())
    asset = await session.scalar(select(MediaAsset).where(MediaAsset.path.in_([url, unquote(url)])))
    try:
        stat = path.stat()
        if asset and asset.sha256 and (asset.checksum_size, asset.checksum_mtime_ns) == (stat.st_size, stat.st_mtime_ns):
            return asset.sha256
        digest, size, mtime_ns = await anyio.to_thread.run_sync(_hash_file, path)
    except OSError:
        logger.exception("Dosya özeti hesaplanamadı: %s", path)
        return None
    values = {"sha256": digest, "checksum_size": size, "checksum_mtime_ns": mtime_ns}
    statement = insert(MediaAsset).values(path=asset.path if asset else url, **values)
    await session.execute(statement.on_conflict_do_update(index_elements=[MediaAsset.path], set_=values))
    await session.commit()
    return digest

"""Medya yolları ve silmeden önce içerik kullanım kontrolü."""

from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Download, FileType


def media_path(value: str | None, origin: str | None = None) -> Path | None:
    if not value:
        return None
    root = settings.upload_path.resolve()
    parsed = urlsplit(value)
    allowed_hosts = {urlsplit(settings.app_base_url).netloc, urlsplit(origin or "").netloc}
    if parsed.netloc and parsed.netloc not in allowed_hosts:
        return None
    path = unquote(parsed.path)
    if path.startswith("/static/uploads/"):
        candidate = root / path.removeprefix("/static/uploads/")
    elif not parsed.scheme and not parsed.netloc:
        candidate = Path(path)
    else:
        return None
    resolved = candidate.resolve()
    return resolved if resolved != root and resolved.is_relative_to(root) else None


class _MediaReferences(HTMLParser):
    def __init__(self, origin: str | None = None) -> None:
        super().__init__()
        self.origin = origin
        self.paths: set[Path] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for key, value in attrs:
            if key in {"href", "src", "poster"}:
                if path := media_path(value, self.origin):
                    self.paths.add(path)
            elif key == "srcset" and value:
                for source in value.split(","):
                    if source.strip() and (path := media_path(source.strip().split()[0], self.origin)):
                        self.paths.add(path)


async def media_usage(session: AsyncSession, origin: str | None = None) -> dict[Path, list[dict]]:
    usage: dict[Path, list[dict]] = {}
    downloads = (await session.scalars(select(Download))).all()
    for download in downloads:
        parser = _MediaReferences(origin)
        parser.feed(download.description or "")
        paths = parser.paths
        values = [download.icon_image_path, download.icon_image_url, download.thumbnail_path]
        if download.file_type == FileType.local:
            values.append(download.file_path)
        for value in values:
            if path := media_path(value, origin):
                paths.add(path)
        for path in paths:
            usage.setdefault(path, []).append({
                "id": download.id, "title": download.title,
                "url": f"/admin/downloads/{download.id}/edit",
            })
    return usage


async def ensure_unused(session: AsyncSession, value: str, origin: str | None = None) -> Path:
    path = media_path(value, origin)
    if path is None:
        raise HTTPException(status_code=400, detail="Geçersiz medya yolu.")
    linked = (await media_usage(session, origin)).get(path, [])
    if linked:
        raise HTTPException(status_code=409, detail={
            "message": "Dosya kullanıldığı için silinemedi. Önce ilgili içeriklerdeki bağlantıyı kaldırın.",
            "downloads": linked,
        })
    return path

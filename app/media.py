"""Medya yolları ve silmeden önce içerik kullanım kontrolü."""

from html.parser import HTMLParser
import logging
import os
from pathlib import Path
import tempfile
from urllib.parse import unquote, urlsplit

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Download, FileType, Page, SiteSettings, User

logger = logging.getLogger(__name__)


def media_path(value: str | None, origin: str | None = None) -> Path | None:
    if not value:
        return None
    public_root = settings.upload_path.resolve()
    private_root = settings.download_path.resolve()
    parsed = urlsplit(value)
    allowed_hosts = {urlsplit(settings.app_base_url).netloc, urlsplit(origin or "").netloc}
    if parsed.netloc and parsed.netloc not in allowed_hosts:
        return None
    path = unquote(parsed.path)
    if path.startswith("/static/uploads/"):
        candidate = public_root / path.removeprefix("/static/uploads/")
    elif path.startswith("/panel/media/files/"):
        candidate = private_root / path.removeprefix("/panel/media/files/")
    elif path.startswith("/admin/media/files/"):
        candidate = private_root / path.removeprefix("/admin/media/files/")
    elif not parsed.scheme and not parsed.netloc:
        candidate = Path(path)
    else:
        return None
    resolved = candidate.resolve()
    for root in (public_root, private_root):
        if resolved != root and resolved.is_relative_to(root):
            return resolved
    return None


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


async def media_usage(session: AsyncSession, origin: str | None = None, *, all_owners: bool = False) -> dict[Path, list[dict]]:
    usage: dict[Path, list[dict]] = {}
    from app.profile_photos import photo_path
    users_query = select(User.id)
    if not all_owners and session.info.get("editor_owner_id") is not None:
        users_query = users_query.where(User.id == session.info["editor_owner_id"])
    for user_id in await session.scalars(users_query):
        try:
            path = photo_path(user_id)
        except ValueError:
            continue
        # Account references must not be mistaken for download IDs by review checks.
        usage[path] = [{"id": None, "title": "Profile photo", "owner_id": user_id,
                        "url": "/panel/settings/account"}]
    downloads = (await session.scalars(select(Download).execution_options(include_all_owners=all_owners))).all()
    for download in downloads:
        parser = _MediaReferences(origin)
        parser.feed(download.description or "")
        paths = parser.paths
        values = [download.icon_image_path, download.icon_image_url, download.thumbnail_path]
        from app.gallery import gallery_paths
        values.extend(gallery_paths(download.gallery_images))
        if download.file_type == FileType.local:
            values.append(download.file_path)
        for value in values:
            if path := media_path(value, origin):
                paths.add(path)
        for path in paths:
            usage.setdefault(path, []).append({
                "id": download.id, "title": download.title,
                "owner_id": download.owner_id,
                "url": f"/panel/downloads/{download.id}/edit",
            })
    if all_owners:
        pages = await session.scalars(select(Page))
        for page in pages:
            parser = _MediaReferences(origin)
            parser.feed(page.body_html)
            for path in parser.paths:
                usage.setdefault(path, []).append({"id": page.id, "title": page.title, "owner_id": None, "url": f"/panel/pages/{page.id}/edit"})
        account = await session.scalar(select(SiteSettings))
        if account:
            for value in (account.logo_light_path, account.logo_dark_path, account.hero_image_path):
                if path := media_path(value, origin):
                    usage.setdefault(path, []).append({"id": account.id, "title": "Site settings", "owner_id": None, "url": "/panel/settings/appearance"})
    return usage


async def ensure_unused(session: AsyncSession, value: str, origin: str | None = None) -> Path:
    """Serialize fresh actor validation and the reference check before deletion."""
    from app.dependencies import credential_stamp
    from app.ownership import require_owned_media
    if session.new or session.dirty or session.deleted:
        raise RuntimeError("Media deletion requires a clean transaction")
    await session.rollback()
    await session.execute(text("BEGIN IMMEDIATE"))
    actor = await session.get(User, session.info.get("actor_id"), populate_existing=True) if session.info.get("actor_id") else None
    account = await session.scalar(select(SiteSettings).execution_options(populate_existing=True))
    if (actor is None or account is None or not actor.is_active or actor.deleted_at is not None
            or actor.role != session.info.get("staff_role")
            or session.info.get("authenticated_generation") != account.session_generation
            or session.info.get("authenticated_credential") != credential_stamp(actor.username, actor.password_hash)):
        raise HTTPException(403, "Forbidden")
    await require_owned_media(session, value)
    path = media_path(value, origin)
    if path is None or any(part.startswith(".") for root in (settings.upload_path.resolve(), settings.download_path.resolve()) if path.is_relative_to(root) for part in path.relative_to(root).parts):
        raise HTTPException(status_code=400, detail="Geçersiz medya yolu.")
    linked = (await media_usage(session, origin, all_owners=True)).get(path, [])
    if linked:
        raise HTTPException(status_code=409, detail={
            "message": "Dosya kullanıldığı için silinemedi. Önce ilgili içeriklerdeki bağlantıyı kaldırın.",
            "downloads": [] if session.info.get("editor_owner_id") is not None else linked,
        })
    return path


async def delete_unused_media(session: AsyncSession, value: str, origin: str | None = None) -> None:
    """Retain original bytes until metadata deletion commits successfully."""
    from app import crud
    from app.storage_quota import _web_path

    backup: Path | None = None
    path: Path | None = None
    committed = False
    try:
        path = await ensure_unused(session, value, origin)
        if path.is_file():
            fd, name = tempfile.mkstemp(prefix=".delete-", suffix=".part", dir=path.parent)
            os.close(fd)
            backup = Path(name)
            try:
                path.replace(backup)
            except BaseException:
                backup.unlink(missing_ok=True)
                backup = None
                raise
        await crud.delete_media_asset(session, _web_path(path))
        committed = True
    except BaseException:
        await session.rollback()
        if backup is not None and path is not None:
            backup.replace(path)
            backup = None
        raise
    finally:
        if committed and backup is not None:
            try:
                backup.unlink(missing_ok=True)
            except OSError:
                logger.exception("Committed media deletion retained a private recovery file")

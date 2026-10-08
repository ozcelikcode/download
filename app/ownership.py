"""Request-scoped editor isolation, including relationship loads and bulk writes."""

from __future__ import annotations

from collections.abc import Iterator
from fastapi import HTTPException
from sqlalchemy import and_, event, inspect, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import ORMExecuteState, Session, with_loader_criteria
from sqlalchemy.sql.selectable import FromClause, Join

from app.models import Category, Download, DownloadTag, MediaAsset, Tag

OWNED_MODELS = (Category, Tag, Download, MediaAsset)


def _direct_tables(clause: FromClause) -> Iterator[FromClause]:
    """Inspect direct FROM tables without pulling subquery tables into the outer query."""
    if isinstance(clause, Join):
        yield from _direct_tables(clause.left)
        yield from _direct_tables(clause.right)
    else:
        yield clause


@event.listens_for(Session, "do_orm_execute")
def scope_editor_queries(state: ORMExecuteState) -> None:
    owner_id = state.session.info.get("editor_owner_id")
    if owner_id is None:
        return
    if state.execution_options.get("include_all_owners"):
        return
    tables = [table for clause in state.statement.get_final_froms() for table in _direct_tables(clause)] if state.is_select else []
    for model in OWNED_MODELS:
        criterion = model.owner_id == owner_id
        if model is Category:
            criterion = (or_(criterion, Category.is_required.is_(True)) if state.is_select
                         else and_(criterion, Category.is_required.is_(False)))
        # COUNT(*) with select_from(Model) has no ORM entity for loader criteria.
        represented = any(column.get("entity") is model for column in getattr(state.statement, "column_descriptions", []))
        if not represented and any(table is model.__table__ or table.compare(model.__table__) for table in tables):
            state.statement = state.statement.where(criterion)
        state.statement = state.statement.options(
            with_loader_criteria(model, criterion, include_aliases=True)
        )


@event.listens_for(Session, "before_flush")
def protect_owned_changes(session: Session, _context: object, _instances: object) -> None:
    actor_id = session.info.get("actor_id")
    editor_id = session.info.get("editor_owner_id")
    for obj in list(session.new):
        if isinstance(obj, OWNED_MODELS) and actor_id is not None:
            obj.owner_id = None if isinstance(obj, Category) and obj.is_required else actor_id
    for obj in list(session.new) + list(session.dirty):
        if isinstance(obj, Download):
            changed = {attr.key for attr in inspect(obj).mapper.column_attrs if inspect(obj).attrs[attr.key].history.has_changes()}
            if obj not in session.new and obj.is_hidden and changed <= {"is_hidden"}:
                continue
            if obj.is_draft:
                obj.publication_pending = False
            else:
                from app.moderation import requires_review
                flagged = editor_id is not None and requires_review(obj.title, obj.description, obj.short_description)
                if obj.is_active is False and not flagged:
                    continue
                if editor_id is None or (session.info.get("verified_editor") and not flagged):
                    obj.publication_pending = False
                    continue
                obj.is_active = False
                obj.publication_pending = True
                obj.publication_feedback = None
    if editor_id is None:
        return
    for obj in list(session.dirty) + list(session.deleted):
        if isinstance(obj, OWNED_MODELS):
            if isinstance(obj, Category) and obj.is_required:
                raise HTTPException(403)
            history = inspect(obj).attrs.owner_id.history
            if obj.owner_id != editor_id or history.has_changes():
                raise HTTPException(404)
            if isinstance(obj, (Category, Tag)) and (obj in session.deleted or session.is_modified(obj, include_collections=False)):
                query = select(Download.id).where(or_(Download.owner_id.is_(None), Download.owner_id != editor_id))
                if isinstance(obj, Category):
                    query = query.where(Download.category_id == obj.id)
                else:
                    query = query.join(DownloadTag, DownloadTag.download_id == Download.id).where(DownloadTag.tag_id == obj.id)
                if session.scalar(query.execution_options(include_all_owners=True).limit(1)) is not None:
                    raise HTTPException(409)


async def require_owned_media(session: AsyncSession, value: str | None, *, mutation: bool = False) -> None:
    """Resolve path aliases before checking ownership; never trust submitted paths."""
    if session.info.get("editor_owner_id") is None or not value:
        return
    from app.media import media_path

    path = media_path(value)
    paths = await session.scalars(select(MediaAsset.path))
    if path is None or not any(media_path(owned) == path for owned in paths):
        raise HTTPException(404)
    if mutation:
        from app.media import media_usage
        # The full usage check stays internal; no other owner's titles are returned.
        usage = await media_usage(session, all_owners=True)
        if any(row["owner_id"] != session.info["editor_owner_id"] for row in usage.get(path, [])):
            raise HTTPException(409)
        # Replacing a live binary or illustration must not bypass publication review.
        from app.models import User
        verified = await session.scalar(select(User.is_verified).where(User.id == session.info["editor_owner_id"], User.is_active.is_(True)))
        if not verified:
            live_ids = set(await session.scalars(select(Download.id).where(Download.is_active.is_(True), Download.is_draft.is_(False), Download.deleted_at.is_(None))))
            if any(row["id"] in live_ids for row in usage.get(path, [])):
                raise HTTPException(409)


async def validate_download_references(session: AsyncSession, data: object) -> None:
    from app.gallery import gallery_paths
    from app.crud import get_site_settings
    import json

    paths = getattr(data, 'gallery_paths', None)
    if paths is not None:
        gallery_paths(json.dumps(paths))
        if len(paths) > (await get_site_settings(session)).gallery_image_limit:
            raise ValueError('Gallery image limit exceeded')
        for path in paths:
            if await session.scalar(select(MediaAsset.id).where(MediaAsset.path == path)) is None:
                raise HTTPException(404)
    if session.info.get("editor_owner_id") is None:
        return
    for model, field in ((Category, "category_id"), (Download, "parent_id")):
        value = getattr(data, field, None)
        if value is not None and await session.scalar(select(model.id).where(model.id == value)) is None:
            raise HTTPException(404)
    ids = set(getattr(data, "tag_ids", None) or [])
    if ids:
        found = set(await session.scalars(select(Tag.id).where(Tag.id.in_(ids))))
        if found != ids:
            raise HTTPException(404)
    for field in ("file_path", "icon_image_path", "thumbnail_path"):
        await require_owned_media(session, getattr(data, field, None))
    # Local URLs and inline images must not bypass the media boundary.
    from app.media import _MediaReferences, media_path

    for field in ("icon_image_url", "external_url"):
        value = getattr(data, field, None)
        if value and media_path(value) is not None:
            await require_owned_media(session, value)
    parser = _MediaReferences()
    parser.feed(getattr(data, "description", None) or "")
    for path in parser.paths:
        await require_owned_media(session, str(path))

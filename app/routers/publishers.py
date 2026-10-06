"""Public publisher catalogs and photos expose only published identities."""

import math

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.database import get_db
from app.models import Download, User
from app.profile_photos import photo_path
from app.routers.public import _sidebar_context
from app.templating import templates

router = APIRouter(prefix="/publisher")


async def visible_publisher(session: AsyncSession, user_id: int) -> User:
    user = await session.get(User, user_id)
    visible = await session.scalar(select(func.count()).select_from(
        crud._download_base_query().where(Download.owner_id == user_id).subquery()))
    if user is None or not user.is_active or user.deleted_at is not None or not visible:
        raise HTTPException(404)
    return user


@router.get("/{user_id}/photo")
async def publisher_photo(user_id: int, session: AsyncSession = Depends(get_db)) -> FileResponse:
    await visible_publisher(session, user_id)
    try:
        path = photo_path(user_id)
    except ValueError as exc:
        raise HTTPException(404) from exc
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, media_type="image/webp", headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/{user_id}")
async def publisher_catalog(request: Request, user_id: int, page: int = Query(1, ge=1),
                            session: AsyncSession = Depends(get_db)):
    user = await visible_publisher(session, user_id)
    items, total = await crud.get_downloads_paginated(session, page=page, owner_id=user_id)
    context = await _sidebar_context(request, session)
    context.update(request=request, publisher=user, downloads=items, total=total, page=page,
                   total_pages=max(1, math.ceil(total / 12)), page_title=user.username, hide_sidebar=True)
    return templates.TemplateResponse(request=request, name="publisher.html", context=context)

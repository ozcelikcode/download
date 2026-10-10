"""Authenticated gallery image uploads and administrator-only gallery policy."""

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.audit import add_event
from app.config import settings
from app.database import get_db
from app.dependencies import require_admin
from app.gallery import GALLERY_LIMITS, prepare_gallery_image
from app.i18n import translate
from app.routers.users import _lock_actor
from app.security import require_csrf
from app.storage_quota import publish_media
from app.uploads import save_upload

router = APIRouter(prefix='/panel', dependencies=[Depends(require_csrf), Depends(require_admin)])


@router.post('/upload/gallery-image')
async def upload_gallery_image(request: Request, file: UploadFile = File(...), session: AsyncSession = Depends(get_db)) -> dict[str, str]:
    policy = await crud.get_site_settings(session)
    level = policy.image_compression_level
    filename = uuid4().hex + '.webp'
    destination = settings.upload_path / 'gallery' / filename
    result_path = '/static/uploads/gallery/' + filename

    def prepare(staged: Path) -> None:
        prepare_gallery_image(staged, level=level)

    async def publish(staged: Path, target: Path) -> None:
        nonlocal result_path
        result_path = await publish_media(session, staged, target, reuse_identical=True)

    try:
        await save_upload(file, destination, validator=prepare, publisher=publish, max_bytes=20 * 1024 * 1024)
    except ValueError:
        raise HTTPException(400, translate(request, 'compression_failed')) from None
    return {'path': result_path}


@router.post('/settings/gallery')
async def save_gallery_policy(request: Request, limit: int = Form(...), session: AsyncSession = Depends(get_db)) -> RedirectResponse:
    await _lock_actor(request, session, 'admin')
    if limit not in GALLERY_LIMITS:
        raise HTTPException(422, translate(request, 'gallery_limit_invalid'))
    policy = await crud.get_site_settings(session)
    before = policy.gallery_image_limit
    policy.gallery_image_limit = limit
    add_event(session, 'update', 'site_settings', 'Gallery image limit', changes={'gallery_image_limit': [before, limit]})
    await session.commit()
    from app.templating import refresh_site_branding_globals
    refresh_site_branding_globals(policy)
    request.session['flash_message'] = translate(request, 'gallery_saved')
    return RedirectResponse('/panel/settings/appearance', status_code=303)

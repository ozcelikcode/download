"""Administrator-only policy for optional content image compression."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.audit import add_event
from app.database import get_db
from app.dependencies import require_admin
from app.security import require_csrf
from app.i18n import translate
from app.routers.users import _lock_actor

router = APIRouter(prefix='/panel/settings', dependencies=[Depends(require_admin), Depends(require_csrf)])


@router.post('/image-compression')
async def save_image_policy(request: Request, session: AsyncSession = Depends(get_db),
                            enabled: bool = Form(False), level: int = Form(..., ge=0, le=4)):
    await _lock_actor(request, session, 'admin')
    policy = await crud.get_site_settings(session)
    before = {'enabled': policy.image_compression_enabled, 'level': policy.image_compression_level}
    policy.image_compression_enabled = enabled
    policy.image_compression_level = level
    add_event(session, 'update', 'site_settings', 'Image compression', changes={
        'enabled': [before['enabled'], enabled], 'level': [before['level'], level]})
    await session.commit()
    request.session['flash_message'] = translate(request, 'compression_saved')
    return RedirectResponse('/panel/settings/appearance', status_code=303)

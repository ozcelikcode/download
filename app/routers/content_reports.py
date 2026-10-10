"""Role-scoped publisher inbox without reporter identities or arbitrary recipient IDs."""

import json
import math

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_admin
from app.models import AuditLog, Download, User
from app.audit import add_event
from app.i18n import translate
from app.security import require_csrf, reserve_login_attempt
from app.routers.users import _lock_actor
from app.validation import RecordId
from app.pagination import PageNumber
from app.templating import templates

router = APIRouter(prefix="/panel/content-reports", dependencies=[Depends(require_admin)])


@router.post('/{download_id}/note', dependencies=[Depends(require_csrf)])
async def send_editor_note(download_id: RecordId, request: Request,
                           note: str = Form(..., min_length=1, max_length=500),
                           session: AsyncSession = Depends(get_db)) -> RedirectResponse:
    """Send a bounded private note to the current editor through the existing inbox."""
    role = request.state.admin_role
    if role not in {'admin', 'manager'}:
        raise HTTPException(403, translate(request, 'permission_denied'))
    note = note.strip()
    if not note:
        raise HTTPException(422, translate(request, 'editor_note_help'))
    await session.rollback()
    try:
        await reserve_login_attempt(session, f'editor-note:{request.state.admin_id}')
    except HTTPException as exc:
        if exc.status_code != 429:
            raise
        raise HTTPException(429, translate(request, 'too_many'), headers=exc.headers) from None
    await _lock_actor(request, session, role)
    download = await session.get(Download, download_id, populate_existing=True)
    publisher = await session.get(User, download.owner_id, populate_existing=True) if download and download.owner_id else None
    if (download is None or download.deleted_at is not None or publisher is None or publisher.role != 'editor'
            or not publisher.is_active or publisher.deleted_at is not None):
        raise HTTPException(404)
    add_event(session, 'report', 'publisher_reports', 'Staff sent an editor note', download.id,
              {'reason': [None, 'editor_note_text'], 'recipient_id': [None, publisher.id], 'note': [None, note]})
    await session.commit()
    request.session['editor_note_sent'] = download.slug
    return RedirectResponse(f'/download/{download.slug}', status_code=303)


@router.get("")
async def publisher_inbox(request: Request, page: PageNumber = 1, session: AsyncSession = Depends(get_db)):
    query = select(AuditLog, Download).outerjoin(Download, Download.id == AuditLog.entity_id).where(
        AuditLog.entity.in_(['publisher_reports'] if request.state.admin_role == 'editor' else ['publisher_reports', 'publisher_alerts']), AuditLog.action == "report")
    if request.state.admin_role == "editor":
        query = query.where(Download.owner_id == request.state.admin_id,
                            func.json_extract(AuditLog.changes, '$.recipient_id[1]') == request.state.admin_id)
    total = await session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = await session.execute(query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).offset((page - 1) * 20).limit(20))
    items = []
    editor_notes: dict[int, str] = {}
    for event, download in rows:
        try:
            changes = json.loads(event.changes)
            reason = changes.get('reason', [None, 'detail_report_incorrect'])[1]
            if reason == 'editor_note_text':
                note = changes.get('note', [None, ''])[1]
                editor_notes[event.id] = note[:500] if isinstance(note, str) else ''
        except (ValueError, TypeError, IndexError, AttributeError):
            reason = 'detail_report_incorrect'
        if reason not in {'detail_report_broken', 'detail_report_incorrect', 'detail_report_unsafe', 'editor_note_text'}:
            reason = 'detail_report_incorrect'
        if event.entity == 'publisher_alerts':
            reason = 'publisher_report_alert'
        items.append((event, download, reason))
    return templates.TemplateResponse(request=request, name="admin/visitor_reports.html", context={
        'request': request, 'admin_user': request.state.admin_user, 'items': items,
        'page': page, 'pages': max(1, math.ceil(total / 20)), 'publisher_inbox': True, 'editor_notes': editor_notes})

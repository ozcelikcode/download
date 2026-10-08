"""Role-scoped publisher inbox without reporter identities or arbitrary recipient IDs."""

import json
import math

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_admin
from app.models import AuditLog, Download
from app.templating import templates

router = APIRouter(prefix="/panel/content-reports", dependencies=[Depends(require_admin)])


@router.get("")
async def publisher_inbox(request: Request, page: int = Query(1, ge=1), session: AsyncSession = Depends(get_db)):
    query = select(AuditLog, Download).outerjoin(Download, Download.id == AuditLog.entity_id).where(
        AuditLog.entity.in_(['publisher_reports'] if request.state.admin_role == 'editor' else ['publisher_reports', 'publisher_alerts']), AuditLog.action == "report")
    if request.state.admin_role == "editor":
        query = query.where(Download.owner_id == request.state.admin_id,
                            func.json_extract(AuditLog.changes, '$.recipient_id[1]') == request.state.admin_id)
    total = await session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = await session.execute(query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).offset((page - 1) * 20).limit(20))
    items = []
    for event, download in rows:
        try:
            reason = json.loads(event.changes).get('reason', [None, 'detail_report_incorrect'])[1]
        except (ValueError, TypeError, IndexError, AttributeError):
            reason = 'detail_report_incorrect'
        if reason not in {'detail_report_broken', 'detail_report_incorrect', 'detail_report_unsafe'}:
            reason = 'detail_report_incorrect'
        if event.entity == 'publisher_alerts':
            reason = 'publisher_report_alert'
        items.append((event, download, reason))
    return templates.TemplateResponse(request=request, name="admin/visitor_reports.html", context={
        'request': request, 'admin_user': request.state.admin_user, 'items': items,
        'page': page, 'pages': max(1, math.ceil(total / 20)), 'publisher_inbox': True})

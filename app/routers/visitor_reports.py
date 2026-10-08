"""Bounded anonymous issue reports stored under the existing audit-retention policy."""

import json

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.audit import add_event
from app.database import get_db
from app.dependencies import get_request_ip
from app.i18n import translate
from app.models import AuditLog
from app.security import require_csrf, reserve_login_attempt

router = APIRouter(dependencies=[Depends(require_csrf)])


@router.post("/download/{slug}/report")
async def report_download(
    slug: str,
    request: Request,
    reason: str = Form(..., max_length=20),
    target: str = Form("staff", max_length=12),
    session: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    if reason not in {"broken", "incorrect", "unsafe"} or target not in {"staff", "publisher"}:
        raise HTTPException(400, translate(request, "detail_report_invalid"))
    try:
        await reserve_login_attempt(session, "visitor-report:" + get_request_ip(request))
    except HTTPException as exc:
        raise HTTPException(exc.status_code, translate(request, "detail_report_limit"), headers=exc.headers) from None
    await session.execute(text("BEGIN IMMEDIATE"))
    download = await crud.get_download_by_slug(session, slug)
    if download is None:
        raise HTTPException(404)
    if target == "publisher" and (download.publisher is None or not download.publisher.is_active or download.publisher.deleted_at is not None):
        raise HTTPException(404)
    # Coalesce identical retained reports; no free text, IP address, or contact data is stored.
    label = "detail_report_" + reason
    changes = {"reason": [None, label]}
    entity = "visitor_reports" if target == "staff" else "publisher_reports"
    if target == "publisher":
        changes["recipient_id"] = [None, download.owner_id]
    duplicate = await session.scalar(select(AuditLog.id).where(
        AuditLog.entity == entity, AuditLog.entity_id == download.id,
        AuditLog.action == "report", AuditLog.changes == json.dumps(changes, ensure_ascii=False),
    ))
    if duplicate is None:
        add_event(session, "report", entity, "Visitor reported a content issue", download.id,
                  changes, actor="anonymous")
        if target == 'publisher' and download.publisher.role == 'editor':
            publisher = download.publisher
            publisher.publisher_report_count += 1
            if publisher.publisher_report_count % 10 == 0:
                add_event(session, 'report', 'publisher_alerts', 'Publisher report threshold reached', download.id,
                          {'recipient_id': [None, publisher.id], 'report_count': [None, publisher.publisher_report_count]}, actor='anonymous')
    await session.commit()
    request.session["download_report_received"] = slug
    return RedirectResponse(f"/download/{download.slug}", status_code=303)

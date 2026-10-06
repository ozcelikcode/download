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
    session: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    if reason not in {"broken", "incorrect", "unsafe"}:
        raise HTTPException(400, translate(request, "detail_report_invalid"))
    try:
        await reserve_login_attempt(session, "visitor-report:" + get_request_ip(request))
    except HTTPException as exc:
        raise HTTPException(exc.status_code, translate(request, "detail_report_limit"), headers=exc.headers) from None
    await session.execute(text("BEGIN IMMEDIATE"))
    download = await crud.get_download_by_slug(session, slug)
    if download is None:
        raise HTTPException(404)
    # Coalesce identical retained reports; no free text, IP address, or contact data is stored.
    label = "detail_report_" + reason
    changes = {"reason": [None, label]}
    duplicate = await session.scalar(select(AuditLog.id).where(
        AuditLog.entity == "visitor_reports", AuditLog.entity_id == download.id,
        AuditLog.action == "report", AuditLog.changes == json.dumps(changes, ensure_ascii=False),
    ))
    if duplicate is None:
        add_event(session, "report", "visitor_reports", "Visitor reported a content issue", download.id,
                  changes, actor="anonymous")
    await session.commit()
    request.session["download_report_received"] = slug
    return RedirectResponse(f"/download/{download.slug}", status_code=303)

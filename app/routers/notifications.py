"""Role-scoped actionable notifications with signed-session read markers."""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_admin
from app.i18n import translate
from app.models import AuditLog, Download, EditorMessage, RegistrationRequest, User
from app.security import require_csrf

router = APIRouter(prefix="/panel/notifications", dependencies=[Depends(require_csrf), Depends(require_admin)])


def _seen(request: Request, kind: str) -> datetime:
    if request.session.get("panel_notice_owner") != request.state.admin_id:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
    markers = request.session.get("panel_notice_reads", {})
    try:
        return datetime.fromisoformat(markers[kind]).replace(tzinfo=timezone.utc)
    except (KeyError, ValueError, TypeError):
        return datetime(1970, 1, 1, tzinfo=timezone.utc)


async def snapshot(request: Request, session: AsyncSession) -> dict[str, Any]:
    items = []
    counters = {}

    async def group(kind: str, label: str, url: str, model: type, date: Any, *conditions: Any,
                    join: tuple | None = None) -> None:
        query = select(func.count(), func.max(date), func.sum(case((date > _seen(request, kind), 1), else_=0))).select_from(model)
        if join is not None:
            query = query.join(*join)
        count, latest, unread = (await session.execute(query.where(*conditions))).one()
        counters[kind] = count
        if count:
            latest = latest.replace(tzinfo=timezone.utc)
            items.append({"kind": kind, "label": translate(request, label), "url": url,
                          "count": count, "unread": int(unread or 0), "latest": latest.isoformat()})

    if request.state.admin_role == "editor":
        await group("contact", "contact_answered", "/panel/contact", EditorMessage, EditorMessage.responded_at,
                    EditorMessage.sender_id == request.state.admin_id, EditorMessage.responded_at.is_not(None))
        await group("content", "content_updates", "/panel/downloads", AuditLog, AuditLog.created_at,
                    AuditLog.entity == "publication", AuditLog.action.in_(["approve", "reject"]),
                    Download.owner_id == request.state.admin_id,
                    join=(Download, Download.id == AuditLog.entity_id))
    else:
        await group("reports", "visitor_reports", "/panel/links/reports", AuditLog, AuditLog.created_at,
                    AuditLog.entity == "visitor_reports", AuditLog.action == "report")
        await group("registrations", "registration_requests", "/panel/registrations", RegistrationRequest, RegistrationRequest.created_at)
        await group("review", "review_title", "/panel/review", Download, Download.updated_at,
                    Download.publication_pending.is_(True), Download.deleted_at.is_(None))
        await group("trash", "trash", "/panel/downloads/trash", Download, Download.deleted_at,
                    Download.deletion_pending.is_(True), Download.deleted_at.is_not(None))
        requested_at = select(func.max(AuditLog.created_at)).where(
            AuditLog.entity == "users", AuditLog.entity_id == User.id, AuditLog.changes.contains('"pending"'),
        ).correlate(User).scalar_subquery()
        await group("users", "user_pending_delete", "/panel/users", User, func.coalesce(requested_at, User.created_at),
                    User.deletion_requested_by.is_not(None), User.is_active.is_(True))
        await group("contact", "contact_title", "/panel/contact", EditorMessage, EditorMessage.created_at,
                    EditorMessage.response.is_(None))
    return {
        "items": items, "counters": counters,
        "unread_counters": {kind: next((item["unread"] for item in items if item["kind"] == kind), 0) for kind in counters},
        "unread": sum(item["unread"] for item in items),
    }


def mark_read(request: Request, data: dict[str, Any], kind: str | None = None) -> None:
    """Acknowledge only the observed horizon, scoped to the authenticated identity."""
    markers = (dict(request.session.get("panel_notice_reads", {}))
               if request.session.get("panel_notice_owner") == request.state.admin_id else {})
    for item in data["items"]:
        if kind is None or item["kind"] == kind:
            markers[item["kind"]] = item["latest"]
            item["unread"] = 0
            data["unread_counters"][item["kind"]] = 0
    request.session["panel_notice_owner"] = request.state.admin_id
    request.session["panel_notice_reads"] = markers
    data["unread"] = sum(item["unread"] for item in data["items"])


async def prepare_page_notifications(request: Request, session: AsyncSession) -> None:
    """Seed HTML badges and acknowledge a notification destination from any entry point."""
    data = await snapshot(request, session)
    destinations = {item["url"].rstrip("/"): item["kind"] for item in data["items"]}
    kind = destinations.get(request.url.path.rstrip("/"))
    if kind is not None:
        mark_read(request, data, kind)
    request.state.panel_notices = data


@router.get("")
async def list_notifications(request: Request, session: AsyncSession = Depends(get_db)):
    return await snapshot(request, session)


@router.post("/open")
async def open_notification(request: Request, kind: str = Form(...), session: AsyncSession = Depends(get_db)):
    data = await snapshot(request, session)
    item = next((item for item in data["items"] if item["kind"] == kind), None)
    if item is None:
        raise HTTPException(404)
    mark_read(request, data, kind)
    return RedirectResponse(item["url"], status_code=303)


@router.post("/read-all", response_model=None)
async def read_all_notifications(
    request: Request, session: AsyncSession = Depends(get_db),
) -> dict[str, Any] | RedirectResponse:
    data = await snapshot(request, session)
    mark_read(request, data)
    if "application/json" in request.headers.get("accept", ""):
        return data
    request.session["flash_message"] = translate(request, "notice_read_all_done")
    return RedirectResponse("/panel", status_code=303)

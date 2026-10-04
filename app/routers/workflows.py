"""Editorial publication review and private editor correspondence."""

from datetime import datetime, timedelta, timezone
import secrets

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import add_event
from app.database import get_db
from app.dependencies import SESSION_COOKIE, require_admin
from app.i18n import translate
from app.models import Download, EditorMessage
from app.security import require_csrf
from app.templating import templates

router = APIRouter(prefix="/panel", dependencies=[Depends(require_csrf), Depends(require_admin)])


def _staff(request: Request) -> None:
    if request.state.admin_role not in {"admin", "manager"}:
        raise HTTPException(403)


async def _lock(request: Request, session: AsyncSession) -> None:
    await session.rollback()
    await session.execute(text("BEGIN IMMEDIATE"))
    await require_admin(request, request.cookies.get(SESSION_COOKIE), session)


def _back(request: Request, path: str, key: str, *, error: bool = False) -> RedirectResponse:
    request.session["flash_message"] = translate(request, key)
    request.session["flash_type"] = "error" if error else "success"
    return RedirectResponse(path, status_code=303)


def _context(request: Request) -> dict:
    return {"admin_user": request.state.admin_user,
            "flash_message": request.session.pop("flash_message", None),
            "flash_type": request.session.pop("flash_type", "success")}


@router.get("/review")
async def review_list(request: Request, session: AsyncSession = Depends(get_db), page: int = Query(1, ge=1)):
    _staff(request)
    filters = (Download.publication_pending.is_(True), Download.deleted_at.is_(None))
    count = await session.scalar(select(func.count()).select_from(Download).where(*filters)) or 0
    pages = max(1, (count + 19) // 20)
    if page > pages:
        return RedirectResponse(f"/panel/review?page={pages}", status_code=303)
    items = list(await session.scalars(select(Download).where(*filters).order_by(Download.updated_at, Download.id).offset((page - 1) * 20).limit(20)))
    return templates.TemplateResponse(request=request, name="admin/review.html", context={
        **_context(request), "items": items, "page": page, "pages": pages,
    })


@router.post("/review/{download_id}")
async def review_content(
    download_id: int, request: Request, action: str = Form(...), reason: str = Form("", max_length=1000),
    revision: str = Form(..., max_length=40),
    session: AsyncSession = Depends(get_db),
):
    await _lock(request, session)
    _staff(request)
    item = await session.scalar(select(Download).where(Download.id == download_id, Download.publication_pending.is_(True), Download.deleted_at.is_(None)))
    if item is None:
        raise HTTPException(404)
    if revision != item.updated_at.isoformat():
        return _back(request, "/panel/review", "review_changed", error=True)
    if action not in {"approve", "reject"} or (action == "reject" and not reason.strip()):
        return _back(request, "/panel/review", "review_reason_required", error=True)
    item.publication_pending = False
    item.publication_feedback = reason.strip() or None
    item.is_active = action == "approve"
    item.is_draft = action == "reject"
    item.draft_token = secrets.token_urlsafe(24) if item.is_draft else None
    add_event(session, action, "publication", "Editorial review completed", item.id)
    await session.commit()
    return _back(request, "/panel/review", "review_saved")


@router.get("/contact")
async def contact_list(request: Request, session: AsyncSession = Depends(get_db), page: int = Query(1, ge=1)):
    query = select(EditorMessage)
    count_query = select(func.count()).select_from(EditorMessage)
    if request.state.admin_role == "editor":
        query = query.where(EditorMessage.sender_id == request.state.admin_id)
        count_query = count_query.where(EditorMessage.sender_id == request.state.admin_id)
    count = await session.scalar(count_query) or 0
    pages = max(1, (count + 19) // 20)
    if page > pages:
        return RedirectResponse(f"/panel/contact?page={pages}", status_code=303)
    items = list(await session.scalars(query.order_by(EditorMessage.created_at.desc(), EditorMessage.id.desc()).offset((page - 1) * 20).limit(20)))
    return templates.TemplateResponse(request=request, name="admin/contact.html", context={
        **_context(request), "items": items, "page": page, "pages": pages,
    })


@router.post("/contact")
async def send_message(
    request: Request, subject: str = Form(..., max_length=150), body: str = Form(..., max_length=5000),
    session: AsyncSession = Depends(get_db),
):
    await _lock(request, session)
    if request.state.admin_role != "editor":
        raise HTTPException(403)
    if not subject.strip() or not body.strip():
        return _back(request, "/panel/contact", "contact_invalid", error=True)
    count = await session.scalar(select(func.count()).select_from(EditorMessage).where(
        EditorMessage.sender_id == request.state.admin_id,
        EditorMessage.created_at >= datetime.now(timezone.utc) - timedelta(hours=1),
    )) or 0
    if count >= 5:
        await session.rollback()
        return _back(request, "/panel/contact", "contact_limited", error=True)
    item = EditorMessage(sender_id=request.state.admin_id, subject=subject.strip(), body=body.strip())
    session.add(item)
    await session.flush()
    add_event(session, "create", "contact", "Editor message submitted", item.id)
    await session.commit()
    return _back(request, "/panel/contact", "contact_sent")


@router.post("/contact/{message_id}/reply")
async def reply_message(
    message_id: int, request: Request, response: str = Form(..., max_length=5000),
    session: AsyncSession = Depends(get_db),
):
    await _lock(request, session)
    _staff(request)
    item = await session.get(EditorMessage, message_id)
    if item is None:
        raise HTTPException(404)
    if not response.strip():
        return _back(request, "/panel/contact", "contact_invalid", error=True)
    if item.response is not None:
        return _back(request, "/panel/contact", "contact_already_answered", error=True)
    item.response = response.strip()
    item.responded_by = request.state.admin_id
    item.responded_at = datetime.now(timezone.utc)
    add_event(session, "update", "contact", "Editor message answered", item.id)
    await session.commit()
    return _back(request, "/panel/contact", "contact_answered")

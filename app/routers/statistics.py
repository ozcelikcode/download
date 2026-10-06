"""Aggregate statistics without visitor tracking or editor data exposure."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.database import get_db
from app.dependencies import require_admin
from app.models import Category, Download
from app.templating import templates

router = APIRouter(prefix='/panel/statistics', dependencies=[Depends(require_admin)])


@router.get('')
async def statistics(request: Request, session: AsyncSession = Depends(get_db)):
    stats = await crud.get_dashboard_stats(session)
    published = (Download.deleted_at.is_(None), Download.is_active.is_(True),
                 Download.is_hidden.is_(False), Download.is_draft.is_(False), Download.publication_pending.is_(False))
    leaders = list((await session.execute(select(Download.title, Download.slug, Download.download_count)
                   .where(*published).order_by(Download.download_count.desc(), Download.id).limit(10))).all())
    categories = list((await session.execute(select(Category.name, func.count(Download.id))
                      .join(Download, Download.category_id == Category.id).where(*published, Download.parent_id.is_(None))
                      .group_by(Category.id).order_by(func.count(Download.id).desc(), Category.name).limit(15))).all())
    return templates.TemplateResponse(request=request, name='admin/statistics.html', context={
        'request': request, 'admin_user': request.state.admin_user, 'stats': stats,
        'leaders': leaders, 'categories': categories,
        'download_max': max([row[2] for row in leaders] + [1]),
        'category_max': max([row[1] for row in categories] + [1]),
    })

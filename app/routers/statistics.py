"""Aggregate statistics without visitor tracking or editor data exposure."""

import platform
from importlib.metadata import version

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.database import get_db
from app.dependencies import require_admin
from app.models import BackupPolicy, Category, Download, Page, Tag, User, MediaAsset, RegistrationRequest
from app.templating import templates
from app.i18n import translate

router = APIRouter(prefix='/panel', dependencies=[Depends(require_admin)])


@router.get('/statistics')
@router.get('/site-information')
async def statistics(request: Request, session: AsyncSession = Depends(get_db)) -> Response:
    if request.state.admin_role != 'admin':
        raise HTTPException(403, translate(request, 'permission_denied'))
    stats = await crud.get_dashboard_stats(session)
    published = (Download.deleted_at.is_(None), Download.is_active.is_(True),
                 Download.is_hidden.is_(False), Download.is_draft.is_(False), Download.publication_pending.is_(False))
    leaders = list((await session.execute(select(Download.title, Download.slug, Download.download_count)
                   .where(*published).order_by(Download.download_count.desc(), Download.id).limit(10))).all())
    categories = list((await session.execute(select(Category.name, func.count(Download.id))
                      .join(Download, Download.category_id == Category.id).where(*published, Download.parent_id.is_(None))
                      .group_by(Category.id).order_by(func.count(Download.id).desc(), Category.name).limit(15))).all())
    policy = await crud.get_site_settings(session)
    runtime = [('Python', platform.python_version())] + [(name, version(name)) for name in ('FastAPI', 'SQLAlchemy', 'Jinja2', 'Pydantic', 'Alembic', 'Uvicorn')]
    runtime.append(('site_storage_engine', 'SQLite ' + await session.scalar(text('SELECT sqlite_version()'))))
    runtime.append(('site_database_mode', (await session.scalar(text('PRAGMA journal_mode'))).upper()))
    runtime.append(('site_operating_system', {'Darwin': 'macOS'}.get(platform.system(), platform.system())))
    # The table may be absent in an isolated create_all test database.
    has_revision = await session.scalar(text("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='alembic_version'"))
    if has_revision:
        runtime.append(('site_database_revision', ', '.join((await session.scalars(text('SELECT version_num FROM alembic_version'))).all())))
    runtime.extend([('site_frontend', 'Jinja2 / Tailwind CSS 3.4.19'), ('site_icons', 'Lucide 1.24.0')])
    inventory = []
    for label, model in [('users', User), ('categories', Category), ('tags', Tag), ('pages', Page), ('media_archive', MediaAsset), ('registration_requests', RegistrationRequest)]:
        inventory.append((label, await session.scalar(select(func.count()).select_from(model))))
    inventory.append(('site_active_accounts', await session.scalar(select(func.count(User.id)).where(User.is_active.is_(True), User.deleted_at.is_(None)))))
    for label, condition in [('draft', Download.is_draft.is_(True)), ('review_title', Download.publication_pending.is_(True)), ('trash', Download.deleted_at.is_not(None))]:
        inventory.append((label, await session.scalar(select(func.count(Download.id)).where(condition))))
    backup_policy = await session.get(BackupPolicy, 1)
    disabled_label = translate(request, 'site_retention_disabled')
    compression_labels = ('compression_minimum', 'compression_low', 'compression_medium', 'compression_high', 'compression_ultra')
    configuration = [('site_name', policy.site_name), ('site_language', policy.site_language.upper()),
                     ('timezone_title', policy.site_timezone),
                     ('site_editor_quota', f'{policy.editor_media_quota_mb} MB'),
                     ('site_manager_quota', f'{policy.manager_media_quota_mb} MB'),
                     ('site_session_minutes', policy.session_max_age_minutes),
                     ('site_audit_limit', policy.audit_log_max_records),
                     ('compression_title', translate(request, compression_labels[min(4, max(0, policy.image_compression_level))]) if policy.image_compression_enabled else disabled_label),
                     ('trash_retention', translate(request, 'retention_days').format(days=policy.trash_retention_days) if policy.trash_retention_days else disabled_label),
                     ('backup_schedule', translate(request, 'backup_every').format(days=backup_policy.interval_days) if backup_policy and backup_policy.enabled else disabled_label)]
    return templates.TemplateResponse(request=request, name='admin/statistics.html', context={
        'request': request, 'admin_user': request.state.admin_user, 'stats': stats,
        'leaders': leaders, 'categories': categories,
        'download_max': max([row[2] for row in leaders] + [1]),
        'category_max': max([row[1] for row in categories] + [1]),
        'runtime': runtime, 'inventory': inventory, 'configuration': configuration,
    })

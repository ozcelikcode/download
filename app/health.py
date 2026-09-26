"""Admin dashboard için içerik ve depolama sağlık denetimleri."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, Literal

from sqlalchemy import and_, func, select
from sqlalchemy.sql import Select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.content_security import rich_text_to_plain_text
from app.media import media_usage
from app.models import Category, Download, FileType, LinkCheck, SiteSettings
from app.seo import inspect_public_base_url
from app.schemas import (
    AdminHealthSummary,
    AdminSiteHealth,
    HealthCheck,
    HealthFinding,
    HealthItem,
)

logger = logging.getLogger(__name__)
HealthSeverity = Literal["critical", "warning", "info"]

_IGNORED_STORAGE_NAMES = {".gitkeep"}


def _local_file_is_missing(value: str | None, root: Path) -> bool:
    if not value:
        return True
    try:
        candidate = Path(value).resolve()
        return (
            candidate == root
            or not candidate.is_relative_to(root)
            or not candidate.is_file()
        )
    except (OSError, RuntimeError):
        return True


def _storage_files(root: Path) -> list[Path]:
    """Kök dışına çıkan sembolik bağlantıları izlemeden gerçek dosyaları döndür."""
    try:
        root = root.resolve()
        candidates = root.rglob("*")
        files: list[Path] = []
        for candidate in candidates:
            if candidate.name in _IGNORED_STORAGE_NAMES or candidate.name.startswith(".upload-"):
                continue
            try:
                resolved = candidate.resolve()
                if resolved.is_relative_to(root) and resolved.is_file():
                    files.append(resolved)
            except (OSError, RuntimeError) as exc:
                logger.warning("Depolama girdisi okunamadı: path=%s error=%s", candidate, exc)
        return files
    except (OSError, RuntimeError) as exc:
        logger.warning("Depolama dizini taranamadı: path=%s error=%s", root, exc)
        return []


def _scan_filesystem(
    local_paths: Iterable[str | None],
    used_paths: set[Path],
) -> tuple[int, int, int, int]:
    """Eksik yerel kayıtları, kullanılmayan medyayı ve depo boyutunu hesapla."""
    private_root = settings.download_path.resolve()
    icon_root = (settings.upload_path / "icons").resolve()

    missing_local_files = sum(
        _local_file_is_missing(value, private_root) for value in local_paths
    )

    private_files = _storage_files(private_root)
    icon_files = _storage_files(icon_root)
    normalized_usage = {path.resolve() for path in used_paths}
    unused_media = sum(
        path not in normalized_usage for path in (*private_files, *icon_files)
    )

    private_storage_bytes = 0
    for path in private_files:
        try:
            private_storage_bytes += path.stat().st_size
        except OSError as exc:
            logger.warning("Dosya boyutu okunamadı: path=%s error=%s", path, exc)

    return (
        missing_local_files,
        unused_media,
        private_storage_bytes,
        len(private_files),
    )


async def get_admin_health(session: AsyncSession) -> AdminHealthSummary:
    """Dashboard için veritabanı ve dosya sistemi sağlık özetini üret."""
    broken_links = await session.scalar(
        select(func.count())
        .select_from(LinkCheck)
        .join(Download, Download.id == LinkCheck.download_id)
        .where(
            LinkCheck.status == "broken",
            LinkCheck.url == Download.external_url,
            Download.file_type == FileType.external,
        )
    )
    uncategorized_content = await session.scalar(
        select(func.count()).select_from(Download).where(
            Download.parent_id.is_(None),
            Download.category_id.is_(None),
            Download.is_active.is_(True),
            Download.is_draft.is_(False),
        )
    )
    local_paths = list(
        (
            await session.scalars(
                select(Download.file_path).where(
                    Download.parent_id.is_(None),
                    Download.file_type == FileType.local,
                    Download.is_draft.is_(False),
                )
            )
        ).all()
    )
    used_paths = set((await media_usage(session)).keys())
    missing, unused, storage_bytes, file_count = await run_in_threadpool(
        _scan_filesystem, local_paths, used_paths
    )

    return AdminHealthSummary(
        broken_links=broken_links or 0,
        missing_local_files=missing,
        unused_media=unused,
        uncategorized_content=uncategorized_content or 0,
        private_storage_bytes=storage_bytes,
        private_file_count=file_count,
    )


def _missing_download_rows(
    rows: list[tuple[int, str, str | None]],
) -> list[tuple[int, str]]:
    """Özel depoda karşılığı olmayan yerel kayıtları bulur."""
    root = settings.download_path.resolve()
    missing: list[tuple[int, str]] = []
    for download_id, title, value in rows:
        if _local_file_is_missing(value, root):
            missing.append((download_id, title))
    return missing


async def _finding_from_query(
    session: AsyncSession,
    *,
    key: str,
    severity: HealthSeverity,
    href: str,
    statement: Select,
) -> HealthFinding:
    """Sayımı ve düzeltilebilir ilk kayıtları tek bulguya dönüştür."""
    count = await session.scalar(
        select(func.count()).select_from(statement.order_by(None).subquery())
    )
    rows = (await session.execute(statement.order_by(None).limit(8))).all()
    items = [
        HealthItem(
            title=row.title,
            href=f"/admin/downloads/{row.id}/edit",
            detail=getattr(row, "message", None),
        )
        for row in rows
    ]
    return HealthFinding(
        key=key,
        severity=severity,
        count=count or 0,
        href=href,
        items=items,
    )


async def get_admin_site_health(session: AsyncSession) -> AdminSiteHealth:
    """Teknik bakım ve SEO için admin ekranında gösterilecek bulguları üret."""
    summary = await get_admin_health(session)
    technical: list[HealthFinding] = []
    seo: list[HealthFinding] = []

    broken_links = select(
        Download.id,
        Download.title,
        LinkCheck.message,
    ).join(
        LinkCheck,
        and_(
            LinkCheck.download_id == Download.id,
            LinkCheck.url == Download.external_url,
            LinkCheck.status == "broken",
        ),
    )
    if summary.broken_links:
        technical.append(await _finding_from_query(
            session,
            key="broken_links",
            severity="critical",
            href="/admin/links?state=broken",
            statement=broken_links,
        ))

    local_rows = (
        await session.execute(
            select(Download.id, Download.title, Download.file_path).where(
                Download.parent_id.is_(None),
                Download.file_type == FileType.local,
                Download.is_draft.is_(False),
            )
        )
    ).all()
    missing_rows = await run_in_threadpool(
        _missing_download_rows,
        [(row.id, row.title, row.file_path) for row in local_rows],
    )
    if missing_rows:
        technical.append(HealthFinding(
            key="missing_files",
            severity="critical",
            count=len(missing_rows),
            href="/admin/downloads?file_type_filter=local",
            items=[
                HealthItem(title=title, href=f"/admin/downloads/{download_id}/edit")
                for download_id, title in missing_rows[:8]
            ],
        ))

    uncategorized = select(
        Download.id, Download.title
    ).where(
        Download.parent_id.is_(None),
        Download.category_id.is_(None),
        Download.is_active.is_(True),
        Download.is_draft.is_(False),
    )
    if summary.uncategorized_content:
        technical.append(await _finding_from_query(
            session,
            key="uncategorized",
            severity="warning",
            href="/admin/downloads?category_id=uncategorized",
            statement=uncategorized,
        ))

    if summary.unused_media:
        technical.append(HealthFinding(
            key="unused_media",
            severity="info",
            count=summary.unused_media,
            href="/admin/media",
        ))

    draft_statement = select(Download.id, Download.title).where(
        Download.is_draft.is_(True)
    )
    draft_count = await session.scalar(
        select(func.count()).select_from(draft_statement.subquery())
    ) or 0
    if draft_count:
        technical.append(await _finding_from_query(
            session,
            key="drafts",
            severity="info",
            href="/admin/downloads?status_filter=draft",
            statement=draft_statement,
        ))

    public_downloads = (
        await session.execute(
            select(
                Download.id,
                Download.title,
                Download.version,
                Download.description,
                Download.short_description,
            )
            .where(
                Download.is_active.is_(True),
                Download.is_draft.is_(False),
            )
            .order_by(Download.title)
        )
    ).all()
    without_description = [
        row for row in public_downloads
        if not (row.short_description or "").strip()
        and not rich_text_to_plain_text(row.description or "").strip()
    ]
    if without_description:
        seo.append(HealthFinding(
            key="seo_missing_description",
            severity="warning",
            count=len(without_description),
            href="/admin/downloads",
            items=[
                HealthItem(title=row.title, href=f"/admin/downloads/{row.id}/edit")
                for row in without_description[:8]
            ],
        ))

    site_name = (
        await session.scalar(select(SiteSettings.site_name).limit(1))
        or settings.app_name
    )
    long_title_rows = [
        row
        for row in public_downloads
        if len(f"{row.title} {row.version or ''} — {site_name}".strip()) > 60
    ]
    if long_title_rows:
        seo.append(HealthFinding(
            key="seo_long_titles",
            severity="info",
            count=len(long_title_rows),
            href="/admin/downloads",
            items=[
                HealthItem(title=row.title, href=f"/admin/downloads/{row.id}/edit")
                for row in long_title_rows[:8]
            ],
        ))

    public_category_ids = select(Download.category_id).where(
        Download.parent_id.is_(None),
        Download.category_id.is_not(None),
        Download.is_active.is_(True),
        Download.is_draft.is_(False),
    )
    category_statement = select(Category.id, Category.name).where(
        func.trim(func.coalesce(Category.description, "")) == "",
        Category.id.in_(public_category_ids),
    )
    category_count = await session.scalar(
        select(func.count()).select_from(category_statement.subquery())
    ) or 0
    if category_count:
        category_rows = (await session.execute(category_statement.order_by(Category.name).limit(8))).all()
        seo.append(HealthFinding(
            key="seo_category_descriptions",
            severity="info",
            count=category_count,
            href="/admin/categories",
            items=[
                HealthItem(title=row.name, href="/admin/categories")
                for row in category_rows
            ],
        ))

    long_category_statement = select(Category.id, Category.name).where(
        func.length(func.trim(func.coalesce(Category.description, ""))) > 160,
        Category.id.in_(public_category_ids),
    )
    long_category_count = await session.scalar(
        select(func.count()).select_from(long_category_statement.subquery())
    ) or 0
    if long_category_count:
        long_category_rows = (
            await session.execute(
                long_category_statement.order_by(Category.name).limit(8)
            )
        ).all()
        seo.append(HealthFinding(
            key="seo_long_category_descriptions",
            severity="info",
            count=long_category_count,
            href="/admin/categories",
            items=[
                HealthItem(
                    title=row.name,
                    href=f"/admin/categories#cat-view-{row.id}",
                )
                for row in long_category_rows
            ],
        ))

    _, base_status, base_detail = inspect_public_base_url()
    public_url_status = "ok" if base_status == "info" else base_status
    url_detail = base_detail if public_url_status != "ok" else None
    checks = [
        HealthCheck(key="metadata", status="ok", href="/"),
        HealthCheck(
            key="canonical", status=public_url_status, detail=url_detail, href="/"
        ),
        HealthCheck(
            key="sitemap", status=public_url_status, detail=url_detail, href="/sitemap.xml"
        ),
        HealthCheck(
            key="robots", status=public_url_status, detail=url_detail, href="/robots.txt"
        ),
        HealthCheck(key="base_url", status=base_status, detail=base_detail),
    ]
    return AdminSiteHealth(
        summary=summary,
        technical_findings=technical,
        seo_findings=seo,
        checks=checks,
    )

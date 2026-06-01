"""
Async CRUD operasyonları.

Her fonksiyon bir AsyncSession alır ve await ile çalışır.
Dış slug üretimi python-slugify ile yapılır.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from slugify import slugify
from sqlalchemy import func, or_, select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Category, Download, DownloadLog, DownloadTag, FileType, IconType, Tag
from app.schemas import (
    CategoryCreate,
    CategoryUpdate,
    DownloadCreate,
    DownloadUpdate,
    TagCreate,
)

logger = logging.getLogger(__name__)


# ===========================================================================
# Slug yardımcıları
# ===========================================================================

def _make_slug(text: str) -> str:
    return slugify(text, allow_unicode=False, separator="-")


async def _unique_slug(
    session: AsyncSession,
    model,
    base_slug: str,
    exclude_id: Optional[int] = None,
) -> str:
    """Çakışma varsa sonuna -2, -3 … ekleyerek eşsiz slug üretir."""
    slug = base_slug
    counter = 1
    while True:
        stmt = select(model).where(model.slug == slug)
        if exclude_id:
            stmt = stmt.where(model.id != exclude_id)
        result = await session.execute(stmt)
        if result.scalar_one_or_none() is None:
            return slug
        counter += 1
        slug = f"{base_slug}-{counter}"


# ===========================================================================
# Category CRUD
# ===========================================================================

async def get_categories(session: AsyncSession) -> List[Category]:
    result = await session.execute(select(Category).order_by(Category.name))
    return list(result.scalars().all())


async def get_category_by_slug(session: AsyncSession, slug: str) -> Optional[Category]:
    result = await session.execute(select(Category).where(Category.slug == slug))
    return result.scalar_one_or_none()


async def get_category_by_id(session: AsyncSession, category_id: int) -> Optional[Category]:
    result = await session.execute(select(Category).where(Category.id == category_id))
    return result.scalar_one_or_none()


async def create_category(session: AsyncSession, data: CategoryCreate) -> Category:
    base_slug = data.slug or _make_slug(data.name)
    slug = await _unique_slug(session, Category, base_slug)
    category = Category(name=data.name, slug=slug, description=data.description)
    session.add(category)
    await session.commit()
    await session.refresh(category)
    logger.info("Kategori oluşturuldu: id=%d slug=%r", category.id, category.slug)
    return category


async def update_category(
    session: AsyncSession, category: Category, data: CategoryUpdate
) -> Category:
    if data.name is not None:
        category.name = data.name
    if data.description is not None:
        category.description = data.description
    if data.slug is not None:
        slug = await _unique_slug(session, Category, data.slug, exclude_id=category.id)
        category.slug = slug
    await session.commit()
    await session.refresh(category)
    logger.info("Kategori güncellendi: id=%d", category.id)
    return category


async def delete_category(session: AsyncSession, category: Category) -> None:
    await session.delete(category)
    await session.commit()
    logger.info("Kategori silindi: id=%d", category.id)


# ===========================================================================
# Tag CRUD
# ===========================================================================

async def get_tags(session: AsyncSession) -> List[Tag]:
    result = await session.execute(select(Tag).order_by(Tag.name))
    return list(result.scalars().all())


async def get_tag_by_slug(session: AsyncSession, slug: str) -> Optional[Tag]:
    result = await session.execute(select(Tag).where(Tag.slug == slug))
    return result.scalar_one_or_none()


async def get_tag_by_id(session: AsyncSession, tag_id: int) -> Optional[Tag]:
    result = await session.execute(select(Tag).where(Tag.id == tag_id))
    return result.scalar_one_or_none()


async def get_or_create_tag(session: AsyncSession, name: str) -> Tag:
    slug = _make_slug(name)
    result = await session.execute(select(Tag).where(Tag.slug == slug))
    tag = result.scalar_one_or_none()
    if tag is None:
        tag = Tag(name=name, slug=slug)
        session.add(tag)
        await session.commit()
        await session.refresh(tag)
        logger.info("Tag oluşturuldu: id=%d name=%r", tag.id, tag.name)
    return tag


async def create_tag(session: AsyncSession, data: TagCreate) -> Tag:
    slug = data.slug or _make_slug(data.name)
    slug = await _unique_slug(session, Tag, slug)
    tag = Tag(name=data.name, slug=slug)
    session.add(tag)
    await session.commit()
    await session.refresh(tag)
    return tag


async def delete_tag(session: AsyncSession, tag: Tag) -> None:
    await session.delete(tag)
    await session.commit()


# ===========================================================================
# Download CRUD
# ===========================================================================

def _download_base_query():
    """Eager load ile temel sorgu — N+1 sorununu önler."""
    return (
        select(Download)
        .options(
            selectinload(Download.category),
            selectinload(Download.tags),
        )
        .where(Download.is_active == True)  # noqa: E712
    )


async def get_downloads_paginated(
    session: AsyncSession,
    page: int = 1,
    page_size: int = 12,
    category_slug: Optional[str] = None,
    tag_slug: Optional[str] = None,
    search: Optional[str] = None,
    featured_only: bool = False,
    include_inactive: bool = False,
) -> Tuple[List[Download], int]:
    """
    Sayfalandırılmış indirme listesi döndürür.
    Dönüş: (items, total_count)
    """
    stmt = _download_base_query()

    # Admin modunda inaktif kayıtlar da gösterilir
    if include_inactive:
        # _download_base_query'nin is_active filtresini override et
        stmt = (
            select(Download)
            .options(
                selectinload(Download.category),
                selectinload(Download.tags),
            )
        )

    # Yalnızca üst seviye kayıtları getir (parent_id=NULL)
    stmt = stmt.where(Download.parent_id == None)  # noqa: E711

    if featured_only:
        stmt = stmt.where(Download.is_featured == True)  # noqa: E712

    if category_slug:
        stmt = stmt.join(Category, Download.category_id == Category.id).where(
            Category.slug == category_slug
        )

    if tag_slug:
        stmt = stmt.join(DownloadTag, Download.id == DownloadTag.download_id).join(
            Tag, DownloadTag.tag_id == Tag.id
        ).where(Tag.slug == tag_slug)

    if search:
        term = f"%{search}%"
        stmt = stmt.where(Download.title.ilike(term))

    # Toplam sayım
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await session.execute(count_stmt)
    total = total_result.scalar_one()

    # Sayfalama
    offset = (page - 1) * page_size
    stmt = stmt.order_by(Download.is_featured.desc(), Download.created_at.desc())
    stmt = stmt.offset(offset).limit(page_size)

    result = await session.execute(stmt)
    items = list(result.scalars().all())
    return items, total


async def get_download_by_slug(
    session: AsyncSession, slug: str
) -> Optional[Download]:
    """Detay sayfası için — sürümler de yüklenir."""
    stmt = (
        select(Download)
        .options(
            selectinload(Download.category),
            selectinload(Download.tags),
            selectinload(Download.versions).options(
                selectinload(Download.tags)
            ),
            selectinload(Download.parent),
        )
        .where(Download.slug == slug, Download.is_active == True)  # noqa: E712
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_download_by_id(
    session: AsyncSession, download_id: int
) -> Optional[Download]:
    stmt = (
        select(Download)
        .options(
            selectinload(Download.category),
            selectinload(Download.tags),
        )
        .where(Download.id == download_id)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def create_download(
    session: AsyncSession, data: DownloadCreate
) -> Download:
    # Slug üret
    base_slug = data.slug or _make_slug(data.title)
    slug = await _unique_slug(session, Download, base_slug)

    # icon_type otomatik belirleme
    icon_type = data.icon_type
    if icon_type == IconType.auto:
        icon_type = _infer_icon_type(data)

    # os_compatibility listesini stringe çevir
    os_str: Optional[str] = None
    if data.os_compatibility:
        os_str = ",".join(data.os_compatibility)

    download = Download(
        title=data.title,
        slug=slug,
        description=data.description,
        version=data.version,
        file_type=data.file_type,
        file_path=data.file_path,
        external_url=str(data.external_url) if data.external_url else None,
        file_size_bytes=data.file_size_bytes,
        icon_type=icon_type,
        thumbnail_path=data.thumbnail_path,
        icon_image_path=data.icon_image_path,
        icon_image_url=data.icon_image_url,
        os_compatibility=os_str,
        category_id=data.category_id,
        parent_id=data.parent_id,
        is_active=data.is_active,
        is_featured=data.is_featured,
    )
    session.add(download)
    await session.flush()  # id almak için

    # Tag ilişkileri
    if data.tag_ids:
        await _sync_tags(session, download, data.tag_ids)

    await session.commit()
    await session.refresh(download)
    logger.info("Download oluşturuldu: id=%d slug=%r", download.id, download.slug)
    return download


async def update_download(
    session: AsyncSession, download: Download, data: DownloadUpdate
) -> Download:
    update_data = data.model_dump(exclude_unset=True, exclude={"tag_ids"})

    if "slug" in update_data and update_data["slug"]:
        update_data["slug"] = await _unique_slug(
            session, Download, update_data["slug"], exclude_id=download.id
        )

    if "external_url" in update_data and update_data["external_url"]:
        update_data["external_url"] = str(update_data["external_url"])

    # icon_type otomatik yeniden belirle
    if "icon_type" in update_data and update_data["icon_type"] == IconType.auto:
        # Güncel değerleri al
        ft = update_data.get("file_type", download.file_type)
        eu = update_data.get("external_url", download.external_url)
        fp = update_data.get("file_path", download.file_path)
        update_data["icon_type"] = _infer_icon_type_from_values(ft, eu, fp)

    # os_compatibility listesini stringe çevir ve güncelle
    if data.os_compatibility is not None:
        update_data["os_compatibility"] = ",".join(data.os_compatibility) if data.os_compatibility else None

    for field, value in update_data.items():
        if field != "os_compatibility":  # yukarıda zaten işlendi
            setattr(download, field, value)
    if "os_compatibility" in update_data:
        download.os_compatibility = update_data["os_compatibility"]

    if data.tag_ids is not None:
        await _sync_tags(session, download, data.tag_ids)

    await session.commit()
    await session.refresh(download)
    logger.info("Download güncellendi: id=%d", download.id)
    return download


async def delete_download(session: AsyncSession, download: Download) -> None:
    await session.delete(download)
    await session.commit()
    logger.info("Download silindi: id=%d slug=%r", download.id, download.slug)


async def increment_download_count(
    session: AsyncSession, download_id: int
) -> None:
    """Download sayacını atomik olarak artırır."""
    from sqlalchemy import update as sa_update

    stmt = (
        sa_update(Download)
        .where(Download.id == download_id)
        .values(download_count=Download.download_count + 1)
    )
    await session.execute(stmt)
    await session.commit()


# ===========================================================================
# DownloadLog CRUD (Rate Limiting)
# ===========================================================================

async def create_download_log(
    session: AsyncSession,
    download_id: int,
    ip_address: str,
    user_agent: Optional[str] = None,
) -> DownloadLog:
    log = DownloadLog(
        download_id=download_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    session.add(log)
    await session.commit()
    return log


async def check_rate_limit(
    session: AsyncSession,
    ip_address: str,
    max_per_hour: int,
) -> bool:
    """
    True → indirmeye izin ver.
    False → rate limit aşıldı.
    """
    window_start = datetime.now(timezone.utc) - timedelta(hours=1)
    stmt = select(func.count()).where(
        DownloadLog.ip_address == ip_address,
        DownloadLog.downloaded_at >= window_start,
    )
    result = await session.execute(stmt)
    count = result.scalar_one()
    return count < max_per_hour


# ===========================================================================
# Kategori bazlı istatistik
# ===========================================================================

async def get_category_download_counts(
    session: AsyncSession,
) -> dict[int, int]:
    """Her kategorinin aktif indirme sayısını döndürür."""
    stmt = (
        select(Download.category_id, func.count(Download.id))
        .where(Download.is_active == True, Download.parent_id == None)  # noqa: E711, E712
        .group_by(Download.category_id)
    )
    result = await session.execute(stmt)
    return {row[0]: row[1] for row in result if row[0] is not None}


# ===========================================================================
# İkon yardımcıları
# ===========================================================================

def _infer_icon_type(data: DownloadCreate) -> IconType:
    return _infer_icon_type_from_values(
        data.file_type,
        str(data.external_url) if data.external_url else None,
        data.file_path,
    )


def _infer_icon_type_from_values(
    file_type: FileType,
    external_url: Optional[str],
    file_path: Optional[str],
) -> IconType:
    EXT_MAP = {
        "zip": IconType.zip, "gz": IconType.zip, "tar": IconType.zip,
        "7z": IconType.zip, "rar": IconType.zip,
        "pdf": IconType.pdf,
        "exe": IconType.exe, "msi": IconType.exe,
        "apk": IconType.apk,
        "dmg": IconType.dmg, "pkg": IconType.dmg,
        "deb": IconType.deb, "rpm": IconType.deb,
        "png": IconType.image, "jpg": IconType.image,
        "jpeg": IconType.image, "svg": IconType.image, "gif": IconType.image,
    }

    # Lokal dosya: uzantıya bak
    if file_type == FileType.local and file_path:
        ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
        return EXT_MAP.get(ext, IconType.link)

    # Dış URL: URL'nin sonundaki uzantıya bak
    if file_type == FileType.external and external_url:
        # query string'i at, sadece path
        from urllib.parse import urlparse
        path = urlparse(external_url).path
        ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
        detected = EXT_MAP.get(ext)
        if detected:
            return detected

    return IconType.link


# ===========================================================================
# Tag sync (iç yardımcı)
# ===========================================================================

async def _sync_tags(
    session: AsyncSession, download: Download, tag_ids: List[int]
) -> None:
    """Download'ın tag ilişkilerini verilen id listesiyle eşitler."""
    # Mevcut junction kayıtlarını sil
    await session.execute(
        delete(DownloadTag).where(DownloadTag.download_id == download.id)
    )
    # Yenilerini ekle
    for tag_id in tag_ids:
        session.add(DownloadTag(download_id=download.id, tag_id=tag_id))
    await session.flush()

"""
Async CRUD operasyonları.

Her fonksiyon bir AsyncSession alır ve await ile çalışır.
Dış slug üretimi python-slugify ile yapılır.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from slugify import slugify
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Category,
    Download,
    DownloadLog,
    DownloadTag,
    DownloadVersionHistory,
    FileType,
    IconType,
    MediaAsset,
    MenuItem,
    SiteSettings,
    Tag,
)
from app.schemas import (
    CategoryCreate,
    CategoryUpdate,
    DownloadCreate,
    DownloadUpdate,
    MenuItemCreate,
    MenuItemUpdate,
    SiteSettingsUpdate,
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


async def get_categories_ordered(session: AsyncSession) -> List[Category]:
    """Sidebar'daki 'Kategori Menüsü' sırasına göre (position, sonra ad) döndürür."""
    result = await session.execute(select(Category).order_by(Category.position, Category.name))
    return list(result.scalars().all())


async def reorder_categories(session: AsyncSession, ordered_ids: List[int]) -> None:
    """Verilen id sırasına göre kategori position alanlarını 0'dan başlayarak yeniden yazar."""
    for position, cat_id in enumerate(ordered_ids):
        await session.execute(
            update(Category).where(Category.id == cat_id).values(position=position)
        )
    await session.commit()


# ===========================================================================
# Tag CRUD
# ===========================================================================

async def get_tags(session: AsyncSession) -> List[Tag]:
    result = await session.execute(select(Tag).order_by(Tag.name))
    return list(result.scalars().all())


async def get_tags_ordered(session: AsyncSession) -> List[Tag]:
    """Sidebar'daki 'Etiketler' sırasına göre (position, sonra ad) döndürür."""
    result = await session.execute(select(Tag).order_by(Tag.position, Tag.name))
    return list(result.scalars().all())


async def reorder_tags(session: AsyncSession, ordered_ids: List[int]) -> None:
    """Verilen id sırasına göre etiket position alanlarını 0'dan başlayarak yeniden yazar."""
    for position, tag_id in enumerate(ordered_ids):
        await session.execute(
            update(Tag).where(Tag.id == tag_id).values(position=position)
        )
    await session.commit()


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
# MenuItem CRUD
# ===========================================================================

async def get_menu_items(
    session: AsyncSession, active_only: bool = False, location: Optional[str] = None
) -> List[MenuItem]:
    stmt = select(MenuItem).order_by(MenuItem.position, MenuItem.id)
    if active_only:
        stmt = stmt.where(MenuItem.is_active.is_(True))
    if location:
        stmt = stmt.where(MenuItem.location == location)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_menu_item_by_id(session: AsyncSession, menu_item_id: int) -> Optional[MenuItem]:
    result = await session.execute(select(MenuItem).where(MenuItem.id == menu_item_id))
    return result.scalar_one_or_none()


async def create_menu_item(session: AsyncSession, data: MenuItemCreate) -> MenuItem:
    max_position = await session.scalar(
        select(func.max(MenuItem.position)).where(MenuItem.location == data.location)
    )
    item = MenuItem(
        label=data.label,
        url=data.url,
        icon=data.icon or None,
        is_active=data.is_active,
        open_in_new_tab=data.open_in_new_tab,
        location=data.location,
        position=(max_position or 0) + 1,
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)
    logger.info("Menü öğesi oluşturuldu: id=%d label=%r location=%r", item.id, item.label, item.location)
    return item


async def update_menu_item(
    session: AsyncSession, item: MenuItem, data: MenuItemUpdate
) -> MenuItem:
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(item, field, value)
    await session.commit()
    await session.refresh(item)
    logger.info("Menü öğesi güncellendi: id=%d", item.id)
    return item


async def delete_menu_item(session: AsyncSession, item: MenuItem) -> None:
    await session.delete(item)
    await session.commit()
    logger.info("Menü öğesi silindi: id=%d", item.id)


async def reorder_menu_items(session: AsyncSession, ordered_ids: List[int]) -> None:
    """Verilen id sırasına göre position alanlarını 0'dan başlayarak yeniden yazar."""
    for position, item_id in enumerate(ordered_ids):
        await session.execute(
            update(MenuItem).where(MenuItem.id == item_id).values(position=position)
        )
    await session.commit()


# ===========================================================================
# SiteSettings — tekil satır (site adı, ikon, ikon rengi)
# ===========================================================================

async def get_site_settings(session: AsyncSession) -> SiteSettings:
    """Tekil ayar satırını döndürür; yoksa varsayılan değerlerle oluşturur."""
    result = await session.execute(select(SiteSettings).limit(1))
    settings_row = result.scalar_one_or_none()
    if settings_row is None:
        settings_row = SiteSettings()
        session.add(settings_row)
        await session.commit()
        await session.refresh(settings_row)
    return settings_row


async def update_site_settings(
    session: AsyncSession, data: SiteSettingsUpdate
) -> SiteSettings:
    settings_row = await get_site_settings(session)
    settings_row.site_name = data.site_name
    settings_row.site_icon = data.site_icon
    settings_row.site_icon_color = data.site_icon_color
    await session.commit()
    await session.refresh(settings_row)
    logger.info("Site kimliği güncellendi: name=%r icon=%r color=%r",
                settings_row.site_name, settings_row.site_icon, settings_row.site_icon_color)
    return settings_row


async def update_sidebar_block_order(session: AsyncSession, order: List[str]) -> SiteSettings:
    """Sidebar blok sırasını ('search', 'categories', 'tags') günceller."""
    settings_row = await get_site_settings(session)
    settings_row.sidebar_block_order = ",".join(order)
    await session.commit()
    await session.refresh(settings_row)
    return settings_row


async def update_admin_credentials(
    session: AsyncSession, username: Optional[str], password_hash: Optional[str]
) -> SiteSettings:
    """Admin kullanıcı adı/şifre hash'ini DB'ye kaydeder (None → değiştirme)."""
    settings_row = await get_site_settings(session)
    if username:
        settings_row.admin_username = username
    if password_hash:
        settings_row.admin_password_hash = password_hash
    await session.commit()
    await session.refresh(settings_row)
    return settings_row


async def update_session_max_age(session: AsyncSession, minutes: int) -> SiteSettings:
    settings_row = await get_site_settings(session)
    settings_row.session_max_age_minutes = minutes
    await session.commit()
    await session.refresh(settings_row)
    return settings_row


async def update_admin_avatar(session: AsyncSession, icon: str, color: str) -> SiteSettings:
    settings_row = await get_site_settings(session)
    settings_row.admin_icon = icon
    settings_row.admin_icon_color = color
    await session.commit()
    await session.refresh(settings_row)
    return settings_row


# ===========================================================================
# DownloadVersionHistory — otomatik sürüm geçmişi düzenleme/silme (ekleme yok)
# ===========================================================================

async def get_version_history_entry(
    session: AsyncSession, entry_id: int
) -> Optional[DownloadVersionHistory]:
    result = await session.execute(
        select(DownloadVersionHistory).where(DownloadVersionHistory.id == entry_id)
    )
    return result.scalar_one_or_none()


async def update_version_history_entry(
    session: AsyncSession, entry: DownloadVersionHistory, version: str
) -> DownloadVersionHistory:
    entry.version = version
    await session.commit()
    await session.refresh(entry)
    return entry


async def delete_version_history_entry(
    session: AsyncSession, entry: DownloadVersionHistory
) -> None:
    await session.delete(entry)
    await session.commit()


# ===========================================================================
# MediaAsset — Medya Arşivi görünen ad meta verisi
# ===========================================================================

async def get_media_display_names(session: AsyncSession, paths: List[str]) -> dict[str, str]:
    """Verilen yollar için (varsa) özel görünen adları toplu olarak döndürür."""
    if not paths:
        return {}
    result = await session.execute(select(MediaAsset).where(MediaAsset.path.in_(paths)))
    return {row.path: row.display_name for row in result.scalars().all() if row.display_name}


async def get_media_assets_info(session: AsyncSession, paths: List[str]) -> dict[str, MediaAsset]:
    """Verilen yollar için tüm meta veriyi (görünen ad, yükleyen, tarih) toplu döndürür."""
    if not paths:
        return {}
    result = await session.execute(select(MediaAsset).where(MediaAsset.path.in_(paths)))
    return {row.path: row for row in result.scalars().all()}


async def record_media_upload(session: AsyncSession, path: str, uploaded_by: str) -> None:
    """Yeni bir dosya/görsel yüklendiğinde 'kim, ne zaman' bilgisini kaydeder.
    Kayıt zaten varsa (ör. daha önce yeniden adlandırılmışsa) yalnızca
    uploaded_by boşsa doldurur — mevcut görünen adı ezmez."""
    result = await session.execute(select(MediaAsset).where(MediaAsset.path == path))
    asset = result.scalar_one_or_none()
    if asset is None:
        session.add(MediaAsset(path=path, uploaded_by=uploaded_by))
    elif not asset.uploaded_by:
        asset.uploaded_by = uploaded_by
    await session.commit()


async def set_media_display_name(
    session: AsyncSession, path: str, display_name: Optional[str]
) -> None:
    """Bir dosya yolu için görünen adı ayarlar; boş verilirse özel adı kaldırır
    (varsayılan olarak fiziksel dosya adı gösterilmeye devam eder)."""
    display_name = (display_name or "").strip() or None
    result = await session.execute(select(MediaAsset).where(MediaAsset.path == path))
    asset = result.scalar_one_or_none()

    if asset is None:
        if display_name is None:
            return
        session.add(MediaAsset(path=path, display_name=display_name))
    elif display_name is None:
        asset.display_name = None
        if not asset.uploaded_by:
            await session.delete(asset)
    else:
        asset.display_name = display_name

    await session.commit()


async def delete_media_asset(session: AsyncSession, path: str) -> None:
    """Bir dosya silindiğinde ona ait görünen ad kaydını da temizler."""
    result = await session.execute(select(MediaAsset).where(MediaAsset.path == path))
    asset = result.scalar_one_or_none()
    if asset:
        await session.delete(asset)
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


async def get_all_downloads_for_media_matching(session: AsyncSession) -> List[Download]:
    """
    Medya Arşivi'ndeki bir dosya/görselin hangi indirmeye ait olduğunu bulmak
    için TÜM kayıtları (alt sürümler dahil, aktif/pasif ayrımı olmadan) döndürür.
    """
    result = await session.execute(select(Download))
    return list(result.scalars().all())


async def get_downloads_paginated(
    session: AsyncSession,
    page: int = 1,
    page_size: int = 12,
    category_slug: Optional[str] = None,
    category_id: Optional[int] = None,
    tag_slug: Optional[str] = None,
    search: Optional[str] = None,
    featured_only: bool = False,
    include_inactive: bool = False,
    status: Optional[str] = None,
    file_type_filter: Optional[str] = None,
    pin_featured: bool = True,
) -> Tuple[List[Download], int]:
    """
    Sayfalandırılmış indirme listesi döndürür.
    Dönüş: (items, total_count)

    `pin_featured=False` verilirse öne çıkan kayıtlar listenin başına
    sabitlenmez (yönetim panelindeki "İçerikler" listesi için kullanılır —
    sabitleme yalnızca sitede görünmeli, admin panelinde değil).
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

    if category_id:
        stmt = stmt.where(Download.category_id == category_id)

    if tag_slug:
        stmt = stmt.join(DownloadTag, Download.id == DownloadTag.download_id).join(
            Tag, DownloadTag.tag_id == Tag.id
        ).where(Tag.slug == tag_slug)

    if search:
        term = f"%{search}%"
        stmt = stmt.where(Download.title.ilike(term))

    if status == "active":
        stmt = stmt.where(Download.is_active == True)  # noqa: E712
    elif status == "inactive":
        stmt = stmt.where(Download.is_active == False)  # noqa: E712

    if file_type_filter:
        stmt = stmt.where(Download.file_type == FileType(file_type_filter))

    # Toplam sayım
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await session.execute(count_stmt)
    total = total_result.scalar_one()

    # Sayfalama
    offset = (page - 1) * page_size
    if pin_featured:
        stmt = stmt.order_by(Download.is_featured.desc(), Download.created_at.desc())
    else:
        stmt = stmt.order_by(Download.created_at.desc())
    stmt = stmt.offset(offset).limit(page_size)

    result = await session.execute(stmt)
    items = list(result.scalars().all())
    return items, total


async def get_dashboard_stats(session: AsyncSession) -> dict:
    """Dashboard'daki genel istatistik kartları için toplu sayım."""
    total_downloads = await session.scalar(
        select(func.count()).select_from(Download).where(Download.parent_id == None)  # noqa: E711
    )
    active_downloads = await session.scalar(
        select(func.count()).select_from(Download).where(
            Download.parent_id == None, Download.is_active == True  # noqa: E711, E712
        )
    )
    inactive_downloads = (total_downloads or 0) - (active_downloads or 0)
    total_download_count = await session.scalar(
        select(func.coalesce(func.sum(Download.download_count), 0))
    )
    featured_count = await session.scalar(
        select(func.count()).select_from(Download).where(Download.is_featured == True)  # noqa: E712
    )
    category_count = await session.scalar(select(func.count()).select_from(Category))
    tag_count = await session.scalar(select(func.count()).select_from(Tag))

    return {
        "total_downloads": total_downloads or 0,
        "active_downloads": active_downloads or 0,
        "inactive_downloads": inactive_downloads,
        "total_download_count": total_download_count or 0,
        "featured_count": featured_count or 0,
        "category_count": category_count or 0,
        "tag_count": tag_count or 0,
    }


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
            selectinload(Download.parent).options(
                selectinload(Download.versions)
            ),
            selectinload(Download.version_history),
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
            selectinload(Download.version_history),
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
        short_description=data.short_description,
        version=data.version,
        file_type=data.file_type,
        file_path=data.file_path,
        external_url=str(data.external_url) if data.external_url else None,
        file_size_bytes=data.file_size_bytes,
        icon_type=icon_type,
        thumbnail_path=data.thumbnail_path,
        icon_image_path=data.icon_image_path,
        icon_image_url=data.icon_image_url,
        icon_extension=data.icon_extension,
        os_compatibility=os_str,
        category_id=data.category_id,
        parent_id=data.parent_id,
        is_active=data.is_active,
        is_featured=data.is_featured,
        is_official_source=data.is_official_source,
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

    # ── Otomatik sürüm geçmişi ───────────────────────────────────────────
    # Sürüm değişiyorsa (ve eskiden bir sürüm bilgisi varsa) eski hâl,
    # üzerine yazılmadan önce anlık görüntü olarak kaydedilir.
    if "version" in update_data and update_data["version"] != download.version and download.version:
        session.add(
            DownloadVersionHistory(
                download_id=download.id,
                version=download.version,
                file_size_bytes=download.file_size_bytes,
            )
        )

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

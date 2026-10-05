"""SQLAlchemy models for downloads, navigation, standalone pages, and site state."""

from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.default_content import default_hero_components


# ---------------------------------------------------------------------------
# Enum: Dosya türü
# ---------------------------------------------------------------------------
class FileType(str, enum.Enum):
    local = "local"
    external = "external"


# ---------------------------------------------------------------------------
# Enum: İkon türü
# ---------------------------------------------------------------------------
class IconType(str, enum.Enum):
    zip = "zip"
    pdf = "pdf"
    link = "link"
    image = "image"
    exe = "exe"
    apk = "apk"
    dmg = "dmg"
    deb = "deb"
    auto = "auto"
    extension = "extension"


# ---------------------------------------------------------------------------
# Yardımcı: UTC şimdiki zaman
# ---------------------------------------------------------------------------
def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# M2M junction tablosu: download ↔ tag
# ---------------------------------------------------------------------------
class DownloadTag(Base):
    __tablename__ = "download_tag"

    download_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("downloads.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )


# ---------------------------------------------------------------------------
# Category
# ---------------------------------------------------------------------------
class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (
        Index("uq_categories_owner_name", "owner_id", "name", unique=True),
        Index("uq_categories_unowned_name", "name", unique=True, sqlite_where=text("owner_id IS NULL")),
        Index("uq_categories_required", "is_required", unique=True, sqlite_where=text("is_required = 1")),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Sidebar'daki "Kategori Menüsü" sıralaması (admin panelinden sürüklenerek değiştirilir)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True)
    # Bir kategori her zaman korunur; adı ve açıklaması düzenlenebilir.
    is_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    # İlişkiler
    downloads: Mapped[List["Download"]] = relationship(
        "Download", back_populates="category", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<Category id={self.id} name={self.name!r}>"


# ---------------------------------------------------------------------------
# Tag
# ---------------------------------------------------------------------------
class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = (
        Index("uq_tags_owner_name", "owner_id", "name", unique=True),
        Index("uq_tags_unowned_name", "name", unique=True, sqlite_where=text("owner_id IS NULL")),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    # Sidebar'daki "Etiketler" sıralaması (admin panelinden sürüklenerek değiştirilir)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True)

    # İlişkiler
    downloads: Mapped[List["Download"]] = relationship(
        "Download", secondary="download_tag", back_populates="tags", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<Tag id={self.id} name={self.name!r}>"


# ---------------------------------------------------------------------------
# MenuItem — site üst navigasyon menüsü VE footer bağlantıları
# (admin panelinden düzenlenir; `location` alanı hangi bölgeye ait olduğunu belirler)
# ---------------------------------------------------------------------------
class MenuItem(Base):
    __tablename__ = "menu_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    label_en: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    icon: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    open_in_new_tab: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # 'navbar' → üst menü, 'footer' → alt bilgi (footer) bağlantıları
    location: Mapped[str] = mapped_column(String(20), default="navbar", nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return f"<MenuItem id={self.id} label={self.label!r} location={self.location!r}>"


class Page(Base):
    """Standalone page; private pages require an administrator session."""

    __tablename__ = "pages"
    __table_args__ = (CheckConstraint("visibility IN ('public', 'private')", name="ck_pages_visibility"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    body_html: Mapped[str] = mapped_column(Text, nullable=False, default="")
    visibility: Mapped[str] = mapped_column(String(10), nullable=False, default="public")
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


# ---------------------------------------------------------------------------
# SiteSettings — tekil satır; site adı, ikon ve ikon rengi (admin panelinden düzenlenir)
# ---------------------------------------------------------------------------
class SiteLifecycle(Base):
    """Kurulum kapısı ve kesinti sonrası tamamlanabilen temizleme işlemi."""

    __tablename__ = "site_lifecycle"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    installed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    pending_reset: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    purge_roots: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class SiteSettings(Base):
    __tablename__ = "site_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    site_name: Mapped[str] = mapped_column(String(100), nullable=False, default="Downloader")
    site_language: Mapped[str] = mapped_column(String(2), nullable=False, default="en")
    site_timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC", server_default="UTC")
    editor_media_quota_mb: Mapped[int] = mapped_column(Integer, nullable=False, default=256, server_default="256")
    manager_media_quota_mb: Mapped[int] = mapped_column(Integer, nullable=False, default=1024, server_default="1024")
    content_language: Mapped[str] = mapped_column(String(2), nullable=False, default="en")
    seo_home_title: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    seo_meta_description: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    site_icon: Mapped[str] = mapped_column(String(50), nullable=False, default="download-cloud")
    site_icon_color: Mapped[str] = mapped_column(String(20), nullable=False, default="blue")
    # Sitenin tüm vurgu bileşenlerinde kullanılan merkezi renk teması.
    theme_color: Mapped[str] = mapped_column(String(20), nullable=False, default="blue")
    logo_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="icon_text")
    logo_light_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    logo_dark_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    favicon_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    hero_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    hero_background: Mapped[str] = mapped_column(String(20), nullable=False, default="soft")
    hero_image_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    hero_components: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default=default_hero_components,
    )
    navbar_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=8)
    footer_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=8)
    sidebar_category_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    sidebar_tag_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=25)
    # Sidebar blok sırası, virgülle ayrılmış: "search,categories,tags"
    sidebar_block_order: Mapped[str] = mapped_column(
        String(100), nullable=False, default="search,categories,tags"
    )
    session_generation: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    admin_icon: Mapped[str] = mapped_column(String(50), nullable=False, default="user-circle")
    admin_icon_color: Mapped[str] = mapped_column(String(20), nullable=False, default="slate")
    # Admin oturumunun dakika cinsinden geçerlilik süresi
    session_max_age_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=480)
    audit_log_max_records: Mapped[int] = mapped_column(Integer, nullable=False, default=200)
    trash_retention_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    restore_marker: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return f"<SiteSettings site_name={self.site_name!r}>"


# ---------------------------------------------------------------------------
# MediaAsset — Medya Arşivi'ndeki dosyalar için görünen ad meta verisi.
# `path` (rastgele üretilen dosya yolu/linki) hiçbir zaman değişmez; kullanıcı
# yalnızca burada saklanan `display_name`'i düzenler.
# ---------------------------------------------------------------------------
class MediaAsset(Base):
    __tablename__ = "media_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    path: Mapped[str] = mapped_column(String(500), unique=True, nullable=False, index=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    uploaded_by: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    checksum_size: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    checksum_mtime_ns: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return f"<MediaAsset id={self.id} path={self.path!r}>"


class LinkCheck(Base):
    __tablename__ = "link_checks"

    download_id: Mapped[int] = mapped_column(ForeignKey("downloads.id", ondelete="CASCADE"), primary_key=True)
    url: Mapped[str] = mapped_column(String(2000))
    status: Mapped[str] = mapped_column(String(30), index=True)
    http_status: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    message: Mapped[str] = mapped_column(String(300))
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class LoginAttempt(Base):
    __tablename__ = "login_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_key: Mapped[str] = mapped_column(String(64), index=True)
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(10), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    media_quota_mb: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    deletion_requested_by: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (CheckConstraint("role IN ('admin', 'manager', 'editor')", name="ck_users_role"),)


class RegistrationRequest(Base):
    """Pending applicants are not accounts and cannot authenticate."""

    __tablename__ = "registration_requests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False, index=True)


class EditorMessage(Base):
    """Private, plain-text correspondence between an editor and authorized staff."""

    __tablename__ = "editor_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(150), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    responded_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
    responded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    sender: Mapped["User"] = relationship(foreign_keys=[sender_id], lazy="selectin")


class BackupPolicy(Base):
    """Only the public encryption key is stored on the server."""
    __tablename__ = "backup_policy"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    interval_days: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    last_attempt: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    __table_args__ = (CheckConstraint("id = 1", name="ck_backup_policy_singleton"),
                     CheckConstraint("interval_days IN (1,3,5,7,14)", name="ck_backup_policy_interval"))


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor: Mapped[str] = mapped_column(String(100), index=True)
    action: Mapped[str] = mapped_column(String(30))
    level: Mapped[str] = mapped_column(String(20), nullable=False, default="success", index=True)
    entity: Mapped[str] = mapped_column(String(50), index=True)
    entity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    label: Mapped[str] = mapped_column(String(300))
    changes: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)


# ---------------------------------------------------------------------------
# Download (Ana tablo)
# ---------------------------------------------------------------------------
class Download(Base):
    __tablename__ = "downloads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    deletion_pending: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    publication_pending: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0", index=True)
    publication_feedback: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    # Temel bilgiler
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(220), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Ön açıklama: ana sayfa kartlarında gösterilen kısa, düz metin özet.
    # Boşsa kart, tam açıklamanın (WYSIWYG) etiketsiz kısaltmasına düşer.
    short_description: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    is_latest_version: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Dosya bilgileri
    file_type: Mapped[FileType] = mapped_column(
        Enum(FileType, name="file_type_enum"), nullable=False, default=FileType.external
    )
    file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    external_url: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    # Görsel
    icon_type: Mapped[IconType] = mapped_column(
        Enum(IconType, name="icon_type_enum"), nullable=False, default=IconType.auto
    )
    thumbnail_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    # Uygulama ikonu (öncelik sırası: icon_image_path > icon_image_url)
    icon_image_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    icon_image_url: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    # icon_type == 'extension' seçildiğinde kullanılan serbest uzantı adı (ör. "rar", "iso")
    icon_extension: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    # İşletim sistemi uyumu (virgülle ayrılmış: windows,macos,linux,android,ios)
    os_compatibility: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # İlişki FK'lar
    category_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    parent_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("downloads.id", ondelete="SET NULL"), nullable=True
    )

    # İstatistikler
    download_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Durum bayrakları
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_draft: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default="0")
    draft_token: Mapped[Optional[str]] = mapped_column(String(64), unique=True, nullable=True)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Kaynak güvenilirliği: True → resmî site, False → üçüncü parti site
    is_official_source: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    # Zaman damgaları
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    # ---------------------------------------------------------------------------
    # İlişkiler
    # ---------------------------------------------------------------------------
    category: Mapped[Optional["Category"]] = relationship(
        "Category", back_populates="downloads", lazy="select"
    )
    publisher: Mapped[Optional["User"]] = relationship("User", foreign_keys=[owner_id], lazy="selectin")
    tags: Mapped[List["Tag"]] = relationship(
        "Tag", secondary="download_tag", back_populates="downloads", lazy="select"
    )
    # Sürüm geçmişi: alt kayıtlar (eski sürümler)
    versions: Mapped[List["Download"]] = relationship(
        "Download",
        back_populates="parent",
        foreign_keys="[Download.parent_id]",
        lazy="select",
        order_by="Download.created_at.desc()",
    )
    parent: Mapped[Optional["Download"]] = relationship(
        "Download",
        back_populates="versions",
        foreign_keys="[Download.parent_id]",
        remote_side="[Download.id]",
        lazy="select",
    )
    # İndirme logları
    logs: Mapped[List["DownloadLog"]] = relationship(
        "DownloadLog", back_populates="download", lazy="select", passive_deletes=True
    )
    # Otomatik sürüm geçmişi: her düzenlemede sürüm değişirse eski hâl buraya kaydedilir
    version_history: Mapped[List["DownloadVersionHistory"]] = relationship(
        "DownloadVersionHistory",
        back_populates="download",
        lazy="select",
        order_by="DownloadVersionHistory.changed_at.desc()",
        cascade="all, delete-orphan",
    )

    # ---------------------------------------------------------------------------
    # Computed properties
    # ---------------------------------------------------------------------------
    @property
    def file_size_human(self) -> Optional[str]:
        """Dosya boyutunu insan okunabilir formata çevirir."""
        if self.file_size_bytes is None:
            return None
        size = float(self.file_size_bytes)
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    @property
    def source_domain(self) -> Optional[str]:
        """Dış URL'nin alan adını (subdomain dahil) döndürür (örn: code.visualstudio.com)."""
        if self.file_type != FileType.external or not self.external_url:
            return None
        from urllib.parse import urlparse
        parsed = urlparse(self.external_url)
        return parsed.netloc or None

    @property
    def source_root_url(self) -> Optional[str]:
        """Kaynak sitenin ana adresini döndürür (örn: https://code.visualstudio.com)."""
        if self.file_type != FileType.external or not self.external_url:
            return None
        from urllib.parse import urlparse
        parsed = urlparse(self.external_url)
        if not parsed.netloc:
            return None
        return f"{parsed.scheme or 'https'}://{parsed.netloc}"

    def __repr__(self) -> str:
        return f"<Download id={self.id} slug={self.slug!r} version={self.version!r}>"


# ---------------------------------------------------------------------------
# DownloadVersionHistory — bir indirmenin geçmiş sürüm anlık görüntüleri.
# Admin panelinden bir kayıt düzenlenip "Sürüm" değiştirildiğinde, ESKİ değer
# otomatik olarak buraya kaydedilir. Ayrı bir sayfası/slug'ı yoktur — sadece
# detay sayfasındaki "Sürüm Geçmişi" kutusunda bilgi amaçlı listelenir.
# ---------------------------------------------------------------------------
class DownloadVersionHistory(Base):
    __tablename__ = "download_version_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    download_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("downloads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Değişiklikten ÖNCEKİ (eski) sürüm bilgisi
    version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    # İlişkiler
    download: Mapped["Download"] = relationship(
        "Download", back_populates="version_history", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<DownloadVersionHistory download_id={self.download_id} version={self.version!r}>"


# ---------------------------------------------------------------------------
# DownloadLog
# ---------------------------------------------------------------------------
class DownloadLog(Base):
    __tablename__ = "download_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    download_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("downloads.id", ondelete="CASCADE"), nullable=False
    )
    client_key: Mapped[str] = mapped_column(String(64), nullable=False)
    downloaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    # İlişkiler
    download: Mapped["Download"] = relationship(
        "Download", back_populates="logs", lazy="select"
    )

    # İndeks: rate limiting sorgusunu hızlandırır
    __table_args__ = (
        Index("ix_download_logs_client_time", "client_key", "downloaded_at"),
        Index("ix_download_logs_download_id", "download_id"),
    )

    def __repr__(self) -> str:
        return f"<DownloadLog id={self.id} download_id={self.download_id}>"

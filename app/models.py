"""
SQLAlchemy ORM modelleri.

Tablolar:
  - Category       : İçerik kategorileri
  - Tag            : Etiketler
  - Download       : Ana indirme kaydı (self-ref ile sürüm ilişkisi)
  - DownloadTag    : M2M junction (Download ↔ Tag)
  - DownloadLog    : İndirme logları (sayaç + rate limiting)
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


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

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Sidebar'daki "Kategori Menüsü" sıralaması (admin panelinden sürüklenerek değiştirilir)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True)
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

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
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


# ---------------------------------------------------------------------------
# SiteSettings — tekil satır; site adı, ikon ve ikon rengi (admin panelinden düzenlenir)
# ---------------------------------------------------------------------------
class SiteSettings(Base):
    __tablename__ = "site_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    site_name: Mapped[str] = mapped_column(String(100), nullable=False, default="Download Sitesi")
    site_icon: Mapped[str] = mapped_column(String(50), nullable=False, default="download-cloud")
    site_icon_color: Mapped[str] = mapped_column(String(20), nullable=False, default="blue")
    # Sidebar blok sırası, virgülle ayrılmış: "search,categories,tags"
    sidebar_block_order: Mapped[str] = mapped_column(
        String(100), nullable=False, default="search,categories,tags"
    )
    # Admin hesabı — boşsa .env'deki ADMIN_USERNAME/ADMIN_PASSWORD_HASH kullanılır
    # (ilk kurulum varsayılanı). Ayarlar'dan değiştirilince burada saklanır.
    admin_username: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    admin_password_hash: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    admin_icon: Mapped[str] = mapped_column(String(50), nullable=False, default="user-circle")
    admin_icon_color: Mapped[str] = mapped_column(String(20), nullable=False, default="slate")
    # Admin oturumunun dakika cinsinden geçerlilik süresi
    session_max_age_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=480)
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
    path: Mapped[str] = mapped_column(String(500), unique=True, nullable=False, index=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return f"<MediaAsset id={self.id} path={self.path!r}>"


# ---------------------------------------------------------------------------
# Download (Ana tablo)
# ---------------------------------------------------------------------------
class Download(Base):
    __tablename__ = "downloads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Temel bilgiler
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(220), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Ön açıklama: ana sayfa kartlarında gösterilen kısa, düz metin özet.
    # Boşsa kart, tam açıklamanın (WYSIWYG) etiketsiz kısaltmasına düşer.
    short_description: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

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
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Kaynak güvenilirliği: True → resmî site, False → üçüncü parti site
    is_official_source: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

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
        "DownloadLog", back_populates="download", lazy="select"
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
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    downloaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    # İlişkiler
    download: Mapped["Download"] = relationship(
        "Download", back_populates="logs", lazy="select"
    )

    # İndeks: rate limiting sorgusunu hızlandırır
    __table_args__ = (
        Index("ix_download_logs_ip_time", "ip_address", "downloaded_at"),
        Index("ix_download_logs_download_id", "download_id"),
    )

    def __repr__(self) -> str:
        return f"<DownloadLog id={self.id} download_id={self.download_id} ip={self.ip_address!r}>"

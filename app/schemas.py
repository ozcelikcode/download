"""
Pydantic v2 şemaları.

Kategori → Tag → Download → DownloadLog sırasıyla tanımlanmıştır.
Her model için Base / Create / Update / Read ayrımı yapılmıştır.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.content_security import normalize_http_url, normalize_navigation_url, sanitize_rich_text
from app.models import FileType, IconType


# ===========================================================================
# Yardımcılar
# ===========================================================================

class PaginatedResponse(BaseModel):
    """Sayfalandırılmış liste yanıtı."""

    items: list
    total: int
    page: int
    page_size: int
    total_pages: int

    model_config = ConfigDict(arbitrary_types_allowed=True)


# ===========================================================================
# Category
# ===========================================================================

class CategoryBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None


class CategoryCreate(CategoryBase):
    slug: Optional[str] = Field(
        None,
        max_length=120,
        description="Boş bırakılırsa name'den otomatik üretilir.",
    )


class CategoryUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    slug: Optional[str] = Field(None, max_length=120)
    description: Optional[str] = None


class CategoryRead(CategoryBase):
    id: int
    slug: str
    created_at: datetime
    download_count: int = 0  # ilişkiden hesaplanacak

    model_config = ConfigDict(from_attributes=True)


class CategoryReadSimple(BaseModel):
    """Download kartlarında yalnızca küçük gösterim için."""

    id: int
    name: str
    slug: str

    model_config = ConfigDict(from_attributes=True)


# ===========================================================================
# Tag
# ===========================================================================

class TagBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=60)


class TagCreate(TagBase):
    slug: Optional[str] = Field(None, max_length=80)


class TagRead(TagBase):
    id: int
    slug: str

    model_config = ConfigDict(from_attributes=True)


# ===========================================================================
# MenuItem
# ===========================================================================

class MenuItemBase(BaseModel):
    label: str = Field(..., min_length=1, max_length=100)
    label_en: Optional[str] = Field(None, max_length=100)
    url: str = Field(..., min_length=1, max_length=500)
    icon: Optional[str] = Field(None, max_length=50)
    is_active: bool = True
    open_in_new_tab: bool = False

    @field_validator("url", mode="before")
    @classmethod
    def validate_url(cls, value: object) -> str:
        return normalize_navigation_url(str(value or ""))


class MenuItemCreate(MenuItemBase):
    location: str = Field("navbar", pattern="^(navbar|footer)$")


class MenuItemUpdate(BaseModel):
    label: Optional[str] = Field(None, min_length=1, max_length=100)
    label_en: Optional[str] = Field(None, max_length=100)
    url: Optional[str] = Field(None, min_length=1, max_length=500)
    icon: Optional[str] = Field(None, max_length=50)
    is_active: Optional[bool] = None
    open_in_new_tab: Optional[bool] = None

    @field_validator("url", mode="before")
    @classmethod
    def validate_url(cls, value: object) -> str | None:
        if value is None:
            return None
        return normalize_navigation_url(str(value))


class MenuItemRead(MenuItemBase):
    id: int
    position: int
    location: str

    model_config = ConfigDict(from_attributes=True)


class SiteSettingsUpdate(BaseModel):
    site_name: str = Field(..., min_length=1, max_length=100)
    site_icon: str = Field(..., min_length=1, max_length=50)
    site_icon_color: str = Field(..., min_length=1, max_length=20)
    theme_color: str = Field("blue", min_length=1, max_length=20)


class AppearanceSettingsUpdate(BaseModel):
    logo_mode: str = Field(pattern="^(icon_text|image_text|image)$")
    hero_enabled: bool = True
    hero_background: str = Field(pattern="^(soft|mesh|lines|image)$")
    hero_components: str
    navbar_limit: int = Field(8, ge=3, le=12)
    footer_limit: int = Field(8, ge=3, le=12)
    sidebar_category_limit: int = Field(10, ge=3, le=20)
    sidebar_tag_limit: int = Field(25, ge=5, le=25)


# ===========================================================================
# Download
# ===========================================================================

class DownloadBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    short_description: Optional[str] = Field(None, max_length=300)
    version: Optional[str] = Field(None, max_length=50)
    is_latest_version: bool = False
    file_type: FileType = FileType.external
    file_path: Optional[str] = Field(None, max_length=500)
    external_url: Optional[str] = Field(None, max_length=2000)
    file_size_bytes: Optional[int] = Field(None, ge=0)
    icon_type: IconType = IconType.auto
    thumbnail_path: Optional[str] = Field(None, max_length=500)
    icon_image_path: Optional[str] = Field(None, max_length=500)
    icon_image_url: Optional[str] = Field(None, max_length=2000)
    icon_extension: Optional[str] = Field(None, max_length=20)
    os_compatibility: List[str] = Field(default_factory=list)
    category_id: Optional[int] = None
    parent_id: Optional[int] = None
    is_active: bool = True
    is_draft: bool = False
    is_featured: bool = False
    is_official_source: bool = True

    @field_validator("description", mode="before")
    @classmethod
    def sanitize_description(cls, value: object) -> str | None:
        return sanitize_rich_text(None if value is None else str(value))

    @field_validator("external_url", "icon_image_url", mode="before")
    @classmethod
    def validate_remote_url(cls, value: object) -> str | None:
        return normalize_http_url(None if value is None else str(value))

    @model_validator(mode="after")
    def check_file_source(self) -> "DownloadBase":
        if self.file_type == FileType.local and not self.file_path:
            raise ValueError("file_type='local' seçildiğinde file_path zorunludur.")
        if self.file_type == FileType.local and self.is_latest_version:
            raise ValueError("Güncel sürüm seçeneği yalnızca dış bağlantılarda kullanılabilir.")
        if self.file_type == FileType.external and not self.external_url:
            raise ValueError("file_type='external' seçildiğinde external_url zorunludur.")
        return self


class DownloadCreate(DownloadBase):
    slug: Optional[str] = Field(
        None,
        max_length=220,
        description="Boş bırakılırsa title'dan otomatik üretilir.",
    )
    tag_ids: List[int] = Field(default_factory=list)


class DownloadUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    slug: Optional[str] = Field(None, max_length=220)
    description: Optional[str] = None
    short_description: Optional[str] = Field(None, max_length=300)
    version: Optional[str] = Field(None, max_length=50)
    is_latest_version: Optional[bool] = None
    file_type: Optional[FileType] = None
    file_path: Optional[str] = Field(None, max_length=500)
    external_url: Optional[str] = Field(None, max_length=2000)
    file_size_bytes: Optional[int] = Field(None, ge=0)
    icon_type: Optional[IconType] = None
    thumbnail_path: Optional[str] = Field(None, max_length=500)
    icon_image_path: Optional[str] = Field(None, max_length=500)
    icon_image_url: Optional[str] = Field(None, max_length=2000)
    icon_extension: Optional[str] = Field(None, max_length=20)
    os_compatibility: Optional[List[str]] = None
    category_id: Optional[int] = None
    parent_id: Optional[int] = None
    is_active: Optional[bool] = None
    is_draft: Optional[bool] = None
    is_featured: Optional[bool] = None
    is_official_source: Optional[bool] = None
    tag_ids: Optional[List[int]] = None

    @field_validator("description", mode="before")
    @classmethod
    def sanitize_description(cls, value: object) -> str | None:
        return sanitize_rich_text(None if value is None else str(value))

    @field_validator("external_url", "icon_image_url", mode="before")
    @classmethod
    def validate_remote_url(cls, value: object) -> str | None:
        return normalize_http_url(None if value is None else str(value))


class DownloadRead(BaseModel):
    """Tam detay şeması — detay sayfası ve API yanıtı için."""

    id: int
    title: str
    slug: str
    description: Optional[str]
    version: Optional[str]
    is_latest_version: bool
    file_type: FileType
    file_path: Optional[str]
    external_url: Optional[str]
    file_size_bytes: Optional[int]
    file_size_human: Optional[str]
    source_domain: Optional[str]
    icon_type: IconType
    thumbnail_path: Optional[str]
    icon_image_path: Optional[str]
    icon_image_url: Optional[str]
    os_compatibility: Optional[str]
    category: Optional[CategoryReadSimple]
    parent_id: Optional[int]
    tags: List[TagRead]
    download_count: int
    is_active: bool
    is_featured: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DownloadListItem(BaseModel):
    """Listede ve kartlarda kullanılan hafif şema."""

    id: int
    title: str
    slug: str
    version: Optional[str]
    is_latest_version: bool
    file_type: FileType
    file_size_human: Optional[str]
    source_domain: Optional[str]
    icon_type: IconType
    thumbnail_path: Optional[str]
    icon_image_path: Optional[str]
    icon_image_url: Optional[str]
    os_compatibility: Optional[str]
    category: Optional[CategoryReadSimple]
    tags: List[TagRead]
    download_count: int
    is_featured: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ===========================================================================
# DownloadLog
# ===========================================================================

class DownloadLogRead(BaseModel):
    id: int
    download_id: int
    ip_address: str
    downloaded_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ===========================================================================
# Admin Auth
# ===========================================================================

class AdminLoginForm(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)

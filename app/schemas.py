"""
Pydantic v2 şemaları.

Kategori → Tag → Download → DownloadLog sırasıyla tanımlanmıştır.
Her model için Base / Create / Update / Read ayrımı yapılmıştır.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

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
# Download
# ===========================================================================

class DownloadBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    version: Optional[str] = Field(None, max_length=50)
    file_type: FileType = FileType.external
    file_path: Optional[str] = Field(None, max_length=500)
    external_url: Optional[str] = Field(None, max_length=2000)
    file_size_bytes: Optional[int] = Field(None, ge=0)
    icon_type: IconType = IconType.auto
    thumbnail_path: Optional[str] = Field(None, max_length=500)
    icon_image_path: Optional[str] = Field(None, max_length=500)
    icon_image_url: Optional[str] = Field(None, max_length=2000)
    os_compatibility: List[str] = Field(default_factory=list)
    category_id: Optional[int] = None
    parent_id: Optional[int] = None
    is_active: bool = True
    is_featured: bool = False

    @model_validator(mode="after")
    def check_file_source(self) -> "DownloadBase":
        if self.file_type == FileType.local and not self.file_path:
            raise ValueError("file_type='local' seçildiğinde file_path zorunludur.")
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
    version: Optional[str] = Field(None, max_length=50)
    file_type: Optional[FileType] = None
    file_path: Optional[str] = Field(None, max_length=500)
    external_url: Optional[str] = Field(None, max_length=2000)
    file_size_bytes: Optional[int] = Field(None, ge=0)
    icon_type: Optional[IconType] = None
    thumbnail_path: Optional[str] = Field(None, max_length=500)
    icon_image_path: Optional[str] = Field(None, max_length=500)
    icon_image_url: Optional[str] = Field(None, max_length=2000)
    os_compatibility: Optional[List[str]] = None
    category_id: Optional[int] = None
    parent_id: Optional[int] = None
    is_active: Optional[bool] = None
    is_featured: Optional[bool] = None
    tag_ids: Optional[List[int]] = None


class DownloadRead(BaseModel):
    """Tam detay şeması — detay sayfası ve API yanıtı için."""

    id: int
    title: str
    slug: str
    description: Optional[str]
    version: Optional[str]
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

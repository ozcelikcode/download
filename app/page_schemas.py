"""Validation for standalone page content."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator
from slugify import slugify

from app.content_security import rich_text_to_plain_text, sanitize_rich_text


class PageInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    slug: str = Field(default="", max_length=120)
    body_html: str = Field(default="", max_length=100_000)
    visibility: Literal["public", "private"] = "public"
    is_published: bool = False

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        title = value.strip()
        if not title:
            raise ValueError("Page title is required.")
        return title

    @field_validator("slug")
    @classmethod
    def clean_slug(cls, value: str) -> str:
        value = value.strip()
        if value and (slugify(value, allow_unicode=False, separator="-") != value or len(value) > 120):
            raise ValueError("The page address must use lowercase letters, numbers, and hyphens.")
        return value

    @model_validator(mode="after")
    def clean_content(self) -> "PageInput":
        if not self.slug:
            self.slug = slugify(self.title, allow_unicode=False, separator="-")[:120].strip("-")
        if not self.slug:
            raise ValueError("A valid page address is required.")
        self.body_html = sanitize_rich_text(self.body_html) or ""
        if self.is_published and not rich_text_to_plain_text(self.body_html):
            raise ValueError("A published page needs content.")
        return self

"""Kurulum ve yüksek riskli bakım formlarının sınırları."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.config import settings
from app.content_security import normalize_http_url


class InstallationForm(BaseModel):
    site_name: str = Field(min_length=1, max_length=100)
    language: Literal["tr", "en"] = "tr"
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=12, max_length=1024)
    password_confirm: str
    public_url: str = Field(max_length=2000)
    deployment_confirmed: Literal["yes"]

    @field_validator("site_name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value or any(ord(c) < 32 for c in value):
            raise ValueError("setup_invalid")
        return value

    @field_validator("public_url")
    @classmethod
    def configured_url(cls, value: str) -> str:
        value = normalize_http_url(value)
        if not value or value.rstrip("/") != settings.app_base_url.rstrip("/"):
            raise ValueError("setup_domain_mismatch")
        return value.rstrip("/")

    @model_validator(mode="after")
    def matching_passwords(self) -> "InstallationForm":
        if self.password != self.password_confirm or len(self.password.encode()) > 1024:
            raise ValueError("passwords_mismatch")
        return self


class ResetAuthorization(BaseModel):
    action: Literal["settings", "full", "uninstall"]
    password: str = Field(min_length=1, max_length=1024)


class ResetConfirmation(BaseModel):
    confirmation: str = Field(min_length=1, max_length=100)
    nonce: str = Field(min_length=1, max_length=100)
    irreversible: Literal["yes"]

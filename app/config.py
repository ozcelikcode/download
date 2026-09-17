"""
Uygulama yapılandırması.
pydantic-settings ile .env dosyasından yüklenir.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


_INSECURE_SECRET_KEYS = {
    "change-me-in-production",
    "replace-with-a-long-random-value",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Genel
    app_name: str = "Download Sitesi"
    app_secret_key: str = "change-me-in-production"
    app_base_url: str = "http://localhost:8000"
    debug: bool = False

    # Admin
    admin_username: str = "admin"
    admin_password_hash: str = ""

    # Dosya yükleme
    upload_dir: str = "app/static/uploads"
    download_dir: str = "storage/downloads"
    max_upload_size_mb: int = 500

    # Veritabanı
    database_url: str = "sqlite+aiosqlite:///./download.db"

    # Rate limiting
    rate_limit_downloads_per_hour: int = 10

    @field_validator("app_secret_key")
    @classmethod
    def validate_app_secret_key(cls, value: str) -> str:
        """Bilinen örnek değerlerin üretimde oturum imzalamasını engelle."""
        if len(value) < 32 or value in _INSECURE_SECRET_KEYS:
            raise ValueError(
                "APP_SECRET_KEY en az 32 karakterlik rastgele bir sır olmalıdır."
            )
        return value

    @property
    def upload_path(self) -> Path:
        path = Path(self.upload_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def download_path(self) -> Path:
        path = Path(self.download_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

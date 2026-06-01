"""
Uygulama yapılandırması.
pydantic-settings ile .env dosyasından yüklenir.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


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
    max_upload_size_mb: int = 500

    # Veritabanı
    database_url: str = "sqlite+aiosqlite:///./download.db"

    # Rate limiting
    rate_limit_downloads_per_hour: int = 10

    @property
    def upload_path(self) -> Path:
        path = Path(self.upload_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

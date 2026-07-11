"""
Ortak pytest fixture'ları.

Her test kendi geçici SQLite dosyasını kullanır — gerçek `download.db`
hiçbir zaman testler tarafından açılmaz veya değiştirilmez. `get_db`
bağımlılığı, test veritabanına bağlı bir session factory ile override
edilir; test bitiminde engine dispose edilir ve geçici dosya (tmp_path
aracılığıyla) pytest tarafından otomatik temizlenir.
"""

from __future__ import annotations

from typing import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.models  # noqa: F401 — tüm modelleri Base.metadata'ya kaydeder
from app.config import settings
from app.database import Base
from app.dependencies import SESSION_COOKIE, create_admin_session_token, get_db
from app.main import app


@pytest.fixture(autouse=True)
def isolated_uploads(tmp_path, monkeypatch):
    """Hiçbir test gerçek app/static/uploads dizinine yazmasın diye
    yükleme dizinini her testte geçici bir klasöre yönlendirir."""
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))


@pytest_asyncio.fixture
async def db_session(tmp_path) -> AsyncIterator[AsyncSession]:
    """Sıfırdan oluşturulmuş, izole bir test veritabanı sağlar."""
    db_path = tmp_path / "test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db

    async with session_factory() as session:
        yield session

    app.dependency_overrides.pop(get_db, None)
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """Kimliksiz istemci — herkese açık rotaları test etmek için."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def admin_client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """Admin oturumu açılmış istemci — gerçek şifreye ihtiyaç duymadan
    geçerli bir imzalı session cookie üretir."""
    token = create_admin_session_token("admin")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        ac.cookies.set(SESSION_COOKIE, token)
        yield ac

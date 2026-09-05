"""Dosya bütünlüğü, indirme sayacı ve oturum süresi için regresyon testleri."""

import io

import pytest
import httpx
from fastapi import HTTPException, UploadFile
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.config import settings
from app.dependencies import hash_admin_password
from app.models import DownloadLog
from app.schemas import DownloadCreate
from app.uploads import save_upload


async def test_local_upload_preserves_existing_file(admin_client: AsyncClient):
    original = settings.upload_path / "setup.zip"
    original.write_bytes(b"original")
    response = await admin_client.post(
        "/admin/downloads/new",
        data={"title": "New file", "file_type": "local", "is_active": "true"},
        files={"upload_file": ("setup.zip", b"new content", "application/zip")},
    )
    assert response.status_code == 302
    assert original.read_bytes() == b"original"


async def test_local_upload_cannot_escape_upload_directory(admin_client: AsyncClient):
    outside = settings.upload_path.parent / "outside.zip"
    response = await admin_client.post(
        "/admin/downloads/new",
        data={"title": "Safe path", "file_type": "local", "is_active": "true"},
        files={"upload_file": ("../outside.zip", b"content", "application/zip")},
    )
    assert response.status_code == 302
    assert not outside.exists()


@pytest.mark.parametrize("endpoint,field,data", [
    ("/admin/media/upload-file", "file", {}),
    ("/admin/upload/icon-image", "file", {}),
    ("/admin/downloads/new", "upload_file", {"title": "Large", "file_type": "local"}),
])
async def test_oversized_upload_leaves_no_files(admin_client, monkeypatch, endpoint, field, data):
    monkeypatch.setattr(settings, "max_upload_size_mb", 0)
    response = await admin_client.post(
        endpoint, data=data, files={field: ("large.png", b"too large", "image/png")},
    )
    assert response.status_code == 413
    assert not [p for p in settings.upload_path.rglob("*") if p.is_file()]


async def test_rejected_replacement_preserves_original(admin_client, monkeypatch):
    original = settings.upload_path / "setup.zip"
    original.write_bytes(b"original")
    monkeypatch.setattr(settings, "max_upload_size_mb", 0)
    response = await admin_client.post(
        "/admin/media/replace-file", data={"path": "/static/uploads/setup.zip"},
        files={"file": ("new.zip", b"too large", "application/zip")},
    )
    assert response.status_code == 413
    assert original.read_bytes() == b"original"
    assert list(settings.upload_path.iterdir()) == [original]


async def test_stream_limit_preserves_original_after_partial_write(monkeypatch):
    original = settings.upload_path / "setup.zip"
    original.write_bytes(b"original")
    monkeypatch.setattr(settings, "max_upload_size_mb", 1)
    upload = UploadFile(filename="setup.zip", file=io.BytesIO(b"x" * (1024 * 1024 + 1)))
    try:
        with pytest.raises(HTTPException) as error:
            await save_upload(upload, original)
        assert error.value.status_code == 413
    finally:
        await upload.close()
    assert original.read_bytes() == b"original"
    assert list(settings.upload_path.iterdir()) == [original]


@pytest.mark.parametrize("source", ["missing", "directory"])
async def test_unavailable_download_is_not_counted(client, db_session, source):
    path = settings.upload_path if source == "directory" else settings.upload_path / "missing.zip"
    download = await crud.create_download(db_session, DownloadCreate(
        title="Unavailable", file_type="local", file_path=str(path),
    ))
    response = await client.get(f"/dl/{download.slug}")
    assert response.status_code == 404
    await db_session.refresh(download)
    assert download.download_count == 0
    assert await db_session.scalar(select(func.count()).select_from(DownloadLog)) == 0


async def test_successful_download_counts_once(client, db_session):
    path = settings.upload_path / "ready.zip"
    path.write_bytes(b"archive")
    download = await crud.create_download(db_session, DownloadCreate(
        title="Ready", file_type="local", file_path=str(path),
    ))
    response = await client.get(f"/dl/{download.slug}")
    assert response.status_code == 200
    assert response.content == b"archive"
    await db_session.refresh(download)
    assert download.download_count == 1
    assert await db_session.scalar(select(func.count()).select_from(DownloadLog)) == 1


async def test_forwarded_headers_do_not_bypass_download_limit(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_downloads_per_hour", 1)
    download = await crud.create_download(db_session, DownloadCreate(
        title="External", external_url="https://example.com/file.zip",
    ))
    first = await client.get(f"/dl/{download.slug}", headers={"X-Forwarded-For": "192.0.2.1"})
    second = await client.get(f"/dl/{download.slug}", headers={"X-Forwarded-For": "192.0.2.2"})
    assert first.status_code == 302
    assert second.status_code == 429


async def test_login_cookie_uses_configured_duration(client: AsyncClient, db_session: AsyncSession):
    await crud.update_admin_credentials(db_session, "test-admin", hash_admin_password("test-password"))
    await crud.update_session_max_age(db_session, 30)
    response = await client.post("/admin/login", data={"username": "test-admin", "password": "test-password"})
    assert response.status_code == 302
    assert "Max-Age=1800" in response.headers["set-cookie"]


async def test_oversized_remote_icon_cleans_partial_file(monkeypatch):
    from app.routers import admin

    monkeypatch.setattr(settings, "max_upload_size_mb", 0)
    transport = httpx.MockTransport(lambda request: httpx.Response(
        200, headers={"content-type": "image/png", "content-length": "0"}, content=b"oversized",
    ))
    client_class = httpx.AsyncClient
    monkeypatch.setattr(admin.httpx, "AsyncClient", lambda **kwargs: client_class(transport=transport, **kwargs))
    monkeypatch.setattr(admin, "_icon_fetch_progress", {"test": {"done": False}})
    await admin._fetch_icon_from_url("https://example.com/icon.png", "test", "admin")
    assert admin._icon_fetch_progress["test"]["done"]
    assert "boyutu" in admin._icon_fetch_progress["test"]["error"]
    assert not [p for p in settings.upload_path.rglob("*") if p.is_file()]

"""Özel indirme deposu ve eski statik dosya geçişi testleri."""

from urllib.parse import quote

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.config import settings
from app.models import MediaAsset
from app.schemas import DownloadCreate
from app.storage import migrate_legacy_local_downloads


async def test_uploaded_download_is_private_but_public_download_route_serves_it(
    client: AsyncClient,
    admin_client: AsyncClient,
    db_session: AsyncSession,
):
    upload = await admin_client.post(
        "/admin/media/upload-file",
        files={"file": ("paket.zip", b"private-content", "application/zip")},
    )
    assert upload.status_code == 200
    name = upload.json()["name"]
    protected_path = upload.json()["path"]
    disk_path = settings.download_path / name

    assert disk_path.read_bytes() == b"private-content"
    assert not (settings.upload_path / name).exists()

    download = await crud.create_download(
        db_session,
        DownloadCreate(title="Private package", file_type="local", file_path=str(disk_path)),
    )

    protected = await client.get(protected_path)
    assert protected.status_code == 302
    assert protected.headers["location"] == "/admin/login"
    assert (await client.get(f"/static/uploads/{quote(name)}")).status_code == 404

    public_download = await client.get(f"/dl/{download.slug}")
    assert public_download.status_code == 200
    assert public_download.content == b"private-content"


async def test_admin_private_file_preview_forces_non_images_to_download(
    admin_client: AsyncClient,
):
    upload = await admin_client.post(
        "/admin/media/upload-file",
        files={"file": ("belge.pdf", b"not-a-real-pdf", "application/pdf")},
    )
    response = await admin_client.get(upload.json()["path"])
    assert response.status_code == 200
    assert response.content == b"not-a-real-pdf"
    assert response.headers["content-type"] == "application/octet-stream"
    assert response.headers["content-disposition"].startswith("attachment;")


async def test_public_download_refuses_file_outside_private_storage(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path,
):
    outside = tmp_path / "outside.zip"
    outside.write_bytes(b"secret")
    download = await crud.create_download(
        db_session,
        DownloadCreate(title="Outside", file_type="local", file_path=str(outside)),
    )

    response = await client.get(f"/dl/{download.slug}")
    assert response.status_code == 404


async def test_legacy_static_downloads_and_metadata_are_migrated(
    db_session: AsyncSession,
):
    source = settings.upload_path / "eski paket.zip"
    source.write_bytes(b"legacy")
    old_web_path = f"/static/uploads/{quote(source.name)}"
    db_session.add(MediaAsset(path=old_web_path, display_name="Eski Paket", uploaded_by="admin"))
    download = await crud.create_download(
        db_session,
        DownloadCreate(title="Legacy", file_type="local", file_path=str(source)),
    )

    updated = await migrate_legacy_local_downloads(db_session)
    await db_session.refresh(download)

    target = settings.download_path / source.name
    assert updated == 1
    assert not source.exists()
    assert target.read_bytes() == b"legacy"
    assert download.file_path == str(target.resolve())
    asset = await db_session.scalar(select(MediaAsset))
    assert asset is not None
    assert asset.path == f"/admin/media/files/{quote(target.name)}"
    assert asset.display_name == "Eski Paket"
    assert await migrate_legacy_local_downloads(db_session) == 0
    assert target.read_bytes() == b"legacy"


async def test_unlinked_legacy_archive_file_is_also_migrated(
    db_session: AsyncSession,
):
    source = settings.upload_path / "unlinked.bin"
    source.write_bytes(b"archive")

    updated = await migrate_legacy_local_downloads(db_session)

    assert updated == 0
    assert not source.exists()
    assert (settings.download_path / source.name).read_bytes() == b"archive"

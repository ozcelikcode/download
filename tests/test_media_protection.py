from urllib.parse import quote

import pytest
from sqlalchemy import select

from app import crud
from app.config import settings
from app.models import MediaAsset
from app.schemas import DownloadCreate


@pytest.mark.parametrize("field", ["file_path", "icon_image_path", "thumbnail_path", "description"])
async def test_used_media_cannot_be_deleted(admin_client, db_session, field):
    file = settings.upload_path / "görsel dosya.png"
    file.write_bytes(b"original")
    url = "/static/uploads/" + quote(file.name)
    values = {"title": "Bağlı içerik", "is_active": False, "external_url": "https://example.com/file"}
    if field == "file_path":
        values.update(file_type="local", file_path=str(file))
    elif field == "description":
        values[field] = f'<p><img src="{url}"></p>'
    else:
        values[field] = url
    download = await crud.create_download(db_session, DownloadCreate(**values))
    await crud.record_media_upload(db_session, url, "admin")
    response = await admin_client.post("/admin/media/delete-file", data={"path": url})
    assert response.status_code == 409
    assert response.json()["detail"]["downloads"][0]["id"] == download.id
    assert file.read_bytes() == b"original"
    assert await db_session.scalar(select(MediaAsset).where(MediaAsset.path == url))
    page = await admin_client.get("/admin/media?tab=files")
    assert "Bağlı içerik" in page.text


async def test_icon_delete_is_also_protected(admin_client, db_session):
    icon = settings.upload_path / "icons" / "used.png"
    icon.parent.mkdir()
    icon.write_bytes(b"image")
    await crud.create_download(db_session, DownloadCreate(
        title="Icon user", external_url="https://example.com", icon_image_path="/static/uploads/icons/used.png",
    ))
    response = await admin_client.post("/admin/upload/icon-image-delete", data={"path": "/static/uploads/icons/used.png"})
    assert response.status_code == 409
    assert icon.exists()


async def test_delete_rejects_outside_path(admin_client):
    response = await admin_client.post("/admin/media/delete-file", data={"path": "/static/uploads/../../download.db"})
    assert response.status_code == 400


async def test_absolute_current_origin_reference_is_protected(admin_client, db_session):
    file = settings.upload_path / "used.png"
    file.write_bytes(b"image")
    await crud.create_download(db_session, DownloadCreate(
        title="Absolute reference", external_url="https://example.com", description='<img src="http://test/static/uploads/used.png">',
    ))
    response = await admin_client.post("/admin/media/delete-file", data={"path": "/static/uploads/used.png"})
    assert response.status_code == 409
    assert file.exists()

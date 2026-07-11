"""
Medya yükleme, sıkıştırma ve otomatik ikon kırpma testleri.

`isolated_uploads` fixture'ı (conftest.py, autouse) sayesinde bu testler
gerçek app/static/uploads dizinine asla dokunmaz.
"""

from __future__ import annotations

import io

from httpx import AsyncClient
from PIL import Image

from app.config import settings
from app.imaging import MAX_DIMENSION


def _make_png_bytes(width: int, height: int, color=(255, 0, 0)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, format="PNG")
    return buf.getvalue()


def _upload_path_to_disk(url_path: str):
    """'/static/uploads/xxx' web yolunu gerçek (izole) disk yoluna çevirir."""
    rel = url_path.removeprefix("/static/uploads/")
    return settings.upload_path / rel


async def test_icon_upload_compresses_large_image(admin_client: AsyncClient):
    big_image = _make_png_bytes(2400, 1800)

    response = await admin_client.post(
        "/admin/upload/icon-image",
        files={"file": ("buyuk.png", big_image, "image/png")},
    )
    assert response.status_code == 200
    path = response.json()["path"]

    disk_path = _upload_path_to_disk(path)
    assert disk_path.exists()

    with Image.open(disk_path) as saved:
        assert max(saved.width, saved.height) <= MAX_DIMENSION

    # Sıkıştırma sonrası dosya, orijinalden gözle görülür şekilde küçük olmalı.
    assert disk_path.stat().st_size < len(big_image)


async def test_icon_upload_rejects_non_image(admin_client: AsyncClient):
    response = await admin_client.post(
        "/admin/upload/icon-image",
        files={"file": ("belge.txt", b"merhaba", "text/plain")},
    )
    assert response.status_code == 400


async def test_icon_auto_crop_produces_square_png(admin_client: AsyncClient):
    wide_image = _make_png_bytes(400, 150, color=(0, 128, 255))
    upload_resp = await admin_client.post(
        "/admin/upload/icon-image",
        files={"file": ("genis.png", wide_image, "image/png")},
    )
    original_path = upload_resp.json()["path"]

    crop_resp = await admin_client.post(
        "/admin/upload/icon-auto-crop",
        data={"path": original_path, "size": "256"},
    )
    assert crop_resp.status_code == 200
    new_path = crop_resp.json()["path"]
    assert new_path != original_path

    disk_path = _upload_path_to_disk(new_path)
    with Image.open(disk_path) as cropped:
        assert cropped.size == (256, 256)
        assert cropped.format == "PNG"


async def test_icon_auto_crop_missing_source_returns_404(admin_client: AsyncClient):
    response = await admin_client.post(
        "/admin/upload/icon-auto-crop",
        data={"path": "/static/uploads/icons/olmayan-dosya.png", "size": "256"},
    )
    assert response.status_code == 404


async def test_media_upload_file_generic_and_unique_name(admin_client: AsyncClient):
    first = await admin_client.post(
        "/admin/media/upload-file",
        files={"file": ("kurulum.zip", b"sahte-zip-icerigi", "application/zip")},
    )
    assert first.status_code == 200
    first_name = first.json()["name"]

    second = await admin_client.post(
        "/admin/media/upload-file",
        files={"file": ("kurulum.zip", b"baska-icerik", "application/zip")},
    )
    second_name = second.json()["name"]

    # Aynı ada sahip iki yükleme çakışmamalı (üzerine yazmamalı).
    assert first_name != second_name
    assert (settings.upload_path / first_name).exists()
    assert (settings.upload_path / second_name).exists()


async def test_media_delete_file_removes_from_disk(admin_client: AsyncClient):
    upload_resp = await admin_client.post(
        "/admin/media/upload-file",
        files={"file": ("gecici.txt", b"icerik", "text/plain")},
    )
    name = upload_resp.json()["name"]
    disk_path = settings.upload_path / name
    assert disk_path.exists()

    delete_resp = await admin_client.post(
        "/admin/media/delete-file", data={"path": f"/static/uploads/{name}"}
    )
    assert delete_resp.status_code == 200
    assert not disk_path.exists()


async def test_media_upload_requires_admin_session(client: AsyncClient):
    response = await client.post(
        "/admin/media/upload-file",
        files={"file": ("x.txt", b"x", "text/plain")},
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/admin/login"

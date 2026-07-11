"""
Medya yükleme, sıkıştırma ve otomatik ikon kırpma testleri.

`isolated_uploads` fixture'ı (conftest.py, autouse) sayesinde bu testler
gerçek app/static/uploads dizinine asla dokunmaz.
"""

from __future__ import annotations

import io

from httpx import AsyncClient
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
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


# ---------------------------------------------------------------------------
# Yerinde düzenleme — link/dosya adı asla değişmemeli
# ---------------------------------------------------------------------------

async def test_icon_replace_in_place_keeps_same_link(admin_client: AsyncClient):
    original = await admin_client.post(
        "/admin/upload/icon-image",
        files={"file": ("orijinal.png", _make_png_bytes(300, 300, (10, 20, 30)), "image/png")},
    )
    path = original.json()["path"]

    replaced = await admin_client.post(
        "/admin/upload/icon-image",
        data={"replace_path": path},
        files={"file": ("kirpilmis.png", _make_png_bytes(150, 150, (200, 0, 0)), "image/png")},
    )
    assert replaced.status_code == 200
    assert replaced.json()["path"] == path  # link değişmedi

    disk_path = _upload_path_to_disk(path)
    with Image.open(disk_path) as img:
        assert img.size == (150, 150)  # içerik gerçekten değişti


async def test_icon_replace_in_place_skips_recompression(admin_client: AsyncClient):
    """replace_path verildiğinde sıkıştırma uygulanmamalı — boyut küçültme yapılmamalı."""
    original = await admin_client.post(
        "/admin/upload/icon-image",
        files={"file": ("kucuk.png", _make_png_bytes(200, 200), "image/png")},
    )
    path = original.json()["path"]

    # MAX_DIMENSION'ı aşan bir görselle yerinde değiştir — sıkıştırma
    # devrede olsaydı küçültülürdü, replace_path ile küçültülmemeli.
    oversized = _make_png_bytes(MAX_DIMENSION + 400, 900)
    replaced = await admin_client.post(
        "/admin/upload/icon-image",
        data={"replace_path": path},
        files={"file": ("buyuk.png", oversized, "image/png")},
    )
    assert replaced.status_code == 200

    disk_path = _upload_path_to_disk(path)
    with Image.open(disk_path) as img:
        assert img.width == MAX_DIMENSION + 400  # küçültülmedi → sıkıştırma atlandı


async def test_icon_auto_crop_in_place_keeps_same_link(admin_client: AsyncClient):
    upload_resp = await admin_client.post(
        "/admin/upload/icon-image",
        files={"file": ("genis.png", _make_png_bytes(400, 150), "image/png")},
    )
    path = upload_resp.json()["path"]

    crop_resp = await admin_client.post(
        "/admin/upload/icon-auto-crop",
        data={"path": path, "size": "128", "in_place": "true"},
    )
    assert crop_resp.status_code == 200
    assert crop_resp.json()["path"] == path  # link değişmedi

    disk_path = _upload_path_to_disk(path)
    with Image.open(disk_path) as img:
        assert img.size == (128, 128)


async def test_media_replace_file_keeps_same_link(admin_client: AsyncClient):
    upload_resp = await admin_client.post(
        "/admin/media/upload-file",
        files={"file": ("kurulum.zip", b"eski-icerik", "application/zip")},
    )
    name = upload_resp.json()["name"]
    path = f"/static/uploads/{name}"

    replace_resp = await admin_client.post(
        "/admin/media/replace-file",
        data={"path": path},
        files={"file": ("yeni.zip", b"yeni-icerik", "application/zip")},
    )
    assert replace_resp.status_code == 200
    assert replace_resp.json()["path"] == path

    assert (settings.upload_path / name).read_bytes() == b"yeni-icerik"


async def test_media_replace_file_missing_source_returns_404(admin_client: AsyncClient):
    response = await admin_client.post(
        "/admin/media/replace-file",
        data={"path": "/static/uploads/olmayan.zip"},
        files={"file": ("x.zip", b"x", "application/zip")},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Görünen ad (display name) — fiziksel dosya adından/linkten bağımsız
# ---------------------------------------------------------------------------

async def test_media_rename_sets_and_clears_display_name(
    admin_client: AsyncClient, db_session: AsyncSession
):
    upload_resp = await admin_client.post(
        "/admin/media/upload-file",
        files={"file": ("2847fc6c5ca8.jpg", b"icerik", "image/jpeg")},
    )
    path = f"/static/uploads/{upload_resp.json()['name']}"

    rename_resp = await admin_client.post(
        "/admin/media/rename", data={"path": path, "display_name": "Tatil Fotoğrafı"}
    )
    assert rename_resp.status_code == 200

    names = await crud.get_media_display_names(db_session, [path])
    assert names[path] == "Tatil Fotoğrafı"

    # Boş ad gönderilirse özel ad kaldırılır (varsayılan dosya adına döner).
    await admin_client.post("/admin/media/rename", data={"path": path, "display_name": ""})
    names_after = await crud.get_media_display_names(db_session, [path])
    assert path not in names_after


async def test_media_delete_also_clears_display_name(
    admin_client: AsyncClient, db_session: AsyncSession
):
    upload_resp = await admin_client.post(
        "/admin/media/upload-file",
        files={"file": ("belge.pdf", b"icerik", "application/pdf")},
    )
    path = f"/static/uploads/{upload_resp.json()['name']}"
    await admin_client.post("/admin/media/rename", data={"path": path, "display_name": "Kılavuz"})

    await admin_client.post("/admin/media/delete-file", data={"path": path})

    names = await crud.get_media_display_names(db_session, [path])
    assert path not in names


async def test_media_page_shows_display_name(admin_client: AsyncClient):
    upload_resp = await admin_client.post(
        "/admin/media/upload-file",
        files={"file": ("orijinal-ad.zip", b"icerik", "application/zip")},
    )
    path = f"/static/uploads/{upload_resp.json()['name']}"
    await admin_client.post(
        "/admin/media/rename", data={"path": path, "display_name": "Özel Görünen Ad"}
    )

    page = await admin_client.get("/admin/media")
    assert "Özel Görünen Ad" in page.text

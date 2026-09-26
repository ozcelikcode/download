from __future__ import annotations

from pathlib import Path

import pytest


async def test_public_and_admin_layouts_load_shared_toast_system(client, admin_client):
    public_page = await client.get("/")
    admin_page = await admin_client.get("/admin")

    for response in (public_page, admin_page):
        assert response.status_code == 200
        assert "/static/js/toast.js?" in response.text
        assert "data-toast-region" in response.text
        assert 'aria-live="polite"' in response.text


async def test_server_flash_message_is_forwarded_to_shared_toast(admin_client):
    created = await admin_client.post(
        "/admin/settings/session-duration", data={"session_max_age_minutes": "480"}
    )
    assert created.status_code == 302

    page = await admin_client.get(created.headers["location"])

    assert page.status_code == 200
    assert 'data-toast-type="success"' in page.text
    assert 'data-toast-id="server-flash"' in page.text
    assert "Oturum süresi güncellendi" in page.text


@pytest.mark.parametrize(
    ("endpoint", "name", "success_message"),
    [
        ("/admin/tags", "Toast Etiketi", "“Toast Etiketi” etiketi eklendi."),
        (
            "/admin/categories",
            "Toast Kategorisi",
            "“Toast Kategorisi” kategorisi eklendi.",
        ),
    ],
)
async def test_taxonomy_creation_shows_success_toast(
    admin_client, endpoint, name, success_message
):
    response = await admin_client.post(endpoint, data={"name": name})
    page = await admin_client.get(response.headers["location"])

    assert response.status_code == 302
    assert page.status_code == 200
    assert 'data-toast-type="success"' in page.text
    assert success_message in page.text


@pytest.mark.parametrize(
    ("endpoint", "name", "error_message"),
    [
        ("/admin/tags", "Tekrarlı Etiket", "Bu etiket adı zaten kullanılıyor."),
        (
            "/admin/categories",
            "Tekrarlı Kategori",
            "Bu kategori adı zaten kullanılıyor.",
        ),
    ],
)
async def test_duplicate_taxonomy_creation_shows_error_toast(
    admin_client, endpoint, name, error_message
):
    first = await admin_client.post(endpoint, data={"name": name})
    duplicate = await admin_client.post(endpoint, data={"name": name})
    page = await admin_client.get(duplicate.headers["location"])

    assert first.status_code == 302
    assert duplicate.status_code == 302
    assert 'data-toast-type="error"' in page.text
    assert error_message in page.text


async def test_media_archive_replays_success_feedback_after_refresh(admin_client):
    page = await admin_client.get("/admin/media")

    assert page.status_code == 200
    assert "sessionStorage.setItem('admin-media-feedback'" in page.text
    assert "sessionStorage.getItem('admin-media-feedback')" in page.text
    assert "window.__reloadMediaTab = function (kind, message, type)" in page.text
    assert "finishUploadQueue(result, 'image', imagesUploadInput)" in page.text
    assert "finishUploadQueue(result, 'file', filesUploadInput)" in page.text
    assert "window.mediaMessages.itemDeleted" in page.text
    assert "window.mediaMessages.fileReplaced" in page.text


async def test_toast_script_is_served_and_writes_messages_as_text(client):
    response = await client.get("/static/js/toast.js")

    assert response.status_code == 200
    assert "window.AppToast" in response.text
    assert ".textContent = String(message" in response.text
    assert "ALLOWED_TYPES" in response.text


def test_page_specific_copy_feedback_uses_shared_toast():
    media = Path("app/templates/admin/media.html").read_text(encoding="utf-8")
    detail = Path("app/templates/detail.html").read_text(encoding="utf-8")

    assert 'id="media-copy-toast"' not in media
    assert "AppToast.show(window.mediaMessages.linkCopied" in media
    assert "AppToast.show(status.textContent" in detail

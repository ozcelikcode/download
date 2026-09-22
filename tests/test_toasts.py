from __future__ import annotations

from pathlib import Path


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

"""Favicon processing, access control, and previous archive compatibility."""

import io
import json
import zipfile

import pytest
from PIL import Image
from sqlalchemy import select

from app import backups
from app.config import settings
from app.dependencies import SESSION_COOKIE, create_admin_session_token
from app.models import SiteSettings, User
from app.templating import favicon_url


async def test_favicon_upload_replace_and_clear_preserve_assets(admin_client, db_session):
    buffer = io.BytesIO()
    Image.new("RGB", (320, 180), "red").save(buffer, format="PNG")
    paths = []
    for _ in range(2):
        response = await admin_client.post("/panel/settings/favicon", files={"favicon_file": ("icon.png", buffer.getvalue(), "image/png")})
        assert response.status_code == 302
        db_session.expire_all()
        account = await db_session.scalar(select(SiteSettings))
        paths.append(account.favicon_path)
        with Image.open(settings.upload_path / "icons" / account.favicon_path.rsplit("/", 1)[1]) as image:
            assert image.size == (128, 128) and image.format == "PNG"
        assert favicon_url().startswith(account.favicon_path + "?v=")
        assert 'rel="icon"' in (await admin_client.get("/panel/users")).text
    assert paths[0] != paths[1]
    assert (await admin_client.post("/panel/settings/favicon", data={"clear_favicon": "true"})).status_code == 302
    db_session.expire_all()
    assert (await db_session.scalar(select(SiteSettings))).favicon_path is None
    assert favicon_url() is None
    assert len(list((settings.upload_path / "icons").glob("*.png"))) == 2
    assert not list(settings.upload_path.rglob(".*.part"))


async def test_favicon_rejects_invalid_image_and_private_address(admin_client, db_session):
    assert (await admin_client.post("/panel/settings/favicon", files={"favicon_file": ("bad.svg", b'<svg onload="alert(1)"></svg>', "image/svg+xml")})).status_code == 400
    assert (await admin_client.post("/panel/settings/favicon", data={"favicon_source": "url", "favicon_web_url": "http://127.0.0.1/icon.png"})).status_code == 400
    assert not list(settings.upload_path.rglob("*.png"))
    assert not list(settings.upload_path.rglob(".*.part"))
    assert (await db_session.scalar(select(SiteSettings))).favicon_path is None


async def test_favicon_editor_denied_and_csrf_required(client, admin_client, db_session):
    admin = await db_session.scalar(select(User).where(User.username == "admin"))
    editor = User(username="favicon-editor", role="editor", password_hash=admin.password_hash)
    db_session.add(editor)
    await db_session.commit()
    client.cookies.set(SESSION_COOKIE, create_admin_session_token(editor.username, editor.password_hash, user_id=editor.id), domain="test.local", path="/")
    assert (await client.post("/panel/settings/favicon", data={"clear_favicon": "true"})).status_code == 403
    admin_client.headers.pop("X-CSRF-Token")
    assert (await admin_client.post("/panel/settings/favicon", data={"clear_favicon": "true"})).status_code == 403


async def test_favicon_remote_import_is_local_normalized_and_pinned(admin_client, db_session, monkeypatch):
    import httpx
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.routers import admin

    buffer = io.BytesIO()
    Image.new("RGB", (300, 150), "green").save(buffer, format="JPEG")

    async def resolve(_url):
        return "93.184.216.34"

    def handle(request):
        assert request.url.host == "93.184.216.34" and request.headers["host"] == "example.com"
        return httpx.Response(200, headers={"content-type": "image/jpeg"}, content=buffer.getvalue())

    client_class = httpx.AsyncClient
    monkeypatch.setattr(admin, "resolve_public_url", resolve)
    monkeypatch.setattr(admin, "AsyncSessionLocal", async_sessionmaker(db_session.bind, expire_on_commit=False))
    monkeypatch.setattr(admin.httpx, "AsyncClient", lambda **kwargs: client_class(transport=httpx.MockTransport(handle), **kwargs))
    response = await admin_client.post("/panel/settings/favicon", data={"favicon_source": "url", "favicon_web_url": "https://example.com/image.jpg"})
    assert response.status_code == 302
    db_session.expire_all()
    path = (await db_session.scalar(select(SiteSettings))).favicon_path
    assert path.startswith("/static/uploads/icons/") and path.endswith(".png")
    with Image.open(settings.upload_path / "icons" / path.rsplit("/", 1)[1]) as image:
        assert image.size == (128, 128) and image.format == "PNG"
    assert not admin._icon_fetch_progress and not list(settings.upload_path.rglob(".*.part"))


def test_panel_update_translations_are_complete():
    from app.i18n import TRANSLATIONS
    from app.locales.panel_updates import STRINGS
    for language in ("en", "es", "fr", "tr"):
        assert set(STRINGS[language]) == set(STRINGS["en"])
        for key in (*STRINGS["en"], "upload_file", "image_url", "remove_image", "notifications"):
            assert TRANSLATIONS[language][key] and TRANSLATIONS[language][key] != key


@pytest.mark.parametrize("value", ["legacy", "https://remote.test/icon.png", "/static/uploads/icons/../secret.png"])
async def test_favicon_backup_adapter_is_strict(db_session, value):
    stage = backups.new_stage()
    try:
        backups.write_archive(stage / "incoming.zip")
        with zipfile.ZipFile(stage / "incoming.zip") as archive:
            manifest = json.loads(archive.read("manifest.json"))
            data = json.loads(archive.read("data.json"))
        if value == "legacy":
            del data['site_settings'][0]['gallery_image_limit']
            for row in data['users']:
                del row['publisher_report_count']
            for row in data['downloads']:
                del row['gallery_images']
            del data["site_settings"][0]["image_compression_enabled"]
            del data["site_settings"][0]["image_compression_level"]
            for user in data["users"]:
                del user["profile_icon"]
            manifest["schema"] = backups.schema_fingerprint(before_favicon=True)
            del data["site_settings"][0]["favicon_path"]
        else:
            data["site_settings"][0]["favicon_path"] = value
        with zipfile.ZipFile(stage / "incoming.zip", "w") as archive:
            archive.writestr("manifest.json", json.dumps(manifest))
            archive.writestr("data.json", json.dumps(data))
        if value == "legacy":
            _, imported = backups.validate_archive(stage)
            assert imported["site_settings"][0]["favicon_path"] is None
        else:
            with pytest.raises(backups.BackupError):
                backups.validate_archive(stage)
    finally:
        backups.remove_stage(stage)

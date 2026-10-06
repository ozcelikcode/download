"""Account-photo privacy, normalization, quota and shared navigation regressions."""

import io
import re
import zipfile

import pytest
from PIL import Image
from sqlalchemy import func, select

from app.config import settings
from app.dependencies import SESSION_COOKIE, create_admin_session_token
from app.i18n import TRANSLATIONS
from app.models import MediaAsset, RegistrationRequest, User
from app.profile_photos import photo_path
from app.storage import migrate_legacy_local_downloads
from app.storage_quota import usage_bytes


def image_bytes(color="red"):
    output = io.BytesIO()
    image = Image.new("RGB", (900, 600), color)
    exif = Image.Exif()
    exif[270] = "PRIVATE IMAGE METADATA"
    image.save(output, "JPEG", exif=exif)
    return output.getvalue()


async def login_role(client, session, role):
    admin = await session.scalar(select(User).where(User.username == "admin"))
    if role == "admin":
        return admin
    user = User(username=f"photo-{role}", role=role, password_hash=admin.password_hash)
    session.add(user)
    await session.commit()
    client.cookies.set(SESSION_COOKIE, create_admin_session_token(
        user.username, user.password_hash, user_id=user.id), domain="test.local", path="/")
    return user


@pytest.mark.parametrize("role", ["admin", "manager", "editor"])
async def test_photo_normalization_replacement_removal(admin_client, client, db_session, role):
    user = await login_role(admin_client, db_session, role)
    response = await admin_client.post("/panel/account/photo", files={"photo": ("source.jpg", image_bytes(), "image/jpeg")})
    assert response.status_code == 303
    path = photo_path(user.id)
    with Image.open(path) as image:
        assert image.size == (256, 256) and image.format == "WEBP"
        assert not image.getexif() and not image.info.get("exif")
    assert path.stat().st_size < len(image_bytes())
    assert await usage_bytes(db_session, user.id) == path.stat().st_size
    asset = await db_session.scalar(select(MediaAsset).where(MediaAsset.owner_id == user.id))
    assert asset.path == f"/static/uploads/icons/.profiles/{user.id}.webp"
    response = await admin_client.get("/panel/account/photo")
    assert response.status_code == 200 and "no-store" in response.headers["cache-control"]
    assert (await client.get(asset.path)).status_code == 404
    assert (await client.get("/panel/account/photo")).status_code == 302
    page = await admin_client.get("/panel/settings/account")
    assert '/panel/account/photo?v=' in page.text and 'enctype="multipart/form-data"' in page.text
    assert '.profiles/' not in (await admin_client.get('/panel/media')).text
    from app.health import get_admin_health
    assert (await get_admin_health(db_session)).unused_media == 0
    original = path.read_bytes()
    await admin_client.post("/panel/account/photo", files={"photo": ("new.jpg", image_bytes("blue"), "image/jpeg")})
    assert path.read_bytes() != original
    assert await db_session.scalar(select(func.count()).select_from(MediaAsset)) == 1
    assert (await admin_client.post("/panel/account/photo/remove")).status_code == 303
    assert not path.exists() and await usage_bytes(db_session, user.id) == 0
    assert not list(path.parent.glob(".upload-*")) and not list(path.parent.glob(".replace-*"))


@pytest.mark.parametrize("payload", [b"<svg onload='alert(1)'/>", b"not an image", b""])
async def test_bad_photo_preserves_existing_photo(admin_client, db_session, payload):
    admin = await login_role(admin_client, db_session, "admin")
    await admin_client.post("/panel/account/photo", files={"photo": ("safe.jpg", image_bytes(), "image/jpeg")})
    path = photo_path(admin.id)
    original = path.read_bytes()
    response = await admin_client.post("/panel/account/photo", files={"photo": ("fake.png", payload, "image/png")})
    assert response.status_code == 303 and path.read_bytes() == original
    assert not list(path.parent.glob(".upload-*"))


async def test_photo_requires_csrf(admin_client):
    admin_client.headers.pop("X-CSRF-Token")
    assert (await admin_client.post("/panel/account/photo", files={"photo": ("x.jpg", image_bytes())})).status_code == 403
    assert (await admin_client.post("/panel/account/photo/remove")).status_code == 403


async def test_photo_has_dedicated_input_limit(admin_client):
    response = await admin_client.post("/panel/account/photo", files={"photo": ("large.png", b"x" * (5 * 1024 * 1024 + 1))})
    assert response.status_code == 413
    assert not list(settings.upload_path.rglob("*.webp"))


async def test_photo_is_only_current_identity(admin_client, db_session):
    admin = await login_role(admin_client, db_session, "admin")
    await admin_client.post("/panel/account/photo", files={"photo": ("x.jpg", image_bytes())})
    original = photo_path(admin.id).read_bytes()
    editor = await login_role(admin_client, db_session, "editor")
    assert (await admin_client.get(f"/panel/account/photo?user_id={admin.id}")).status_code == 404
    await admin_client.post("/panel/account/photo", data={"user_id": admin.id}, files={"photo": ("x.jpg", image_bytes("blue"))})
    assert photo_path(admin.id).read_bytes() == original and photo_path(editor.id).exists()
    await admin_client.post("/panel/account/photo/remove", data={"user_id": admin.id})
    assert photo_path(admin.id).read_bytes() == original


async def test_photo_counts_toward_quota_and_survives_legacy_migration(admin_client, db_session):
    user = await login_role(admin_client, db_session, "editor")
    user.media_quota_mb = 64
    db_session.add(user)
    path = settings.download_path / "full.zip"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as output:
        output.truncate(64 * 1024 * 1024)
    db_session.add(MediaAsset(owner_id=user.id, uploaded_by=user.username, path="/panel/media/files/full.zip"))
    await db_session.commit()
    response = await admin_client.post("/panel/account/photo", files={"photo": ("x.jpg", image_bytes())})
    assert response.status_code == 413 and not photo_path(user.id).exists()
    path.unlink()
    await admin_client.post("/panel/account/photo", files={"photo": ("x.jpg", image_bytes())})
    await migrate_legacy_local_downloads(db_session)
    assert photo_path(user.id).exists()


@pytest.mark.parametrize("role", ["admin", "manager", "editor"])
async def test_navigation_order_is_shared_and_updates_follow_stats(admin_client, db_session, role):
    await login_role(admin_client, db_session, role)
    if role != "editor":
        db_session.add(RegistrationRequest(username="pending-photo-test", password_hash="test-only"))
        await db_session.commit()
    html = (await admin_client.get("/panel", headers={"Accept": "text/html"})).text
    groups = re.findall(r'<div class="admin-nav-children">(.*?)</div>', html, re.S)
    desktop = re.findall(r'href="([^"]+)"', groups[1])
    mobile = re.findall(r'href="([^"]+)"', groups[3])
    assert desktop == mobile
    assert desktop[:3] == ["/panel/categories", "/panel/tags", "/panel/media"]
    if role != "editor":
        assert desktop[-1] == "/panel/settings"
        assert html.index('grid grid-cols-2') < html.index('id="dashboard-updates-title"')
    else:
        assert "/panel/settings" not in desktop and "/panel/users" not in desktop


@pytest.mark.parametrize("language", ["en", "es", "fr", "tr"])
def test_photo_copy_complete(language):
    from app.locales.profile_photos import COPY
    assert all(TRANSLATIONS[language].get(key) for key in COPY)


async def test_image_pixel_limit_is_enforced(admin_client, monkeypatch):
    monkeypatch.setattr("app.imaging.MAX_IMAGE_PIXELS", 100)
    response = await admin_client.post("/panel/account/photo", files={"photo": ("x.jpg", image_bytes())})
    assert response.status_code == 303 and not list(settings.upload_path.rglob("*.webp"))


async def test_photo_is_in_existing_backup_format(admin_client, db_session, tmp_path):
    from app.backups import write_archive, validate_archive
    await admin_client.post("/panel/account/photo", files={"photo": ("x.jpg", image_bytes())})
    archive = tmp_path / "incoming.zip"
    write_archive(archive)
    with zipfile.ZipFile(archive) as saved:
        assert saved.read("uploads/icons/.profiles/1.webp") == photo_path(1).read_bytes()
    validate_archive(tmp_path)


async def test_photo_storage_rejects_symlinks(admin_client, tmp_path):
    icons = settings.upload_path / "icons"
    icons.mkdir(parents=True, exist_ok=True)
    outside = tmp_path / "other-private-storage"
    outside.mkdir()
    (icons / ".profiles").symlink_to(outside, target_is_directory=True)
    response = await admin_client.post("/panel/account/photo", files={"photo": ("x.jpg", image_bytes())})
    assert response.status_code == 303 and not list(outside.iterdir())


async def test_profile_replacement_is_not_a_content_publication(admin_client, db_session):
    from app.models import Download
    user = await login_role(admin_client, db_session, "editor")
    db_session.add(Download(id=user.id, owner_id=user.id, title="Existing publication",
                           slug="existing-publication", external_url="https://example.com",
                           is_active=True, is_draft=False))
    await db_session.commit()
    for color in ("red", "blue"):
        response = await admin_client.post("/panel/account/photo", files={"photo": ("x.jpg", image_bytes(color))})
        assert response.status_code == 303

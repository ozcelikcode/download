"""Storage policy authorization, atomic replacement, and concurrent enforcement."""

import asyncio
import io
import json
from pathlib import Path
import zipfile

import pytest
from PIL import Image
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import settings
from app.dependencies import SESSION_COOKIE, create_admin_session_token, credential_stamp
from app.models import MediaAsset, SiteSettings, User
from app.storage_quota import MEBIBYTE, QUOTA_CHOICES, publish_media, quota_bytes, usage_bytes, validate_quota


async def _editor(db_session, client=None, role="editor"):
    admin = await db_session.scalar(select(User).where(User.username == "admin"))
    user = User(username=f"quota-{role}", password_hash=admin.password_hash, role=role, media_quota_mb=64)
    db_session.add(user)
    await db_session.commit()
    if client:
        client.cookies.set(SESSION_COOKIE, create_admin_session_token(user.username, user.password_hash, user_id=user.id), domain="test.local", path="/")
    return user


async def test_default_quota_update_does_not_require_password_but_keeps_csrf(admin_client, db_session):
    response = await admin_client.post('/panel/users/media-quota/defaults', data={'editor_quota_mb': 128, 'manager_quota_mb': 512})
    assert response.status_code == 303
    account = await db_session.scalar(select(SiteSettings).execution_options(populate_existing=True))
    assert (account.editor_media_quota_mb, account.manager_media_quota_mb) == (128, 512)
    page = await admin_client.get('/panel/users?section=storage')
    assert 'name="current_password"' not in page.text
    admin_client.headers.pop('X-CSRF-Token')
    assert (await admin_client.post('/panel/users/media-quota/defaults', data={'editor_quota_mb': 256, 'manager_quota_mb': 1024})).status_code == 403
    await db_session.refresh(account)
    assert account.editor_media_quota_mb == 128


def _sparse(path: Path, size: int):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as output:
        output.truncate(size)


async def _fill(db_session, user, size=64 * MEBIBYTE):
    path = settings.download_path / "occupied.zip"
    _sparse(path, size)
    db_session.add(MediaAsset(path="/panel/media/files/occupied.zip", owner_id=user.id, uploaded_by=user.username))
    await db_session.commit()
    return path


async def _context(db_session, user):
    account = await db_session.scalar(select(SiteSettings))
    return {"actor_id": user.id, "staff_role": user.role,
            "editor_owner_id": user.id if user.role == "editor" else None,
            "authenticated_credential": credential_stamp(user.username, user.password_hash),
            "authenticated_generation": account.session_generation}


def test_quota_validation_is_strict():
    for value in QUOTA_CHOICES:
        validate_quota(value)
    validate_quota(None, optional=True)
    for value in (0, -1, 65, True, "64", None):
        with pytest.raises(ValueError):
            validate_quota(value)


async def test_staging_files_are_not_served_or_listed(client, admin_client):
    public = settings.upload_path / "icons" / ".upload-secret.part"
    public.parent.mkdir(parents=True, exist_ok=True)
    public.write_bytes(b"unvalidated")
    private = settings.download_path / ".upload-private.part"
    private.write_bytes(b"NEVER-SERVE-STAGED-BYTES")
    response = await client.get("/static/uploads/icons/.upload-secret.part", headers={"Accept": "text/html"})
    assert response.status_code == 404 and "unvalidated" not in response.text
    response = await admin_client.get("/panel/media/files/.upload-private.part")
    assert response.status_code == 404 and "NEVER-SERVE-STAGED-BYTES" not in response.text
    response = await admin_client.get("/panel/media")
    assert response.status_code == 200 and ".upload-secret.part" not in response.text and ".upload-private.part" not in response.text


async def test_role_defaults_and_override(db_session):
    account = await db_session.scalar(select(SiteSettings))
    assert quota_bytes(User(role="editor"), account) == 256 * MEBIBYTE
    assert quota_bytes(User(role="manager"), account) == 1024 * MEBIBYTE
    assert quota_bytes(User(role="manager", media_quota_mb=64), account) == 64 * MEBIBYTE
    assert quota_bytes(User(role="admin", media_quota_mb=64), account) is None


@pytest.mark.parametrize("language", ["en", "es", "fr", "tr"])
async def test_full_quota_blocks_upload_and_cleans_stage(client, db_session, language):
    from app.i18n import TRANSLATIONS, set_ui_language
    user = await _editor(db_session, client)
    await _fill(db_session, user)
    set_ui_language(language)
    response = await client.post("/panel/media/upload-file", files={"file": ("extra.zip", b"extra", "application/zip")})
    assert response.status_code == 413
    assert response.json()["detail"] == TRANSLATIONS[language]["quota_exceeded"]
    assert [p.name for p in settings.download_path.iterdir()] == ["occupied.zip"]


async def test_denied_replacement_keeps_old_file(client, db_session):
    user = await _editor(db_session, client)
    original = await _fill(db_session, user)
    small = settings.download_path / "small.zip"
    small.write_bytes(b"old")
    db_session.add(MediaAsset(path="/panel/media/files/small.zip", owner_id=user.id))
    await db_session.commit()
    response = await client.post("/panel/media/replace-file", data={"path": "/panel/media/files/small.zip"}, files={"file": ("small.zip", b"bigger", "application/zip")})
    assert response.status_code == 413 and small.read_bytes() == b"old"
    assert original.stat().st_size == 64 * MEBIBYTE
    response = await client.post("/panel/media/replace-file", data={"path": "/panel/media/files/small.zip"}, files={"file": ("small.zip", b"x", "application/zip")})
    assert response.status_code == 200 and small.read_bytes() == b"x"
    assert not list(settings.download_path.glob(".*.part"))


async def test_aliases_are_counted_once_and_other_users_are_not(db_session):
    user = await _editor(db_session)
    path = await _fill(db_session, user, 12)
    db_session.add(MediaAsset(path="/admin/media/files/occupied.zip", owner_id=user.id))
    db_session.add(MediaAsset(path="/panel/media/files/missing.zip", owner_id=user.id))
    await db_session.commit()
    assert await usage_bytes(db_session, user.id) == 12
    assert await usage_bytes(db_session, 1) == 0
    assert path.exists()


async def test_concurrent_uploads_cannot_overrun_quota(db_session):
    user = await _editor(db_session)
    await _fill(db_session, user, 64 * MEBIBYTE - 4)
    context = await _context(db_session, user)
    await db_session.commit()
    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)

    async def attempt(number):
        staged = settings.download_path / f".test-{number}.part"
        staged.write_bytes(b"four")
        try:
            async with factory() as session:
                session.info.update(context)
                await publish_media(session, staged, settings.download_path / f"new-{number}.zip")
                return 200
        except HTTPException as exc:
            return exc.status_code
        finally:
            staged.unlink(missing_ok=True)

    assert sorted(await asyncio.gather(attempt(1), attempt(2))) == [200, 413]
    assert await usage_bytes(db_session, user.id) == 64 * MEBIBYTE


async def test_revoked_actor_cannot_publish(db_session):
    user = await _editor(db_session)
    context = await _context(db_session, user)
    user.is_active = False
    await db_session.commit()
    staged = settings.download_path / ".revoked.part"
    staged.parent.mkdir(parents=True, exist_ok=True)
    staged.write_bytes(b"data")
    try:
        db_session.info.update(context)
        with pytest.raises(HTTPException) as error:
            await publish_media(db_session, staged, settings.download_path / "revoked.zip")
        assert error.value.status_code == 403
        assert not (settings.download_path / "revoked.zip").exists()
    finally:
        staged.unlink(missing_ok=True)


async def test_quota_controls_are_admin_only(client, db_session):
    await _editor(db_session, client, role="manager")
    assert (await client.post("/panel/users/media-quota/defaults", data={"editor_quota_mb": 64, "manager_quota_mb": 128, "current_password": "wrong"})).status_code == 403
    assert (await client.post("/panel/users/1/media-quota", data={"quota_mb": 64, "current_password": "wrong"})).status_code == 403
    page = await client.get("/panel/users")
    assert page.status_code == 200 and 'name="quota_mb"' not in page.text


async def test_admin_quota_change_requires_password_and_preserves_files(admin_client, db_session, monkeypatch):
    from app.routers import users
    user = await _editor(db_session)
    path = await _fill(db_session, user)
    response = await admin_client.post(f"/panel/users/{user.id}/media-quota", data={"quota_mb": 128, "current_password": "wrong"})
    assert response.status_code == 303
    await db_session.refresh(user)
    assert user.media_quota_mb == 64
    async def correct_password(*_args):
        return True
    monkeypatch.setattr(users, "verify_password_async", correct_password)
    response = await admin_client.post("/panel/users/media-quota/defaults", data={"editor_quota_mb": 128, "manager_quota_mb": 512, "current_password": "verified"})
    assert response.status_code == 303
    response = await admin_client.post(f"/panel/users/{user.id}/media-quota", data={"quota_mb": "", "current_password": "verified"})
    assert response.status_code == 303
    await db_session.refresh(user)
    account = await db_session.scalar(select(SiteSettings).execution_options(populate_existing=True))
    assert user.media_quota_mb is None and quota_bytes(user, account) == 128 * MEBIBYTE
    assert account.manager_media_quota_mb == 512 and path.is_file()
    assert (await admin_client.get("/panel/users")).status_code == 200


@pytest.mark.parametrize("operation", ["image", "crop", "remote", "content", "appearance"])
async def test_every_media_creation_path_enforces_quota(client, db_session, monkeypatch, operation):
    from app.routers import admin
    import httpx
    role = "manager" if operation == "appearance" else "editor"
    user = await _editor(db_session, client, role=role)
    await _fill(db_session, user)
    buffer = io.BytesIO()
    Image.new("RGB", (32, 32), "red").save(buffer, format="PNG")
    image = buffer.getvalue()
    if operation == "crop":
        src = settings.upload_path / "icons" / "owned.png"
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_bytes(image)
        db_session.add(MediaAsset(path="/static/uploads/icons/owned.png", owner_id=user.id))
        await db_session.commit()
        response = await client.post("/panel/upload/icon-auto-crop", data={"path": "/static/uploads/icons/owned.png"})
        assert src.read_bytes() == image
    elif operation == "remote":
        original_client = httpx.AsyncClient
        async def resolve(_url):
            return "93.184.216.34"
        monkeypatch.setattr(admin, "resolve_public_url", resolve)
        monkeypatch.setattr(admin, "AsyncSessionLocal", async_sessionmaker(db_session.bind, expire_on_commit=False))
        monkeypatch.setattr(admin.httpx, "AsyncClient", lambda **kw: original_client(transport=httpx.MockTransport(lambda _r: httpx.Response(200, headers={"content-type": "image/png"}, content=image)), **kw))
        response = await client.post("/panel/upload/icon-image-url", data={"url": "https://example.com/icon.png", "token": "quota-remote"})
        assert response.status_code == 200
        response = await client.get("/panel/upload/progress/quota-remote")
        assert response.json()["done"] and response.json()["path"] is None
        assert response.json()["error"] and "authenticated_credential" not in response.text
    elif operation == "content":
        response = await client.post("/panel/downloads/new", data={"submission_intent": "publish", "title": "Quota", "file_type": "local"}, files={"upload_file": ("new.zip", b"data", "application/zip")})
    elif operation == "appearance":
        response = await client.post("/panel/settings/appearance", files={"logo_light_file": ("logo.png", image, "image/png")})
    else:
        response = await client.post("/panel/upload/icon-image", files={"file": ("icon.png", image, "image/png")})
    if operation != "remote":
        assert response.status_code == 413
    assert not list(settings.download_path.glob(".*.part"))
    assert not list(settings.upload_path.rglob(".*.part"))
    assert list(settings.upload_path.rglob("*.png")) == ([src] if operation == "crop" else [])


async def test_failed_database_commit_restores_replaced_file(db_session, monkeypatch):
    user = await _editor(db_session)
    original = await _fill(db_session, user, 3)
    original.write_bytes(b"old")
    db_session.info.update(await _context(db_session, user))
    staged = settings.download_path / ".failure.part"
    staged.write_bytes(b"new")
    commit = db_session.commit
    count = 0
    async def fail_final_commit():
        nonlocal count
        count += 1
        if count == 2:
            raise RuntimeError("Simulated database failure")
        await commit()
    monkeypatch.setattr(db_session, "commit", fail_final_commit)
    try:
        with pytest.raises(RuntimeError):
            await publish_media(db_session, staged, original)
        assert original.read_bytes() == b"old"
        assert not list(settings.download_path.glob(".replace-*.part"))
    finally:
        staged.unlink(missing_ok=True)


async def test_failed_filesystem_recovery_retains_old_bytes(db_session, monkeypatch):
    user = await _editor(db_session)
    original = await _fill(db_session, user, 3)
    original.write_bytes(b"old")
    db_session.info.update(await _context(db_session, user))
    staged = settings.download_path / ".failure.part"
    staged.write_bytes(b"new")
    commit = db_session.commit
    replace = Path.replace
    count = 0
    async def fail_final_commit():
        nonlocal count
        count += 1
        if count == 2:
            raise RuntimeError("Simulated commit failure")
        await commit()
    def fail_recovery(path, target):
        if path.name.startswith(".replace-"):
            raise OSError("Simulated recovery failure")
        return replace(path, target)
    monkeypatch.setattr(db_session, "commit", fail_final_commit)
    monkeypatch.setattr(Path, "replace", fail_recovery)
    try:
        with pytest.raises(OSError):
            await publish_media(db_session, staged, original)
        recovery = list(settings.download_path.glob(".replace-*.part"))
        assert len(recovery) == 1 and recovery[0].read_bytes() == b"old"
    finally:
        staged.unlink(missing_ok=True)


@pytest.mark.parametrize("legacy", [True, False])
async def test_backup_quota_validation_and_previous_schema(db_session, legacy):
    from app import backups
    stage = backups.new_stage()
    try:
        backups.write_archive(stage / "incoming.zip")
        with zipfile.ZipFile(stage / "incoming.zip") as archive:
            manifest = json.loads(archive.read("manifest.json"))
            data = json.loads(archive.read("data.json"))
        if legacy:
            del data["site_settings"][0]["image_compression_enabled"]
            del data["site_settings"][0]["image_compression_level"]
            for user in data["users"]:
                del user["profile_icon"]
            manifest["schema"] = backups.schema_fingerprint(before_quotas=True)
            del data["site_settings"][0]["favicon_path"]
            del data["site_settings"][0]["editor_media_quota_mb"]
            del data["site_settings"][0]["manager_media_quota_mb"]
            for user in data["users"]:
                del user["media_quota_mb"]
        else:
            data["users"][0]["media_quota_mb"] = -1
        with zipfile.ZipFile(stage / "incoming.zip", "w") as archive:
            archive.writestr("manifest.json", json.dumps(manifest))
            archive.writestr("data.json", json.dumps(data))
        if legacy:
            _, imported = backups.validate_archive(stage)
            assert imported["site_settings"][0]["editor_media_quota_mb"] == 256
            assert imported["users"][0]["media_quota_mb"] is None
        else:
            with pytest.raises(backups.BackupError):
                backups.validate_archive(stage)
    finally:
        backups.remove_stage(stage)

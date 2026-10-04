"""Isolated coverage for visibility, retention, encrypted export and reviewed restore."""

import base64
from datetime import datetime, timedelta, timezone
import json
import hashlib
import os
import shutil
import subprocess
import struct
import zipfile

import pytest
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import select, text

from app import backups, crud
from app.backup_restore import restore_site
from app.config import settings
from app.dependencies import SESSION_COOKIE, create_admin_session_token, hash_admin_password
from app.models import BackupPolicy, Category, Download, Page, SiteSettings, User
from app.trash_retention import RETENTION_DAYS, purge_expired_trash

PASSWORD = "a unique maintenance test password"


@pytest.fixture(scope="module")
def key_pair():
    private = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    pem = private.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    return private, pem


async def password(session):
    actor = await session.scalar(select(User).where(User.role == "admin"))
    actor.password_hash = hash_admin_password(PASSWORD)
    await session.commit()
    return actor


def login(client, actor):
    client.cookies.set(SESSION_COOKIE, create_admin_session_token(actor.username, actor.password_hash, user_id=actor.id), domain="test.local", path="/")


def decrypt(path, private):
    contents = path.read_bytes()
    assert contents[:8] == backups.MAGIC
    size = struct.unpack(">I", contents[8:12])[0]
    prefix = contents[:12 + size]
    header = json.loads(contents[12:12 + size])
    key = private.decrypt(base64.b64decode(header["wrapped_key"]), padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
    return AESGCM(key).decrypt(base64.b64decode(header["iv"]), contents[12 + size:], prefix)


async def test_hidden_content_blocks_all_public_paths(admin_client, client, db_session):
    item = Download(title="Hidden regression", slug="hidden-regression", external_url="https://example.com", is_active=True)
    db_session.add(item)
    await db_session.commit()
    assert (await client.get("/download/hidden-regression")).status_code == 200
    result = await admin_client.post("/admin/downloads/bulk", data={"action": "hide", "download_ids": [item.id]})
    assert result.status_code == 302
    await db_session.refresh(item)
    assert item.is_hidden and item.is_active
    assert (await client.get("/download/hidden-regression")).status_code == 404
    assert "hidden-regression" not in (await client.get("/sitemap.xml")).text
    assert "Hidden regression" not in (await client.get("/")).text
    assert "Hidden regression" in (await admin_client.get("/admin/downloads?status_filter=hidden")).text


async def test_form_and_category_move_layout(admin_client, db_session):
    db_session.add(Category(name="Layout source", slug="layout-source"))
    await db_session.commit()
    html = (await admin_client.get("/admin/categories")).text
    assert 'id="category-move-modal"' in html and 'data-lucide="arrow-right"' in html
    html = (await admin_client.get("/admin/downloads/new")).text
    assert html.index('name="is_featured"') < html.index('name="is_active"') < html.index('name="is_hidden"')


async def test_retention_off_and_pending_family_safe(db_session):
    old = datetime.now(timezone.utc) - timedelta(days=70)
    parent = Download(title="Pending family", slug="pending-family", deleted_at=old)
    expired = Download(title="Expired", slug="expired", deleted_at=old)
    fresh = Download(title="Fresh", slug="fresh", deleted_at=datetime.now(timezone.utc))
    page = Page(title="Expired page", slug="expired-page", body_html="<p>Text</p>", deleted_at=old)
    db_session.add_all([parent, expired, fresh, page])
    await db_session.flush()
    child = Download(title="Pending child", slug="pending-child", parent_id=parent.id, deleted_at=old, deletion_pending=True)
    db_session.add(child)
    await db_session.commit()
    assert await purge_expired_trash(db_session) == 0
    account = await crud.get_site_settings(db_session)
    account.trash_retention_days = 30
    await db_session.commit()
    assert await purge_expired_trash(db_session) == 2
    remaining = list(await db_session.scalars(select(Download)))
    assert {row.slug for row in remaining} == {"pending-family", "pending-child", "fresh"}
    assert not db_session.info.get("audit_suppressed")


@pytest.mark.parametrize("days", RETENTION_DAYS + (0,))
async def test_retention_choices_and_countdown(admin_client, db_session, days):
    actor = await password(db_session)
    login(admin_client, actor)
    response = await admin_client.post("/admin/settings/maintenance/retention", data={"days": days, "current_password": PASSWORD})
    assert response.status_code == 303
    db_session.expire_all()
    assert (await crud.get_site_settings(db_session)).trash_retention_days == (days or None)
    item = Download(title="Timed trash", slug="timed-trash", deleted_at=datetime.now(timezone.utc))
    db_session.add(item)
    await db_session.commit()
    html = (await admin_client.get("/admin/downloads/trash")).text
    assert ('data-trash-expires=' in html) == bool(days)


async def test_backup_admin_boundaries_and_csrf(client, db_session):
    for role in ("editor", "manager"):
        user = User(username="backup-" + role, password_hash=hash_admin_password(PASSWORD), role=role)
        db_session.add(user)
        await db_session.commit()
        login(client, user)
        assert (await client.get("/admin/backups")).status_code == 403
        assert (await client.get("/admin/backups/status")).status_code == 403
        assert (await client.post("/admin/backups/manual", data={"current_password": PASSWORD})).status_code == 403


async def test_key_schedule_and_queue(admin_client, db_session, key_pair):
    actor = await password(db_session)
    login(admin_client, actor)
    assert (await admin_client.get("/admin/backups")).status_code == 200
    data = {"public_key": key_pair[1], "current_password": PASSWORD, "recovery_saved": "true"}
    assert (await admin_client.post("/admin/backups/key", data=data)).status_code == 303
    assert (await db_session.get(BackupPolicy, 1)).public_key == key_pair[1]
    assert (await admin_client.post("/admin/backups/schedule", data={"current_password": PASSWORD, "enabled": "true", "interval_days": 3})).status_code == 303
    assert (await admin_client.post("/admin/backups/manual", data={"current_password": PASSWORD})).status_code == 303
    db_session.expire_all()
    policy = await db_session.get(BackupPolicy, 1)
    assert policy.interval_days == 3 and policy.enabled and policy.requested
    html = (await admin_client.get("/admin/backups")).text
    assert 'id="backup-import-form"' in html and 'name="private_key"' not in html


async def test_encrypted_exports_retention_and_tampering(db_session, key_pair, tmp_path):
    private, pem = key_pair
    (settings.upload_path / "test.png").write_bytes(b"raster fixture")
    paths = [backups.create_backup(pem) for _ in range(9)]
    files = backups.list_backups()
    assert len(files) == 8 and paths[0] not in files and files[0] == paths[-1]
    plain = decrypt(files[0], private)
    stage = backups.new_stage()
    (stage / "incoming.zip").write_bytes(plain)
    manifest, data = backups.validate_archive(stage)
    assert "backup_policy" not in data and manifest["format"] == 1
    assert (stage / "extracted/uploads/test.png").read_bytes() == b"raster fixture"
    with pytest.raises(backups.BackupError, match="backup_latest_protected"):
        backups.delete_backup(files[0].name)
    backups.delete_backup(files[-1].name)
    assert len(backups.list_backups()) == 7
    damaged = tmp_path / "damaged.dbackup"
    contents = bytearray(files[0].read_bytes()); contents[-1] ^= 1; damaged.write_bytes(contents)
    with pytest.raises(InvalidTag):
        decrypt(damaged, private)
    backups.remove_stage(stage)


async def test_failed_backup_does_not_prune(db_session, key_pair, monkeypatch):
    backups.create_backup(key_pair[1])
    before = backups.list_backups()
    def fail(*args):
        raise OSError("storage full")
    monkeypatch.setattr(backups, "encrypt_archive", fail)
    with pytest.raises(OSError):
        backups.create_backup(key_pair[1])
    assert backups.list_backups() == before


@pytest.mark.parametrize("name", ["../data.json", "uploads/../../outside", "/etc/passwd", "uploads\\evil", "app/main.py"])
async def test_import_rejects_unsafe_members(db_session, name):
    stage = backups.new_stage()
    with zipfile.ZipFile(stage / "incoming.zip", "w") as archive:
        archive.writestr(name, "unsafe")
    with pytest.raises(backups.BackupError, match="backup_invalid"):
        backups.validate_archive(stage)
    backups.remove_stage(stage)


async def test_restore_transaction_and_media(db_session):
    actor = await password(db_session)
    account = await crud.get_site_settings(db_session)
    account.site_name = "Before snapshot"
    await db_session.commit()
    (settings.upload_path / "old.png").write_bytes(b"original")
    stage = backups.new_stage()
    backups.write_archive(stage / "incoming.zip")
    account.site_name = "Changed after snapshot"
    (settings.upload_path / "old.png").write_bytes(b"changed")
    (settings.upload_path / "extra.png").write_bytes(b"new")
    await db_session.commit()
    await db_session.execute(text("BEGIN IMMEDIATE"))
    await restore_site(db_session, stage, actor)
    db_session.expunge_all()
    account = await crud.get_site_settings(db_session)
    assert account.site_name == "Before snapshot" and account.session_generation
    assert (settings.upload_path / "old.png").read_bytes() == b"original"
    assert not (settings.upload_path / "extra.png").exists()
    assert not stage.exists() and not (backups.backup_root() / "restore.json").exists()
    actor = await db_session.scalar(select(User).where(User.username == "admin"))
    assert actor.password_hash.startswith("scrypt$") and actor.role == "admin"


async def test_restore_rolls_back_if_media_swap_fails(db_session, monkeypatch):
    actor = await password(db_session)
    stage = backups.new_stage()
    backups.write_archive(stage / "incoming.zip")
    account = await crud.get_site_settings(db_session)
    account.site_name = "Keep this site"
    await db_session.commit()
    original = backups.install_media
    def fail(directory):
        original(directory)
        raise OSError("simulated interrupted swap")
    monkeypatch.setattr(backups, "install_media", fail)
    with pytest.raises(OSError):
        await restore_site(db_session, stage, actor)
    db_session.expunge_all()
    assert (await crud.get_site_settings(db_session)).site_name == "Keep this site"
    assert not stage.exists()


async def test_shipped_webcrypto_generate_and_import(db_session):
    node = shutil.which("node") or os.environ.get("BACKUP_TEST_NODE")
    if not node:
        pytest.skip("Optional browser Web Crypto compatibility test requires Node.js")
    def browser(data):
        result = subprocess.run([node, "tests/backup_webcrypto.cjs"], input=json.dumps(data), text=True, capture_output=True, check=True, timeout=45)
        return json.loads(result.stdout)
    generated = browser({"mode": "generate", "password": PASSWORD})
    backup = backups.create_backup(generated["publicKey"])
    result = browser({"mode": "import", "password": PASSWORD, "recovery": generated["recovery"], "backup": base64.b64encode(backup.read_bytes()).decode()})
    private_bytes = AESGCM(hashlib.pbkdf2_hmac("sha256", PASSWORD.encode(), base64.b64decode(generated["recovery"]["salt"]), 600000)).decrypt(base64.b64decode(generated["recovery"]["iv"]), base64.b64decode(generated["recovery"]["encrypted_private_key"]), None)
    private = serialization.load_der_private_key(private_bytes, password=None)
    assert result["digest"] == hashlib.sha256(decrypt(backup, private)).hexdigest()
    assert set(result["fields"]) == {"current_password", "csrf_token", "file"}


async def test_reviewed_import_restore_route(admin_client, db_session, key_pair):
    actor = await password(db_session)
    login(admin_client, actor)
    policy = BackupPolicy(id=1, public_key=key_pair[1])
    db_session.add(policy)
    await db_session.commit()
    stage = backups.new_stage()
    backups.write_archive(stage / "incoming.zip")
    plain = (stage / "incoming.zip").read_bytes()
    backups.remove_stage(stage)
    account = await crud.get_site_settings(db_session)
    account.site_name = "Current site confirmation"
    await db_session.commit()
    response = await admin_client.post("/admin/backups/import", data={"current_password": PASSWORD}, files={"file": ("incoming.zip", plain, "application/zip")})
    assert response.status_code == 200
    url = response.json()["redirect_url"]
    assert (await admin_client.get(url)).status_code == 200
    token = url.split("stage=", 1)[1]
    wrong = await admin_client.post("/admin/backups/restore", data={"current_password": PASSWORD, "token": token, "confirmation": "Wrong name", "irreversible": "true"})
    assert wrong.status_code == 303
    db_session.expire_all()
    assert (await crud.get_site_settings(db_session)).site_name == "Current site confirmation"
    response = await admin_client.post("/admin/backups/restore", data={"current_password": PASSWORD, "token": token, "confirmation": "Current site confirmation", "irreversible": "true"})
    assert response.status_code == 303 and response.headers["location"] == "/login"
    db_session.expunge_all()
    assert (await crud.get_site_settings(db_session)).site_name == "Download Sitesi"
    assert (await db_session.get(BackupPolicy, 1)).public_key == key_pair[1]
    assert len(backups.list_backups()) == 1  # Required pre-restore safety backup.
    assert (await admin_client.get("/admin/backups")).status_code != 200


async def test_scheduler_interval_and_manual_off_mode(db_session, monkeypatch, key_pair):
    from app import maintenance_jobs
    from sqlalchemy.ext.asyncio import async_sessionmaker
    monkeypatch.setattr(maintenance_jobs, "AsyncSessionLocal", async_sessionmaker(db_session.bind, expire_on_commit=False))
    policy = BackupPolicy(id=1, public_key=key_pair[1], enabled=False, interval_days=3)
    db_session.add(policy)
    await db_session.commit()
    await maintenance_jobs.tick()
    assert not backups.list_backups()
    policy.requested = True
    await db_session.commit()
    await maintenance_jobs.tick()
    assert len(backups.list_backups()) == 1
    db_session.expire_all()
    policy = await db_session.get(BackupPolicy, 1)
    assert policy.last_success and not policy.requested and not policy.error_code
    policy.enabled = True
    await db_session.commit()
    await maintenance_jobs.tick()
    assert len(backups.list_backups()) == 1
    policy.last_success = datetime.now(timezone.utc) - timedelta(days=4)
    policy.last_attempt = datetime.now(timezone.utc) - timedelta(minutes=11)
    await db_session.commit()
    await maintenance_jobs.tick()
    assert len(backups.list_backups()) == 2

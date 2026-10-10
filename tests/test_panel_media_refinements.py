"""Media archive isolation, safe scans and browser upload regressions."""

import io
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest
from PIL import Image
from sqlalchemy import select

from app.config import settings
from app.models import Download, MediaAsset


def test_database_engine_hides_private_sql_parameters():
    from app.database import engine

    assert engine.sync_engine.hide_parameters is True


def test_media_lists_use_bounded_responsive_tracks():
    root = Path(__file__).resolve().parents[1] / "app"
    template = (root / "templates/admin/media.html").read_text()
    css = (root / "static/css/app.css").read_text()
    assert template.count('class="media-card media-list-row ') == 2
    assert template.count('class="media-list-links"') == 2
    assert 'grid-template-columns: auto minmax(0, 1fr)' in css
    assert '.media-list-links, .media-list-actions { grid-column: 1 / -1; min-width: 0; }' in css


def test_panel_media_upload_interactions():
    node = os.environ.get("BACKUP_TEST_NODE") or shutil.which("node")
    if not node:
        pytest.skip("Node is required for media interaction checks")
    subprocess.run([node, str(Path(__file__).parent / "js" / "media-upload.mjs")], check=True, capture_output=True, text=True)


async def test_gallery_assets_appear_in_archive_and_preserve_used_media(admin_client, db_session):
    buffer = io.BytesIO()
    Image.new("RGB", (48, 32), "blue").save(buffer, "PNG")
    uploaded = await admin_client.post("/panel/upload/gallery-image", files={"file": ("screen.png", buffer.getvalue(), "image/png")})
    path = uploaded.json()["path"]
    served = await admin_client.get(path)
    assert served.status_code == 200 and served.headers["content-type"] == "image/webp"
    page = await admin_client.get("/panel/media")
    assert f'data-media-path="{path}"' in page.text
    # Gallery images must remain canonical compressed WebP, not icon-crop targets.
    card = page.text.split(f'data-media-path="{path}"', 1)[1].split('data-media-path=', 1)[0]
    assert 'data-action="autocrop"' not in card and 'data-action="edit"' not in card
    asset = await db_session.scalar(select(MediaAsset).where(MediaAsset.path == path))
    item = Download(title="Gallery reference", slug="gallery-reference", gallery_images=json.dumps([path]), owner_id=asset.owner_id)
    db_session.add(item)
    await db_session.commit()
    assert (await admin_client.post("/panel/media/delete-file", data={"path": path})).status_code == 409
    assert (settings.upload_path / path.removeprefix("/static/uploads/")).is_file()


async def test_configured_upload_mount_never_serves_hidden_files_or_escaping_symlinks(client, tmp_path):
    root = settings.upload_path
    (root / ".private.png").write_bytes(b"NEVER-SERVE-HIDDEN-BYTES")
    outside = tmp_path / "private.png"
    outside.write_bytes(b"NEVER-SERVE-OUTSIDE-BYTES")
    (root / "linked.png").symlink_to(outside)
    for path in ("/static/uploads/.private.png", "/static/uploads/linked.png"):
        response = await client.get(path)
        assert response.status_code == 404
        assert b"NEVER-SERVE-HIDDEN-BYTES" not in response.content and b"NEVER-SERVE-OUTSIDE-BYTES" not in response.content


async def test_failed_metadata_deletion_restores_original_file(admin_client, db_session, monkeypatch):
    from app import crud

    uploaded = await admin_client.post("/panel/media/upload-file", files={"file": ("fixture.zip", b"preserved original bytes", "application/zip")})
    path = uploaded.json()["path"]
    file = settings.download_path / uploaded.json()["name"]

    async def failure(session, path):
        raise RuntimeError("Simulated database failure")

    monkeypatch.setattr(crud, "delete_media_asset", failure)
    with pytest.raises(RuntimeError, match="Simulated database failure"):
        await admin_client.post("/panel/media/delete-file", data={"path": path})
    assert file.read_bytes() == b"preserved original bytes"
    assert list(settings.download_path.iterdir()) == [file]
    assert await db_session.scalar(select(MediaAsset).where(MediaAsset.path == path))


async def test_media_delete_rechecks_revoked_actor_under_lock(admin_client, db_session, monkeypatch):
    from app import media
    from app.models import User

    uploaded = await admin_client.post("/panel/media/upload-file", files={"file": ("fixture.zip", b"original", "application/zip")})
    path = uploaded.json()["path"]
    original = media.ensure_unused

    async def revoke_before_lock(session, value, origin=None):
        actor = await db_session.scalar(select(User).where(User.username == "admin"))
        actor.is_active = False
        await db_session.commit()
        return await original(session, value, origin)

    monkeypatch.setattr(media, "ensure_unused", revoke_before_lock)
    response = await admin_client.post("/panel/media/delete-file", data={"path": path})
    assert response.status_code == 403
    assert (settings.download_path / uploaded.json()["name"]).read_bytes() == b"original"


async def test_media_delete_normalizes_alias_and_hides_recovery_file(admin_client, client, db_session):
    uploaded = await admin_client.post("/panel/media/upload-file", files={"file": ("fixture.zip", b"original", "application/zip")})
    path = uploaded.json()["path"]
    alias = "http://test" + path
    response = await admin_client.post("/panel/media/delete-file", data={"path": alias})
    assert response.status_code == 200
    assert await db_session.scalar(select(MediaAsset).where(MediaAsset.path == path)) is None
    recovery = settings.download_path / ".delete-recovery.part"
    recovery.write_bytes(b"private")
    assert (await admin_client.get("/panel/media/files/.delete-recovery.part")).status_code == 404
    assert (await admin_client.post("/panel/media/delete-file", data={"path": "/panel/media/files/.delete-recovery.part"})).status_code == 400
    assert recovery.read_bytes() == b"private"


def test_media_scan_hides_private_files_and_escaping_symlinks(tmp_path):
    from app.routers.admin import _list_media_files
    root = tmp_path / "icons"
    root.mkdir()
    (root / ".private.png").write_bytes(b"private")
    (root / "visible.png").write_bytes(b"image")
    outside = tmp_path / "private.png"
    outside.write_bytes(b"outside")
    (root / "linked.png").symlink_to(outside)
    items = _list_media_files(root, "/static/uploads/icons")
    assert [item["name"] for item in items] == ["visible.png"]


def test_media_scan_tolerates_concurrent_deletion(tmp_path, monkeypatch):
    from app.routers.admin import _list_media_files
    path = tmp_path / "removed.png"
    path.write_bytes(b"image")
    original = Path.stat
    calls = 0

    def raced(self, *args, **kwargs):
        nonlocal calls
        if self == path:
            calls += 1
            if calls == 2:
                raise FileNotFoundError("Concurrent deletion")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", raced)
    assert _list_media_files(tmp_path, "/static/uploads/icons") == []

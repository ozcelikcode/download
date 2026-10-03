"""Editor isolation is enforced for lists, IDs, references, uploads, and deletion review."""

import pytest
from sqlalchemy import select

from app.config import settings
from app.dependencies import SESSION_COOKIE, create_admin_session_token, hash_admin_password
from app.models import Category, Download, DownloadTag, DownloadVersionHistory, MediaAsset, Tag, User


async def staff(session):
    editor = User(username="owner-editor", password_hash=hash_admin_password("a unique editor password"), role="editor")
    other = User(username="other-editor", password_hash=editor.password_hash, role="editor")
    manager = User(username="review-manager", password_hash=editor.password_hash, role="manager")
    session.add_all([editor, other, manager])
    await session.commit()
    return editor, other, manager


def login(client, session, user):
    session.info.clear()
    client.cookies.set(SESSION_COOKIE, create_admin_session_token(user.username, user.password_hash, user_id=user.id), domain="test.local", path="/")


async def test_editor_lists_and_direct_access_are_personal(client, db_session):
    editor, other, _ = await staff(db_session)
    mine = Download(title="My isolated content", slug="my-isolated", external_url="https://example.com", owner_id=editor.id)
    theirs = Download(title="Other private draft", slug="other-private", owner_id=other.id, is_draft=True)
    site = Download(title="Legacy site content", slug="legacy-site")
    cat = Category(name="Site category secret", slug="site-category")
    tag = Tag(name="Site tag secret", slug="site-tag")
    db_session.add_all([mine, theirs, site, cat, tag])
    await db_session.commit()
    login(client, db_session, editor)
    for path in ("/admin", "/admin/downloads", "/admin/downloads/new", "/admin/categories", "/admin/tags"):
        response = await client.get(path)
        assert response.status_code == 200
        for hidden in (theirs.title, site.title, cat.name, tag.name):
            assert hidden not in response.text
    assert (await client.get(f"/admin/downloads/{mine.id}/edit")).status_code == 200
    for item in (theirs, site):
        assert (await client.get(f"/admin/downloads/{item.id}/edit")).status_code == 404
        assert (await client.get(f"/admin/downloads/{item.id}/preview")).status_code == 404
        assert (await client.post(f"/admin/downloads/{item.id}/delete")).status_code == 404
    overview = (await client.get("/admin")).text
    assert "Çalışma alanım" in overview
    assert 'href="/admin/site-health"' not in overview
    assert 'href="/admin/audit"' not in overview
    from app import crud
    db_session.info["editor_owner_id"] = editor.id
    assert (await crud.get_dashboard_stats(db_session))["total_downloads"] == 1
    _, total = await crud.get_downloads_paginated(db_session, page=1, include_inactive=True)
    assert total == 1


@pytest.mark.parametrize("field", ["category_id", "parent_id", "tag_ids", "icon_image_final_path"])
async def test_editor_cannot_attach_foreign_references(client, db_session, field):
    editor, other, _ = await staff(db_session)
    category = Category(name="Foreign category", slug="foreign-category", owner_id=other.id)
    tag = Tag(name="Foreign tag", slug="foreign-tag", owner_id=other.id)
    download = Download(title="Foreign parent", slug="foreign-parent", owner_id=other.id)
    asset = MediaAsset(path="/static/uploads/icons/foreign.png", owner_id=other.id)
    db_session.add_all([category, tag, download, asset])
    await db_session.commit()
    values = {"category_id": str(category.id), "parent_id": str(download.id), "tag_ids": str(tag.id), "icon_image_final_path": asset.path}
    login(client, db_session, editor)
    response = await client.post("/admin/downloads/drafts/autosave", data={
        "title": "My draft", "draft_token": "own-draft-token", "file_type": "external",
        field: values[field],
    })
    assert response.status_code == 404


async def test_editor_drafts_and_definitions_receive_stable_ownership(client, db_session):
    editor, other, _ = await staff(db_session)
    login(client, db_session, editor)
    saved = await client.post("/admin/downloads/drafts/autosave", data={"title": "Owned draft", "draft_token": "personal-token"})
    assert saved.status_code == 200
    draft_id = saved.json()["draft_id"]
    assert (await client.post("/admin/categories", data={"name": "Shared name"})).status_code == 302
    assert (await client.post("/admin/tags", data={"name": "Shared label"})).status_code == 302
    login(client, db_session, other)
    assert (await client.get(f"/admin/downloads/{draft_id}/edit")).status_code == 404
    assert (await client.post("/admin/categories", data={"name": "Shared name"})).status_code == 302
    assert (await client.post("/admin/tags", data={"name": "Shared label"})).status_code == 302
    db_session.info.clear()
    assert (await db_session.scalar(select(Download).where(Download.id == draft_id))).owner_id == editor.id
    categories = list(await db_session.scalars(select(Category).where(Category.name == "Shared name")))
    assert {category.owner_id for category in categories} == {editor.id, other.id}
    assert len(set(category.slug for category in categories)) == 2


async def test_editor_media_isolation_covers_listing_and_all_mutations(client, db_session):
    editor, other, _ = await staff(db_session)
    root = settings.download_path
    root.mkdir(parents=True, exist_ok=True)
    (root / "mine.zip").write_bytes(b"mine")
    (root / "theirs.zip").write_bytes(b"theirs")
    own_path = "/admin/media/files/mine.zip"
    foreign_path = "/admin/media/files/theirs.zip"
    db_session.add_all([MediaAsset(path=own_path, owner_id=editor.id), MediaAsset(path=foreign_path, owner_id=other.id)])
    await db_session.commit()
    login(client, db_session, editor)
    response = await client.get("/admin/media?tab=files")
    assert response.status_code == 200
    assert "mine.zip" in response.text and "theirs.zip" not in response.text
    assert (await client.get(own_path)).status_code == 200
    assert (await client.get(foreign_path)).status_code == 404
    for route in ("/admin/media/rename", "/admin/media/delete-file", "/admin/upload/icon-image-delete", "/admin/upload/icon-auto-crop"):
        assert (await client.post(route, data={"path": foreign_path, "display_name": "Changed"})).status_code == 404
    assert (await client.post("/admin/media/replace-file", data={"path": foreign_path}, files={"file": ("new.zip", b"changed", "application/zip")})).status_code == 404
    assert (root / "theirs.zip").read_bytes() == b"theirs"


@pytest.mark.parametrize("review", ["reject", "purge", "restore"])
async def test_editor_deletion_is_reviewed_by_staff(client, db_session, review):
    editor, other, manager = await staff(db_session)
    item = Download(title="Review my removal", slug="review-removal", owner_id=editor.id)
    db_session.add(item)
    await db_session.commit()
    item_id = item.id
    login(client, db_session, editor)
    assert (await client.post(f"/admin/downloads/{item.id}/delete")).status_code == 302
    trash = (await client.get("/admin/downloads/trash")).text
    assert item.title in trash and "Silme onayı bekliyor" in trash
    assert 'value="purge"' not in trash and 'value="reject"' not in trash
    assert (await client.post("/admin/downloads/trash/bulk", data={"action": "purge", "download_ids": str(item.id)})).status_code == 403
    assert (await client.post("/admin/downloads/trash/bulk", data={"action": "reject", "download_ids": str(item.id)})).status_code == 403
    login(client, db_session, other)
    assert item.title not in (await client.get("/admin/downloads/trash")).text
    login(client, db_session, manager)
    assert item.title in (await client.get("/admin/downloads/trash")).text
    if review == "restore":
        login(client, db_session, editor)
    response = await client.post("/admin/downloads/trash/bulk", data={"action": review, "download_ids": str(item.id)})
    assert response.status_code == 302
    db_session.info.clear()
    db_session.expire_all()
    saved = await db_session.scalar(select(Download).where(Download.id == item_id))
    if review == "purge":
        assert saved is None
    else:
        assert saved.deleted_at is None and not saved.deletion_pending


async def test_foreign_version_history_and_bulk_actions_are_blocked(client, db_session):
    editor, other, _ = await staff(db_session)
    item = Download(title="Other item", slug="other-item", owner_id=other.id)
    db_session.add(item)
    await db_session.flush()
    entry = DownloadVersionHistory(download_id=item.id, version="1.0")
    db_session.add(entry)
    await db_session.commit()
    login(client, db_session, editor)
    assert (await client.post(f"/admin/downloads/{item.id}/version-history/{entry.id}/edit", data={"version": "2.0"})).status_code == 404
    assert (await client.post(f"/admin/downloads/{item.id}/version-history/{entry.id}/delete")).status_code == 404
    assert (await client.post("/admin/downloads/bulk", data={"action": "delete", "download_ids": str(item.id)})).status_code == 302
    db_session.info.clear()
    await db_session.refresh(item)
    assert item.deleted_at is None


async def test_editor_cannot_change_media_used_by_another_owner(client, db_session):
    editor, other, _ = await staff(db_session)
    root = settings.download_path
    root.mkdir(parents=True, exist_ok=True)
    (root / "shared.zip").write_bytes(b"original")
    path = "/admin/media/files/shared.zip"
    db_session.add_all([
        MediaAsset(path=path, owner_id=editor.id),
        Download(title="Hidden staff usage", slug="staff-usage", owner_id=other.id, file_type="local", file_path=str(root / "shared.zip")),
    ])
    await db_session.commit()
    login(client, db_session, editor)
    deletion = await client.post("/admin/media/delete-file", data={"path": path})
    assert deletion.status_code == 409
    assert "Hidden staff usage" not in deletion.text
    replacement = await client.post("/admin/media/replace-file", data={"path": path}, files={"file": ("replacement.zip", b"changed", "application/zip")})
    assert replacement.status_code == 409
    assert (root / "shared.zip").read_bytes() == b"original"


async def test_editor_upload_and_publication_keep_ownership(client, db_session):
    editor, _, _ = await staff(db_session)
    login(client, db_session, editor)
    uploaded = await client.post("/admin/media/upload-file", files={"file": ("owned.zip", b"download contents", "application/zip")})
    assert uploaded.status_code == 200
    response = await client.post("/admin/downloads/new", data={
        "title": "My local file", "file_type": "local", "submission_intent": "publish",
        "file_final_path": uploaded.json()["storage_path"], "is_active": "true",
    })
    assert response.status_code == 302
    item = await db_session.scalar(select(Download).where(Download.title == "My local file"))
    asset = await db_session.scalar(select(MediaAsset).where(MediaAsset.path == uploaded.json()["path"]))
    assert item.owner_id == editor.id and asset.owner_id == editor.id


async def test_editor_cannot_read_or_overwrite_foreign_upload_progress(client, db_session, monkeypatch):
    from app.routers import admin
    editor, other, _ = await staff(db_session)
    monkeypatch.setattr(admin, "_icon_fetch_progress", {"foreign-token": {"owner_id": other.id, "done": False, "path": "hidden"}})
    login(client, db_session, editor)
    assert (await client.get("/admin/upload/progress/foreign-token")).status_code == 404
    assert (await client.post("/admin/upload/icon-image-url", data={"token": "foreign-token", "url": "https://example.com/icon.png"})).status_code == 409
    assert admin._icon_fetch_progress["foreign-token"]["owner_id"] == other.id


@pytest.mark.parametrize("kind", ["categories", "tags"])
async def test_editor_cannot_modify_taxonomy_used_by_another_owner(client, db_session, kind):
    editor, other, _ = await staff(db_session)
    model = Category if kind == "categories" else Tag
    definition = model(name="My shared definition", slug="shared-definition", owner_id=editor.id)
    db_session.add(definition)
    await db_session.flush()
    item = Download(title="Other owner's content", slug="other-owned-content", owner_id=other.id)
    if kind == "categories":
        item.category_id = definition.id
    db_session.add(item)
    await db_session.flush()
    if kind == "tags":
        db_session.add(DownloadTag(download_id=item.id, tag_id=definition.id))
    await db_session.commit()
    login(client, db_session, editor)
    response = await client.post(f"/admin/{kind}/{definition.id}/edit", data={"name": "Changed definition"})
    assert response.status_code == 409
    assert "Other owner's content" not in response.text
    await db_session.refresh(definition)
    assert definition.name == "My shared definition"

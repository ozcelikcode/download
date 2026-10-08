"""Regression coverage for shared categories, publication review, and correspondence."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select

from app import crud
from app.models import AuditLog, Category, Download, DownloadVersionHistory, EditorMessage, MediaAsset, User
from app.dependencies import SESSION_COOKIE, create_admin_session_token, hash_admin_password

PASSWORD = "a long unique workflow password"


async def accounts(session):
    digest = hash_admin_password(PASSWORD)
    users = [User(username=name, role=role, password_hash=digest) for name, role in (
        ("editor-first", "editor"), ("editor-second", "editor"), ("workflow-manager", "manager"))]
    session.add_all(users)
    await session.commit()
    return users


def login(client, user):
    client.cookies.set(SESSION_COOKIE, create_admin_session_token(user.username, user.password_hash, user_id=user.id), domain="test.local", path="/")


async def test_required_category_is_shared_read_only_and_usable(client, db_session):
    first, second, manager = await accounts(db_session)
    login(client, manager)
    await client.get("/panel/categories")
    category = await db_session.scalar(select(Category).where(Category.is_required.is_(True)))
    assert category.owner_id is None
    assert (await client.post(f"/panel/categories/{category.id}/edit", data={"name": "Shared defaults"})).status_code == 302
    for user in (first, second):
        login(client, user)
        page = await client.get("/panel/categories")
        assert "Shared defaults" in page.text
        assert f'id="cat-edit-{category.id}"' not in page.text
        assert (await client.post(f"/panel/categories/{category.id}/edit", data={"name": "Forbidden"})).status_code == 403
        response = await client.post("/panel/downloads/drafts/autosave", data={"title": "Using shared category", "draft_token": user.username, "category_id": str(category.id)})
        assert response.status_code == 200
        assert (await client.post(f"/panel/categories/{category.id}/move", data={"target_category_id": category.id})).status_code in (403, 422)
    await db_session.refresh(category)
    assert category.name == "Shared defaults"
    assert await db_session.scalar(select(func.count()).select_from(Category).where(Category.is_required.is_(True))) == 1


async def test_category_move_includes_trash_and_drafts_without_copying(client, db_session):
    editor, _, _ = await accounts(db_session)
    a = Category(name="Source A", slug="source-a", owner_id=editor.id)
    b = Category(name="Target B", slug="target-b", is_required=True)
    db_session.add_all([a, b])
    await db_session.flush()
    items = [Download(title=f"Move {i}", slug=f"move-{i}", category_id=a.id, owner_id=editor.id,
                      is_draft=i == 1, deleted_at=datetime.now(timezone.utc) if i == 2 else None) for i in range(3)]
    db_session.add_all(items)
    await db_session.commit()
    login(client, editor)
    assert (await client.post(f"/panel/categories/{a.id}/move", data={"target_category_id": b.id})).status_code == 302
    db_session.expire_all()
    categories = list(await db_session.scalars(select(Category)))
    moved = list(await db_session.scalars(select(Download)))
    assert len(categories) == 2 and len(moved) == 3
    assert all(item.category_id == categories[1].id for item in moved)


async def test_category_move_denies_foreign_target_and_shared_source(client, db_session):
    first, second, _ = await accounts(db_session)
    a = Category(name="Mine", slug="mine", owner_id=first.id)
    b = Category(name="Not mine", slug="not-mine", owner_id=second.id)
    required = Category(name="Global", slug="global", is_required=True)
    db_session.add_all([a, b, required])
    await db_session.commit()
    login(client, first)
    assert (await client.post(f"/panel/categories/{a.id}/move", data={"target_category_id": b.id})).status_code == 404
    assert (await client.post(f"/panel/categories/{required.id}/move", data={"target_category_id": a.id})).status_code == 403


@pytest.mark.parametrize("verified", [False, True])
async def test_publication_requires_review_unless_verified(client, db_session, verified):
    editor, _, manager = await accounts(db_session)
    editor.is_verified = verified
    await db_session.commit()
    login(client, editor)
    response = await client.post("/panel/downloads/new", data={"title": "Editorial submission", "description": "Useful application documentation. " * 10, "file_type": "external", "external_url": "https://example.com/download", "is_active": "true", "submission_intent": "publish"})
    assert response.status_code == 302
    item = await db_session.scalar(select(Download).where(Download.title == "Editorial submission"))
    assert item.is_active == verified and item.publication_pending != verified
    public = await client.get(f"/download/{item.slug}")
    assert public.status_code == (200 if verified else 404)
    assert (await client.get("/panel/review")).status_code == 403
    if not verified:
        assert (await client.post(f"/panel/review/{item.id}", data={"action": "approve", "revision": item.updated_at.isoformat()})).status_code == 403
        login(client, manager)
        assert "Editorial submission" in (await client.get("/panel/review")).text
        assert (await client.post(f"/panel/review/{item.id}", data={"action": "approve", "revision": item.updated_at.isoformat()})).status_code == 303
        await db_session.refresh(item)
        assert item.is_active and not item.publication_pending
        assert (await client.get(f"/download/{item.slug}")).status_code == 200


async def test_rejection_returns_draft_with_private_feedback(client, db_session):
    editor, other, manager = await accounts(db_session)
    item = Download(title="Needs revision", slug="needs-revision", owner_id=editor.id, is_active=False, publication_pending=True)
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)
    login(client, manager)
    await client.post(f"/panel/review/{item.id}", data={"action": "reject", "reason": "Add a proper description", "revision": item.updated_at.isoformat()})
    await db_session.refresh(item)
    assert item.is_draft and not item.is_active and not item.publication_pending
    login(client, editor)
    assert "Add a proper description" in (await client.get(f"/panel/downloads/{item.id}/edit")).text
    login(client, other)
    assert (await client.get(f"/panel/downloads/{item.id}/edit")).status_code == 404


async def test_unverified_edits_cannot_keep_an_approved_publication_live(client, db_session):
    editor, _, _ = await accounts(db_session)
    item = Download(title="Previously approved", slug="previously-approved", owner_id=editor.id, external_url="https://example.com", is_active=True)
    db_session.add(item)
    await db_session.commit()
    login(client, editor)
    response = await client.post(f"/panel/downloads/{item.id}/edit", data={"title": "Changed publication", "file_type": "external", "external_url": "https://example.com/new", "is_active": "true", "submission_intent": "publish"})
    assert response.status_code == 302
    await db_session.refresh(item)
    assert not item.is_active and item.publication_pending


@pytest.mark.parametrize("role", ["admin", "manager"])
async def test_verification_without_password_requires_staff_and_editor_target(client, db_session, role):
    editor, other, manager = await accounts(db_session)
    actor = manager if role == "manager" else await db_session.scalar(select(User).where(User.role == "admin"))
    if role == "admin":
        actor.password_hash = hash_admin_password(PASSWORD)
        await db_session.commit()
    login(client, actor)
    assert (await client.post(f"/panel/users/{editor.id}/verification", data={"verified": "true"})).status_code == 303
    await db_session.refresh(editor)
    assert editor.is_verified
    assert (await client.post(f"/panel/users/{actor.id}/verification", data={"verified": "true"})).status_code == 404
    login(client, other)
    assert (await client.post(f"/panel/users/{editor.id}/verification", data={"verified": "true"})).status_code == 403


async def test_private_contact_scopes_messages_escapes_text_and_accepts_staff_reply(client, db_session):
    editor, other, manager = await accounts(db_session)
    login(client, editor)
    assert (await client.post("/panel/contact", data={"subject": "Private question", "body": "<script>alert('private')</script>"})).status_code == 303
    item = await db_session.scalar(select(EditorMessage))
    page = (await client.get("/panel/contact")).text
    assert "&lt;script&gt;" in page and "<script>alert('private')</script>" not in page
    login(client, other)
    assert "Private question" not in (await client.get("/panel/contact")).text
    assert (await client.post(f"/panel/contact/{item.id}/reply", data={"response": "Forbidden reply"})).status_code == 403
    login(client, manager)
    assert "Private question" in (await client.get("/panel/contact")).text
    assert (await client.post(f"/panel/contact/{item.id}/reply", data={"response": "Staff answer"})).status_code == 303
    login(client, editor)
    assert "Staff answer" in (await client.get("/panel/contact")).text
    logs = list(await db_session.scalars(select(AuditLog)))
    assert all("alert('private')" not in log.label + log.changes and "Staff answer" not in log.label + log.changes for log in logs)


async def test_contact_limits_and_csrf_are_enforced(client, db_session):
    editor, _, _ = await accounts(db_session)
    login(client, editor)
    for i in range(6):
        assert (await client.post("/panel/contact", data={"subject": f"Question {i}", "body": "Problem details"})).status_code == 303
    assert await db_session.scalar(select(func.count()).select_from(EditorMessage)) == 5
    assert (await client.post("/panel/contact", data={"subject": "Too long", "body": "x" * 5001})).status_code == 422
    client.headers.pop("X-CSRF-Token")
    assert (await client.post("/panel/contact", data={"subject": "CSRF", "body": "No token"})).status_code == 403


async def test_new_translation_keys_are_complete():
    from app.locales.workflows import STRINGS
    assert all(set(values) == set(STRINGS["en"]) for values in STRINGS.values())


async def test_bulk_publish_cannot_bypass_review(client, db_session):
    editor, _, _ = await accounts(db_session)
    item = Download(title="Bulk draft", slug="bulk-draft", description="Useful application documentation. " * 10, is_draft=True, is_active=False,
                    owner_id=editor.id, external_url="https://example.com")
    db_session.add(item)
    await db_session.commit()
    login(client, editor)
    response = await client.post("/panel/downloads/bulk", data={"action": "publish", "download_ids": str(item.id)})
    assert response.status_code == 302
    await db_session.refresh(item)
    assert item.publication_pending and not item.is_active and not item.is_draft


async def test_stale_review_cannot_approve_changed_content(client, db_session):
    _, _, manager = await accounts(db_session)
    item = Download(title="Changed during review", slug="changed-during-review", is_active=False, publication_pending=True)
    db_session.add(item)
    await db_session.commit()
    login(client, manager)
    response = await client.post(f"/panel/review/{item.id}", data={"action": "approve", "revision": "2000-01-01T00:00:00"})
    assert response.status_code == 303
    await db_session.refresh(item)
    assert item.publication_pending and not item.is_active


@pytest.mark.parametrize("role,verified,color", [("editor", True, "publisher-badge--editor"), ("admin", False, "publisher-badge--admin"), ("manager", False, "publisher-badge--manager"), ("editor", False, None)])
async def test_public_publisher_badge_matches_role(client, db_session, role, verified, color):
    publisher = User(username="public-publisher", role=role, is_verified=verified, password_hash=hash_admin_password(PASSWORD))
    db_session.add(publisher)
    await db_session.flush()
    db_session.add(Download(title="Publisher record", slug="publisher-record", owner_id=publisher.id, external_url="https://example.com"))
    await db_session.commit()
    response = await client.get("/download/publisher-record")
    assert response.status_code == 200 and publisher.username in response.text
    if color:
        assert color in response.text and 'data-lucide="badge-check"' in response.text
    else:
        assert 'publisher-badge--' not in response.text


async def test_editor_write_refreshes_revoked_verification(db_session):
    from app.schemas import DownloadCreate
    editor, _, _ = await accounts(db_session)
    db_session.info.update(editor_owner_id=editor.id, actor_id=editor.id, staff_role="editor", verified_editor=True)
    item = await crud.create_download(db_session, DownloadCreate(title="Revoked trust", description="Useful application documentation. " * 10, external_url="https://example.com", is_active=True))
    assert item.publication_pending and not item.is_active


async def test_invalid_editor_form_returns_validation_page_not_server_error(client, db_session):
    editor, _, _ = await accounts(db_session)
    item = Download(title="Validation recovery", slug="validation-recovery", owner_id=editor.id, external_url="https://example.com")
    db_session.add(item)
    await db_session.commit()
    login(client, editor)
    response = await client.post(f"/panel/downloads/{item.id}/edit", data={"title": "Valid title", "external_url": "invalid"})
    assert response.status_code == 422


async def test_live_media_replacement_cannot_bypass_editor_review(client, db_session):
    from app.config import settings
    editor, _, _ = await accounts(db_session)
    root = settings.download_path
    root.mkdir(parents=True, exist_ok=True)
    path = root / "approved.zip"
    path.write_bytes(b"approved contents")
    db_session.add_all([
        MediaAsset(path="/panel/media/files/approved.zip", owner_id=editor.id),
        Download(title="Approved binary", slug="approved-binary", owner_id=editor.id,
                 file_type="local", file_path=str(path), is_active=True),
    ])
    await db_session.commit()
    login(client, editor)
    response = await client.post("/panel/media/replace-file", data={"path": "/panel/media/files/approved.zip"}, files={"file": ("replacement.zip", b"unreviewed", "application/zip")})
    assert response.status_code == 409
    assert path.read_bytes() == b"approved contents"


async def test_public_version_history_changes_require_review(client, db_session):
    editor, _, _ = await accounts(db_session)
    item = Download(title="History policy", slug="history-policy", owner_id=editor.id, external_url="https://example.com", is_active=True)
    db_session.add(item)
    await db_session.flush()
    entry = DownloadVersionHistory(download_id=item.id, version="1.0")
    db_session.add(entry)
    await db_session.commit()
    login(client, editor)
    assert (await client.post(f"/panel/downloads/{item.id}/version-history/{entry.id}/edit", data={"version": "2.0"})).status_code == 302
    await db_session.refresh(item)
    assert item.publication_pending and not item.is_active


async def test_verified_editor_can_publish_a_previously_pending_item(client, db_session):
    editor, _, _ = await accounts(db_session)
    editor.is_verified = True
    item = Download(title="Newly verified", slug="newly-verified", owner_id=editor.id, external_url="https://example.com", is_active=False, publication_pending=True)
    db_session.add(item)
    await db_session.commit()
    login(client, editor)
    await client.post("/panel/downloads/bulk", data={"action": "publish", "download_ids": str(item.id)})
    await db_session.refresh(item)
    assert item.is_active and not item.publication_pending

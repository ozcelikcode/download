"""User-screen organization and role-isolated notification navigation."""

from datetime import datetime, timezone

from sqlalchemy import select

from app.dependencies import SESSION_COOKIE, create_admin_session_token
from app.models import AuditLog, Download, EditorMessage, RegistrationRequest, User


async def test_user_screen_separates_accounts_creation_and_quota(admin_client):
    accounts = await admin_client.get("/panel/users")
    assert accounts.status_code == 200 and '<details' not in accounts.text.split('id="staff-accounts"', 1)[1]
    assert 'name="editor_quota_mb"' not in accounts.text
    assert 'name="username"' not in accounts.text
    storage = await admin_client.get("/panel/users?section=storage")
    assert storage.status_code == 200 and 'type="radio" name="editor_quota_mb"' in storage.text
    assert '<select name="editor_quota_mb"' not in storage.text
    creation = await admin_client.get("/panel/users?section=new")
    assert creation.status_code == 200 and 'name="username"' in creation.text


async def test_staff_notifications_link_to_pending_requests(admin_client, db_session):
    db_session.add(RegistrationRequest(username="pending-notice", password_hash="test-only"))
    await db_session.commit()
    response = await admin_client.get("/panel/notifications")
    assert response.status_code == 200 and response.json()["counters"]["registrations"] == 1
    assert "pending-notice" not in response.text and "test-only" not in response.text
    response = await admin_client.post("/panel/notifications/open", data={"kind": "registrations"})
    assert response.status_code == 303 and response.headers["location"] == "/panel/registrations"
    data = (await admin_client.get("/panel/notifications")).json()
    assert data["unread"] == 0 and data["counters"]["registrations"] == 1


async def test_editor_notices_never_show_foreign_or_staff_data(client, db_session):
    admin = await db_session.scalar(select(User).where(User.username == "admin"))
    editor = User(username="notice-editor", role="editor", password_hash=admin.password_hash)
    other = User(username="foreign-editor", role="editor", password_hash=admin.password_hash)
    db_session.add_all([editor, other])
    await db_session.flush()
    db_session.add_all([
        EditorMessage(sender_id=editor.id, subject="own", body="private", response="answer", responded_at=datetime.now(timezone.utc)),
        EditorMessage(sender_id=other.id, subject="foreign", body="secret", response="private answer", responded_at=datetime.now(timezone.utc)),
        RegistrationRequest(username="staff-only", password_hash="secret"),
    ])
    await db_session.commit()
    client.cookies.set(SESSION_COOKIE, create_admin_session_token(editor.username, editor.password_hash, user_id=editor.id), domain="test.local", path="/")
    data = (await client.get("/panel/notifications")).json()
    assert data["unread"] == 1 and data["counters"] == {"contact": 1, "content": 0}
    assert "secret" not in str(data) and "foreign" not in str(data)
    assert (await client.post("/panel/notifications/open", data={"kind": "registrations"})).status_code == 404
    assert (await client.post("/panel/notifications/open", data={"kind": "contact"})).status_code == 303
    assert (await client.get("/panel/notifications")).json()["unread"] == 0
    assert (await client.get("/panel/users?section=storage")).status_code == 403


async def test_notifications_require_authentication_and_csrf(client, admin_client):
    assert (await client.get("/panel/notifications")).status_code == 302
    admin_client.headers.pop("X-CSRF-Token")
    assert (await admin_client.post("/panel/notifications/open", data={"kind": "contact"})).status_code == 403


async def test_editor_receives_only_owned_publication_decisions(client, db_session):
    admin = await db_session.scalar(select(User).where(User.username == "admin"))
    editor = User(username="review-notice-editor", role="editor", password_hash=admin.password_hash)
    db_session.add(editor)
    await db_session.flush()
    own = Download(title="Owned", slug="own-notice", owner_id=editor.id)
    other = Download(title="Foreign", slug="foreign-notice", owner_id=admin.id)
    db_session.add_all([own, other])
    await db_session.flush()
    db_session.add_all([AuditLog(actor="admin", action="approve", entity="publication", entity_id=own.id, label="Editorial review completed"),
                        AuditLog(actor="admin", action="reject", entity="publication", entity_id=other.id, label="Editorial review completed")])
    await db_session.commit()
    client.cookies.set(SESSION_COOKIE, create_admin_session_token(editor.username, editor.password_hash, user_id=editor.id), domain="test.local", path="/")
    assert (await client.get("/panel/notifications")).json()["counters"]["content"] == 1
    assert (await client.post("/panel/notifications/open", data={"kind": "content"})).headers["location"] == "/panel/downloads"
    assert (await client.get("/panel/notifications")).json()["unread"] == 0


async def test_staff_user_deletion_counter(admin_client, db_session):
    admin = await db_session.scalar(select(User).where(User.username == "admin"))
    user = User(username="delete-notice-editor", role="editor", password_hash=admin.password_hash, deletion_requested_by="manager")
    db_session.add(user)
    await db_session.commit()
    data = (await admin_client.get("/panel/notifications")).json()
    assert data["counters"]["users"] == 1 and data["unread"] == 1

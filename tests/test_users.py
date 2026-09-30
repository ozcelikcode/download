"""Server-side role boundaries, deletion review, and administrator continuity."""

from sqlalchemy import func, select

from app.dependencies import SESSION_COOKIE, create_admin_session_token, hash_admin_password
from app.models import AuditLog, Page, User


PASSWORD = "a long unique staff password"


async def _staff_cookie(client, db_session, role: str, username: str) -> User:
    user = User(username=username, password_hash=hash_admin_password(PASSWORD), role=role)
    db_session.add(user)
    await db_session.commit()
    client.cookies.set(SESSION_COOKIE, create_admin_session_token(username, user.password_hash, user_id=user.id), domain="test.local", path="/")
    return user


async def test_editor_cannot_reach_settings_or_private_page(client, db_session):
    await _staff_cookie(client, db_session, "editor", "editor-one")
    assert (await client.get("/admin/categories")).status_code == 200
    assert (await client.get("/admin/settings")).status_code == 403
    assert (await client.get("/admin/audit")).status_code == 403
    assert (await client.get("/admin/users")).status_code == 403
    assert (await client.get("/admin/settings/account")).status_code == 200


async def test_manager_delete_request_needs_admin_review(client, db_session):
    editor = await _staff_cookie(client, db_session, "editor", "editor-two")
    await _staff_cookie(client, db_session, "manager", "manager-one")
    private_page = Page(title="Confidential", slug="confidential", body_html="secret", visibility="private", is_published=True)
    db_session.add(private_page)
    await db_session.commit()
    assert (await client.get("/admin/settings/general")).status_code == 200
    assert (await client.get("/admin/settings/maintenance")).status_code == 403
    assert (await client.get("/admin/audit")).status_code == 403
    assert (await client.get(f"/admin/pages/{private_page.id}/edit")).status_code == 404
    assert (await client.get("/page/confidential")).status_code == 404
    assert (await client.post("/admin/pages", data={"title": "Secret", "visibility": "private"})).status_code == 403
    assert (await client.post(f"/admin/users/{editor.id}/request-delete")).status_code == 303
    await db_session.refresh(editor)
    assert editor.deletion_requested_by is not None and editor.is_active
    assert (await client.post(f"/admin/users/1/request-delete")).status_code == 403


async def test_admin_can_replace_another_but_not_last_admin(client, db_session):
    first = await db_session.scalar(select(User).where(User.username == "admin"))
    first.password_hash = hash_admin_password(PASSWORD)
    await db_session.commit()
    client.cookies.set(SESSION_COOKIE, create_admin_session_token(first.username, first.password_hash, user_id=first.id), domain="test.local", path="/")
    created = await client.post("/admin/users", data={"username": "second-admin", "password": PASSWORD, "role": "admin", "current_password": PASSWORD})
    assert created.status_code == 303
    second = await db_session.scalar(select(User).where(User.username == "second-admin"))
    assert second is not None
    assert (await client.post(f"/admin/users/{first.id}/delete", data={"current_password": PASSWORD})).status_code == 303
    await db_session.refresh(first)
    assert not first.is_active
    assert (await client.get("/admin/users")).status_code == 302
    client.cookies.set(SESSION_COOKIE, create_admin_session_token(second.username, second.password_hash, user_id=second.id), domain="test.local", path="/")
    assert (await client.post(f"/admin/users/{second.id}/delete", data={"current_password": PASSWORD})).status_code == 303
    await db_session.refresh(second)
    assert second.is_active
    count = await db_session.scalar(select(func.count()).select_from(User).where(User.role == "admin", User.is_active.is_(True)))
    assert count == 1


async def test_visitor_error_log_is_anonymous_and_path_free(client, db_session):
    from app.main import _recent_public_errors
    _recent_public_errors.clear()
    response = await client.get("/page/private-secret-that-must-not-be-logged")
    assert response.status_code == 404
    row = await db_session.scalar(select(AuditLog).where(AuditLog.entity == "request"))
    assert row.actor == "anonymous"
    assert "private-secret" not in row.label
    assert "127.0.0.1" not in row.changes


async def test_account_mutation_rechecks_actor_role_after_password_verification(admin_client, db_session, monkeypatch):
    from app.routers import users

    actor = await db_session.scalar(select(User).where(User.username == "admin"))
    target = User(username="remaining-admin", password_hash=actor.password_hash, role="admin")
    db_session.add(target)
    await db_session.commit()

    async def demote_actor_during_verification(password, stored_hash):
        actor.role = "editor"
        await db_session.commit()
        return True

    monkeypatch.setattr(users, "verify_password_async", demote_actor_during_verification)
    response = await admin_client.post(f"/admin/users/{target.id}/delete", data={"current_password": PASSWORD})
    assert response.status_code == 403
    await db_session.refresh(target)
    assert target.is_active

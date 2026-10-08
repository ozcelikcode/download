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
    assert (await client.get("/panel/categories")).status_code == 200
    assert (await client.get("/panel/settings")).status_code == 403
    assert (await client.get("/panel/audit")).status_code == 403
    assert (await client.get("/panel/users")).status_code == 403
    assert (await client.get("/panel/settings/account")).status_code == 200


async def test_manager_delete_request_needs_admin_review(client, db_session):
    editor = await _staff_cookie(client, db_session, "editor", "editor-two")
    await _staff_cookie(client, db_session, "manager", "manager-one")
    private_page = Page(title="Confidential", slug="confidential", body_html="secret", visibility="private", is_published=True)
    db_session.add(private_page)
    await db_session.commit()
    assert (await client.get("/panel/settings/general")).status_code == 200
    assert (await client.get("/panel/settings/maintenance")).status_code == 403
    assert (await client.get("/panel/audit")).status_code == 403
    assert (await client.get(f"/panel/pages/{private_page.id}/edit")).status_code == 404
    assert (await client.get("/page/confidential")).status_code == 404
    assert (await client.post("/panel/pages", data={"title": "Secret", "visibility": "private"})).status_code == 403
    assert (await client.post(f"/panel/users/{editor.id}/request-delete")).status_code == 303
    await db_session.refresh(editor)
    assert editor.deletion_requested_by is not None and editor.is_active
    assert (await client.post(f"/panel/users/1/request-delete")).status_code == 403


async def test_admin_can_replace_another_but_not_last_admin(client, db_session):
    first = await db_session.scalar(select(User).where(User.username == "admin"))
    first.password_hash = hash_admin_password(PASSWORD)
    await db_session.commit()
    client.cookies.set(SESSION_COOKIE, create_admin_session_token(first.username, first.password_hash, user_id=first.id), domain="test.local", path="/")
    created = await client.post("/panel/users", data={"username": "second-admin", "password": PASSWORD, "role": "admin", "current_password": PASSWORD})
    assert created.status_code == 303
    second = await db_session.scalar(select(User).where(User.username == "second-admin"))
    assert second is not None
    assert (await client.post(f"/panel/users/{first.id}/delete", data={"current_password": PASSWORD})).status_code == 303
    await db_session.refresh(first)
    assert not first.is_active
    assert (await client.get("/panel/users")).status_code == 302
    client.cookies.set(SESSION_COOKIE, create_admin_session_token(second.username, second.password_hash, user_id=second.id), domain="test.local", path="/")
    assert (await client.post(f"/panel/users/{second.id}/delete", data={"current_password": PASSWORD})).status_code == 303
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


async def test_account_mutation_rechecks_actor_role_under_write_lock(admin_client, db_session, monkeypatch):
    from app.routers import users

    actor = await db_session.scalar(select(User).where(User.username == "admin"))
    target = User(username="remaining-admin", password_hash=actor.password_hash, role="admin")
    db_session.add(target)
    await db_session.commit()

    original_lock = users._lock_actor

    async def demote_actor_before_lock(request, session, role, **kwargs):
        actor.role = "editor"
        await db_session.commit()
        return await original_lock(request, session, role, **kwargs)

    monkeypatch.setattr(users, "_lock_actor", demote_actor_before_lock)
    response = await admin_client.post(f"/panel/users/{target.id}/delete")
    assert response.status_code == 403
    await db_session.refresh(target)
    assert target.is_active


async def test_admin_user_actions_without_password(admin_client, db_session):
    actor = await db_session.scalar(select(User).where(User.username == "admin"))
    target = User(username="passwordless-editor", password_hash=actor.password_hash, role="editor")
    db_session.add(target)
    await db_session.commit()
    for operation, data in [("verification", {"verified": "true"}), ("role", {"role": "manager"}), ("delete", {})]:
        response = await admin_client.post(f"/panel/users/{target.id}/{operation}", data=data)
        assert response.status_code == 303
        await db_session.refresh(target)
        if operation == "verification":
            assert target.is_verified
        elif operation == "role":
            assert target.role == "manager"
        else:
            assert not target.is_active


async def test_manager_cannot_set_roles_without_password(client, db_session):
    actor = await db_session.scalar(select(User).where(User.username == "admin"))
    manager = User(username="role-manager", password_hash=actor.password_hash, role="manager")
    target = User(username="role-editor", password_hash=actor.password_hash, role="editor")
    db_session.add_all([manager, target])
    await db_session.commit()
    client.cookies.set(SESSION_COOKIE, create_admin_session_token(manager.username, manager.password_hash, user_id=manager.id), domain="test.local", path="/")
    response = await client.post(f"/panel/users/{target.id}/role", data={"role": "admin"})
    assert response.status_code == 403
    await db_session.refresh(target)
    assert target.role == "editor"
    page = await client.get("/panel/users")
    assert f'action="/panel/users/{target.id}/role"' not in page.text


async def test_passwordless_user_actions_still_require_csrf(admin_client, db_session):
    actor = await db_session.scalar(select(User).where(User.username == "admin"))
    target = User(username="csrf-editor", password_hash=actor.password_hash, role="editor")
    db_session.add(target)
    await db_session.commit()
    admin_client.headers.pop("X-CSRF-Token")
    for operation, data in [("verification", {"verified": "true"}), ("role", {"role": "manager"}), ("media-quota", {"quota_mb": "128"}), ("delete", {})]:
        assert (await admin_client.post(f"/panel/users/{target.id}/{operation}", data=data)).status_code == 403
    await db_session.refresh(target)
    assert target.role == "editor" and not target.is_verified and target.is_active


async def test_user_actions_have_no_password_fields(admin_client, db_session):
    page = await admin_client.get("/panel/users")
    assert page.status_code == 200
    assert 'name="current_password"' not in page.text


async def test_panel_toolbar_has_consistent_order(admin_client):
    page = await admin_client.get('/panel/users')
    toolbar = page.text.split('class="panel-toolbar"', 1)[1].split('</header>', 1)[0]
    controls = ['aria-label="Siteye Git"', 'id="theme-toggle-btn"', 'id="panel-messages-toggle"', 'class="btn-secondary panel-account-link"', 'action="/panel/logout"']
    positions = [toolbar.index(control) for control in controls]
    assert positions == sorted(positions)

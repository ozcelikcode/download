"""Global panel permissions, UTF-8 errors, legacy media, and self closure."""

import pytest
from html import unescape
from sqlalchemy import select

from app import crud
from app.dependencies import SESSION_COOKIE, create_admin_session_token, hash_admin_password
from app.i18n import set_ui_language, TRANSLATIONS
from app.media import media_path
from app.models import Category, Download, MediaAsset, Tag, User
from app.templating import templates

PASSWORD = "self-closure-password-1234"


async def sign_in(client, session, role="editor"):
    user = User(username="close-" + role, password_hash=hash_admin_password(PASSWORD), role=role)
    session.add(user)
    await session.commit()
    client.cookies.set(SESSION_COOKIE, create_admin_session_token(user.username, user.password_hash, user_id=user.id), domain="test.local", path="/")
    return user


@pytest.mark.parametrize("language", ["en", "es", "fr", "tr"])
async def test_permission_errors_are_localized_html_or_utf8_json(client, db_session, language):
    await sign_in(client, db_session)
    set_ui_language(language)
    templates.env.globals["site_language"] = language
    response = await client.get("/panel/audit", headers={"Accept": "text/html"})
    assert response.status_code == 403 and response.headers["content-type"].startswith("text/html")
    assert TRANSLATIONS[language]["permission_denied"] in unescape(response.text)
    assert response.headers["cache-control"] == "no-store"
    response = await client.get("/panel/audit", headers={"Accept": "application/json"})
    assert response.status_code == 403
    assert response.headers["content-type"] == "application/json; charset=utf-8"
    assert response.json()["detail"] == TRANSLATIONS[language]["permission_denied"]


async def test_legacy_bookmarks_do_not_bypass_permissions(client, db_session):
    await sign_in(client, db_session)
    response = await client.get("/admin/audit")
    assert response.status_code == 303 and response.headers["location"] == "/panel/audit"
    assert (await client.get(response.headers["location"])).status_code == 403
    assert (await client.get("/admin/login")).headers["location"] == "/login"
    assert (await client.post("/admin/users/1/delete", data={"current_password": PASSWORD})).status_code in {404, 405}


async def test_existing_media_metadata_survives_new_panel_prefix(db_session):
    path = "/admin/media/files/legacy.zip"
    db_session.add(MediaAsset(path=path, display_name="Legacy file"))
    await db_session.commit()
    new_path = "/panel/media/files/legacy.zip"
    assert media_path(path) == media_path(new_path)
    info = await crud.get_media_assets_info(db_session, [new_path])
    assert info[new_path].display_name == "Legacy file"
    await crud.set_media_display_name(db_session, new_path, "Updated file")
    assert (await db_session.scalar(select(MediaAsset).where(MediaAsset.path == path))).display_name == "Updated file"


@pytest.mark.parametrize("role", ["editor", "manager", "admin"])
async def test_account_closure_preserves_all_owned_data(client, db_session, role):
    user = await sign_in(client, db_session, role)
    original_username = user.username
    objects = [Category(name="Preserved", slug="preserved", owner_id=user.id),
               Tag(name="Preserved", slug="preserved", owner_id=user.id),
               MediaAsset(path="/static/uploads/icons/preserved.png", owner_id=user.id),
               Download(title="Preserved", slug="preserved", owner_id=user.id)]
    db_session.add_all(objects)
    await db_session.commit()
    identifiers = [obj.id for obj in objects]
    cookie = client.cookies.get(SESSION_COOKIE)
    response = await client.post("/panel/account/close", data={"current_password": PASSWORD, "confirmation": original_username, "acknowledged": "true", "user_id": 1})
    assert response.status_code == 303 and response.headers["location"] == "/login"
    await db_session.refresh(user)
    assert not user.is_active and user.deleted_at is not None and user.password_hash == ""
    assert user.username != original_username
    for obj, identifier in zip(objects, identifiers):
        await db_session.refresh(obj)
        assert obj.id == identifier and obj.owner_id == user.id
    assert (await db_session.get(User, 1)).is_active
    client.cookies.set(SESSION_COOKIE, cookie, domain="test.local", path="/")
    assert (await client.get("/panel")).headers["location"] == "/login"


@pytest.mark.parametrize("data", [
    {"current_password": "wrong", "confirmation": "close-editor", "acknowledged": "true"},
    {"current_password": PASSWORD, "confirmation": "someone-else", "acknowledged": "true"},
    {"current_password": PASSWORD, "confirmation": "close-editor"},
])
async def test_closure_requires_password_exact_username_and_ack(client, db_session, data):
    user = await sign_in(client, db_session)
    assert (await client.post("/panel/account/close", data=data)).status_code == 303
    await db_session.refresh(user)
    assert user.is_active and user.username == "close-editor"


async def test_last_administrator_cannot_close_account(admin_client, db_session):
    user = await db_session.scalar(select(User).where(User.username == "admin"))
    # Use a known test password without changing any real account.
    user.password_hash = hash_admin_password(PASSWORD)
    await db_session.commit()
    admin_client.cookies.set(SESSION_COOKIE, create_admin_session_token(user.username, user.password_hash, user_id=user.id), domain="test.local", path="/")
    response = await admin_client.post("/panel/account/close", data={"current_password": PASSWORD, "confirmation": "admin", "acknowledged": "true"})
    assert response.headers["location"] == "/panel/settings/account"
    await db_session.refresh(user)
    assert user.is_active and user.password_hash


async def test_closure_requires_csrf(client, db_session):
    user = await sign_in(client, db_session)
    del client.headers["X-CSRF-Token"]
    assert (await client.post("/panel/account/close", data={"current_password": PASSWORD, "confirmation": user.username, "acknowledged": "true"})).status_code == 403


async def test_last_admin_close_form_is_not_offered(admin_client):
    page = await admin_client.get('/panel/settings/account')
    assert page.status_code == 200
    assert 'action="/panel/account/close"' not in page.text
    assert TRANSLATIONS['tr']['last_admin_required'] in page.text


@pytest.mark.parametrize('role', ['editor', 'manager'])
async def test_non_admin_close_form_and_single_personal_icon(client, db_session, role):
    await sign_in(client, db_session, role)
    page = await client.get('/panel/settings/account')
    assert page.status_code == 200
    assert 'action="/panel/account/close"' in page.text
    assert page.text.count('action="/panel/account/icon"') == 1
    assert 'action="/panel/settings/avatar"' not in page.text
    assert 'avatar-color-radio' not in page.text
    assert 'href="https://lucide.dev/icons/"' in page.text
    assert 'name="icon" type="text"' in page.text


async def test_manual_profile_icon_is_personal_and_legacy_color_is_ignored(client, db_session):
    from app.models import SiteSettings
    user = await sign_in(client, db_session, 'manager')
    settings = await db_session.scalar(select(SiteSettings))
    old_branding = (settings.admin_icon, settings.admin_icon_color)
    response = await client.post('/panel/account/icon', data={'icon': '  rocket  ', 'color': 'red'})
    assert response.status_code == 303
    await db_session.refresh(user)
    assert user.profile_icon == 'rocket'
    assert (await db_session.get(User, 1)).profile_icon == 'user-circle'
    assert 'data-lucide="rocket"' in (await client.get('/panel')).text
    response = await client.post('/panel/settings/avatar', data={'admin_icon': 'leaf', 'admin_icon_color': 'red'})
    assert response.status_code == 303
    await db_session.refresh(settings)
    await db_session.refresh(user)
    assert user.profile_icon == 'leaf'
    assert (settings.admin_icon, settings.admin_icon_color) == old_branding


@pytest.mark.parametrize('icon', ['unknown-icon-name', '<svg onload=alert(1)>', 'user" onclick="alert(1)', 'a' * 51])
async def test_manual_profile_icon_rejects_unknown_and_markup(client, db_session, icon):
    user = await sign_in(client, db_session)
    assert (await client.post('/panel/account/icon', data={'icon': icon})).status_code == 303
    await db_session.refresh(user)
    assert user.profile_icon == 'user-circle'

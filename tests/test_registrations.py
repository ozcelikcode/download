"""Application privacy, public authentication links, and staff approval boundaries."""

from datetime import datetime, timedelta, timezone
from httpx import ASGITransport, AsyncClient
import json
import re
import zipfile

import pytest
from sqlalchemy import func, select

from app.dependencies import SESSION_COOKIE, create_admin_session_token, hash_admin_password, verify_admin_password
from app.i18n import TRANSLATIONS, set_ui_language
from app.locales.registrations import STRINGS
from app.models import AuditLog, LoginAttempt, RegistrationRequest, User
from app.templating import templates
from app import backups
from app.main import app

PASSWORD = "registration-password-for-tests"


def login(client, user):
    client.cookies.set(SESSION_COOKIE, create_admin_session_token(user.username, user.password_hash, user_id=user.id), domain="test.local", path="/")


async def staff(client, session, role):
    user = User(username="review-" + role, role=role, password_hash=hash_admin_password(PASSWORD))
    session.add(user)
    await session.commit()
    login(client, user)
    return user


async def submit(client, username="applicant", **extras):
    data = {"username": username, "password": PASSWORD, "password_confirmation": PASSWORD}
    data.update(extras)
    return await client.post("/register", data=data)


async def test_navbar_and_login_links(client):
    html = (await client.get("/")).text
    assert 'href="/login"' in html and 'href="/register"' not in html
    html = (await client.get("/login")).text
    assert 'href="/register"' in html
    response = await client.get("/register")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-robots-tag"] == "noindex, nofollow"


async def test_global_login_and_legacy_bookmark(client):
    response = await client.get("/login")
    assert response.status_code == 200
    assert 'action="/login"' in response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-robots-tag"] == "noindex, nofollow"
    legacy = await client.get("/panel/login")
    assert legacy.status_code == 303 and legacy.headers["location"] == "/login"
    assert (await client.get("/panel")).headers["location"] == "/login"


@pytest.mark.parametrize("role", ["admin", "manager"])
async def test_native_registration_form_reaches_staff_panel(client, db_session, role):
    html = (await client.get("/register")).text
    token = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
    del client.headers["X-CSRF-Token"]
    response = await client.post("/register", data={
        "username": "native-form-applicant", "password": PASSWORD,
        "password_confirmation": PASSWORD, "csrf_token": token,
    })
    assert response.status_code == 303
    assert STRINGS["tr"]["registration_received"] in (await client.get(response.headers["location"])).text
    pending = await db_session.scalar(select(RegistrationRequest).where(RegistrationRequest.username == "native-form-applicant"))
    assert pending is not None
    await staff(client, db_session, role)
    dashboard = (await client.get("/panel")).text
    assert 'href="/panel/registrations"' in dashboard
    card = re.search(r'<a[^>]*data-notice-kind="registrations"[^>]*>(.*?)</a>', dashboard, re.S)
    assert card is not None and re.search(r'class="panel-count[^\"]*">1</span>', card.group(1))
    assert "native-form-applicant" in (await client.get("/panel/registrations")).text


async def test_receipt_cannot_be_fabricated_with_query_parameter(client):
    response = await client.get("/register?received=true")
    assert STRINGS["tr"]["registration_received"] not in response.text
    assert 'action="/register"' in response.text


async def test_pending_is_hashed_not_an_account_and_cannot_login(client, db_session):
    response = await submit(client, role="admin", is_verified="true")
    assert response.status_code == 303
    row = await db_session.scalar(select(RegistrationRequest))
    assert row.password_hash.startswith("scrypt$") and verify_admin_password(PASSWORD, row.password_hash)
    assert await db_session.scalar(select(User.id).where(User.username == "applicant")) is None
    assert (await client.post("/login", data={"username": "applicant", "password": PASSWORD})).status_code == 401
    assert PASSWORD not in (await client.get(response.headers["location"])).text
    logs = list(await db_session.scalars(select(AuditLog)))
    assert all(PASSWORD not in (log.label + log.changes) and row.password_hash not in (log.label + log.changes) for log in logs)


@pytest.mark.parametrize("extras", [{"username": "x"}, {"username": "<script>"}, {"password": "short"}, {"password_confirmation": "mismatch"}, {"password": "é" * 600, "password_confirmation": "é" * 600}])
async def test_invalid_applications_are_not_saved(client, db_session, extras):
    assert (await submit(client, **extras)).status_code == 422
    assert await db_session.scalar(select(func.count()).select_from(RegistrationRequest)) == 0


async def test_duplicates_show_unavailable_without_replacing_password(client, db_session):
    first = await submit(client)
    row = await db_session.scalar(select(RegistrationRequest))
    digest = row.password_hash
    second = await submit(client, password="another-password-12345", password_confirmation="another-password-12345")
    existing = await submit(client, username="admin")
    assert first.status_code == 303
    assert second.status_code == existing.status_code == 409
    assert STRINGS["tr"]["registration_username_unavailable"] in second.text
    assert STRINGS["tr"]["registration_username_unavailable"] in existing.text
    assert STRINGS["tr"]["registration_received"] not in second.text
    assert STRINGS["tr"]["registration_received"] not in (await client.get("/register?received=true")).text
    await db_session.refresh(row)
    assert row.password_hash == digest
    assert await db_session.scalar(select(func.count()).select_from(RegistrationRequest)) == 1


@pytest.mark.parametrize("role", ["admin", "manager"])
async def test_staff_approval_creates_only_unverified_editor(client, db_session, role):
    assert (await submit(client)).status_code == 303
    row = await db_session.scalar(select(RegistrationRequest))
    reviewer = await staff(client, db_session, role)
    html = (await client.get("/panel/registrations")).text
    assert "applicant" in html and row.password_hash not in html
    response = await client.post(f"/panel/registrations/{row.id}", data={"action": "approve", "role": "admin"})
    assert response.status_code == 303
    user = await db_session.scalar(select(User).where(User.username == "applicant"))
    assert user.role == "editor" and user.is_active and not user.is_verified
    db_session.expunge_all()
    assert await db_session.scalar(select(RegistrationRequest.id).where(RegistrationRequest.id == row.id)) is None
    client.cookies.delete(SESSION_COOKIE, domain="test.local", path="/")
    response = await client.post("/login", data={"username": "applicant", "password": PASSWORD})
    assert response.status_code == 302
    assert (await client.get("/panel/registrations")).status_code == 403


async def test_reject_removes_request_and_credentials(client, db_session):
    await submit(client)
    row = await db_session.scalar(select(RegistrationRequest))
    await staff(client, db_session, "manager")
    assert (await client.post(f"/panel/registrations/{row.id}", data={"action": "reject"})).status_code == 303
    db_session.expunge_all()
    assert await db_session.get(RegistrationRequest, row.id) is None
    assert await db_session.scalar(select(User.id).where(User.username == "applicant")) is None
    event = await db_session.scalar(select(AuditLog).where(AuditLog.label == "Registration rejected"))
    assert event.action == "reject" and "applicant" in event.changes


async def test_editor_and_anonymous_cannot_review(client, db_session):
    await submit(client)
    row = await db_session.scalar(select(RegistrationRequest))
    assert (await client.get("/panel/registrations")).status_code == 302
    await staff(client, db_session, "editor")
    assert (await client.get("/panel/registrations")).status_code == 403
    assert (await client.post(f"/panel/registrations/{row.id}", data={"action": "approve", "current_password": PASSWORD})).status_code == 403


async def test_review_needs_csrf_but_not_password(client, db_session):
    await submit(client)
    row = await db_session.scalar(select(RegistrationRequest))
    await staff(client, db_session, "manager")
    csrf = client.headers.pop("X-CSRF-Token")
    assert (await client.post(f"/panel/registrations/{row.id}", data={"action": "approve"})).status_code == 403
    assert await db_session.scalar(select(User.id).where(User.username == "applicant")) is None
    assert (await submit(client, username="without-csrf")).status_code == 403
    client.headers["X-CSRF-Token"] = csrf
    page = await client.get("/panel/registrations")
    assert 'name="current_password"' not in page.text
    assert (await client.post(f"/panel/registrations/{row.id}", data={"action": "approve"})).status_code == 303
    assert await db_session.scalar(select(User.id).where(User.username == "applicant")) is not None
    assert await db_session.scalar(select(RegistrationRequest.id).where(RegistrationRequest.id == row.id)) is None
    event = await db_session.scalar(select(AuditLog).where(AuditLog.label == "Registration approved"))
    assert event is not None and event.action == "approve" and "applicant" in event.changes


async def test_application_quota_keeps_only_keyed_identifiers(client, db_session):
    for i in range(5):
        assert (await submit(client, username=f"request-{i}")).status_code == 303
    assert (await submit(client, username="over-quota")).status_code == 429
    attempts = list(await db_session.scalars(select(LoginAttempt)))
    assert all(len(row.client_key) == 64 and "127.0.0.1" not in row.client_key for row in attempts)


async def test_pagination(client, db_session):
    db_session.add_all(RegistrationRequest(username=f"pending-{i}", password_hash="hash", created_at=datetime.now(timezone.utc) + timedelta(seconds=i)) for i in range(21))
    await db_session.commit()
    await staff(client, db_session, "manager")
    html = (await client.get("/panel/registrations")).text
    assert 'href="?page=2"' in html and "pending-20" not in html
    assert "pending-20" in (await client.get("/panel/registrations?page=2")).text


async def test_full_queue_has_uniform_responses(client, db_session, monkeypatch):
    from app.routers import registrations
    monkeypatch.setattr(registrations, "MAX_PENDING", 1)
    assert (await submit(client)).status_code == 303
    for username in ("new-applicant", "applicant", "admin"):
        assert (await submit(client, username=username)).status_code == 503
    assert await db_session.scalar(select(func.count()).select_from(RegistrationRequest)) == 1


async def test_approval_cannot_replace_existing_user_or_be_replayed(client, db_session):
    await submit(client)
    row = await db_session.scalar(select(RegistrationRequest))
    await staff(client, db_session, "admin")
    existing = User(username="applicant", role="manager", password_hash=hash_admin_password("existing-password"))
    db_session.add(existing)
    await db_session.commit()
    digest = existing.password_hash
    response = await client.post(f"/panel/registrations/{row.id}", data={"action": "approve", "current_password": PASSWORD})
    assert response.status_code == 303
    await db_session.refresh(existing)
    assert existing.role == "manager" and existing.password_hash == digest
    assert await db_session.get(RegistrationRequest, row.id) is not None
    assert (await client.post(f"/panel/registrations/{row.id}", data={"action": "reject", "current_password": PASSWORD})).status_code == 303
    assert (await client.post(f"/panel/registrations/{row.id}", data={"action": "approve", "current_password": PASSWORD})).status_code == 404
    assert await db_session.scalar(select(func.count()).select_from(User).where(User.username == "applicant")) == 1


@pytest.mark.parametrize("language", ["en", "es", "fr", "tr"])
async def test_complete_registration_translations(client, language):
    assert set(STRINGS[language]) == set(STRINGS["en"])
    templates.env.globals["site_language"] = language
    set_ui_language(language)
    assert STRINGS[language]["sign_in"] in (await client.get("/login")).text
    html = (await client.get("/register")).text
    assert STRINGS[language]["registration_title"] in html
    assert all(key in TRANSLATIONS[language] for key in STRINGS[language])


async def test_remote_http_password_submission_is_rejected(client, db_session):
    transport = ASGITransport(app=app, client=("198.51.100.10", 1234))
    async with AsyncClient(transport=transport, base_url="http://test") as remote:
        remote.cookies.update(client.cookies)
        remote.headers.update(client.headers)
        response = await submit(remote)
        assert response.status_code == 400
        response = await remote.post("/login", data={"username": "admin", "password": PASSWORD}, headers={"X-Forwarded-Proto": "https"})
        assert response.status_code == 400
    assert await db_session.scalar(select(func.count()).select_from(RegistrationRequest)) == 0


async def test_remote_https_application_allowed(client, db_session):
    transport = ASGITransport(app=app, client=("198.51.100.10", 1234))
    async with AsyncClient(transport=transport, base_url="https://test") as remote:
        # Obtain a same-origin HTTPS CSRF session.
        page = await remote.get("/register")
        token = re.search(r'name="csrf-token" content="([^"]+)"', page.text).group(1)
        remote.headers["X-CSRF-Token"] = token
        assert (await submit(remote)).status_code == 303


async def test_previous_backup_schema_remains_importable(db_session):
    stage = backups.new_stage()
    backups.write_archive(stage / "incoming.zip")
    with zipfile.ZipFile(stage / "incoming.zip") as archive:
        manifest = json.loads(archive.read("manifest.json"))
        data = json.loads(archive.read("data.json"))
    del data['site_settings'][0]['gallery_image_limit']
    for row in data['users']:
        del row['publisher_report_count']
    for row in data['downloads']:
        del row['gallery_images']
    del data["registration_requests"]
    del data["site_settings"][0]["image_compression_enabled"]
    del data["site_settings"][0]["image_compression_level"]
    for user in data["users"]:
        del user["profile_icon"]
    del data["site_settings"][0]["favicon_path"]
    del data["site_settings"][0]["site_timezone"]
    del data["site_settings"][0]["editor_media_quota_mb"]
    del data["site_settings"][0]["manager_media_quota_mb"]
    for user in data["users"]:
        del user["media_quota_mb"]
    manifest["schema"] = backups.schema_fingerprint(before_registrations=True)
    with zipfile.ZipFile(stage / "incoming.zip", "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("data.json", json.dumps(data))
    _, imported = backups.validate_archive(stage)
    assert imported["registration_requests"] == []
    backups.remove_stage(stage)

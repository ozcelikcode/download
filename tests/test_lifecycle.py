"""Kurulum sahipliği, doğrulama ve yıkıcı işlemlerin güvenlik sınırları."""

import asyncio
import json
import re
import time

import pytest
from sqlalchemy import func, select

from app import crud
from app.config import settings
from app.dependencies import SESSION_COOKIE, create_admin_session_token, hash_admin_password
from app.lifecycle import RequestGate, finish_pending_reset, get_lifecycle, reset_site, reset_storage_roots, single_worker_guard
from app.main import app
from app.models import AuditLog, Category, Download, MediaAsset, User
from app.schemas import DownloadCreate

PASSWORD = "a unique test password 123!"
SETUP_KEY = "isolated-test-setup-key-" * 3


@pytest.fixture(scope="module")
def password_hash():
    return hash_admin_password(PASSWORD)


async def owner(client, session, password_hash):
    account = await crud.get_site_settings(session)
    account.site_name = "Doğrulanacak Site"
    user = await session.scalar(select(User).where(User.username == "admin"))
    user.password_hash = password_hash
    await session.commit()
    client.cookies.set(SESSION_COOKIE, create_admin_session_token("admin", password_hash, user_id=user.id), domain="test.local", path="/")
    return account


async def authorize(client, action="full", password=PASSWORD):
    return await client.post("/admin/settings/maintenance/authorize", data={"action": action, "password": password})


async def confirm(client, page, name="Doğrulanacak Site"):
    nonce = re.search(r'name="nonce" value="([^"]+)"', page.text).group(1)
    return await client.post("/admin/settings/maintenance/confirm", data={
        "confirmation": name, "nonce": nonce, "irreversible": "yes",
    })


async def test_new_site_closed_until_owner_completes_setup(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "setup_token", SETUP_KEY)
    state = await get_lifecycle(db_session)
    state.installed = False
    await db_session.commit()
    for path in ("/", "/admin/login", "/sitemap.xml", "/static/uploads/icons/old.png", "/static/css/%2e%2e/uploads/old.png", "/dl/old"):
        response = await client.get(path)
        assert response.status_code == 303
        assert response.headers["location"] == "/setup"
    assert "Disallow: /" in (await client.get("/robots.txt")).text
    page = await client.get("/setup?lang=en")
    assert "Site setup" in page.text
    assert '<html lang="en">' in (await client.get("/setup")).text
    assert page.headers["cache-control"] == "no-store"
    assert SETUP_KEY not in page.text
    data = dict(setup_token=SETUP_KEY, site_name="Installed site", username="owner",
                password=PASSWORD, password_confirm=PASSWORD, language="en",
                public_url=settings.app_base_url, deployment_confirmed="yes")
    rejected = await client.post("/setup", data={**data, "setup_token": "wrong"})
    assert rejected.status_code == 403
    assert PASSWORD not in rejected.text
    rejected = await client.post("/setup", data={**data, "public_url": "https://attacker.example"})
    assert rejected.status_code == 422
    accepted = await client.post("/setup", data=data)
    assert accepted.status_code == 303
    assert accepted.headers["location"] == "/admin/login"
    assert (await client.get("/")).status_code == 200
    assert (await client.get("/setup")).headers["location"] == "/admin/login"
    db_session.expire_all()
    account = await crud.get_site_settings(db_session)
    owner_user = await db_session.scalar(select(User).where(User.username == "owner"))
    assert owner_user.password_hash.startswith("scrypt$")
    assert json.loads(account.hero_components)[1]["text"] == "Safe and Free Software"
    category = await db_session.scalar(select(Category).where(Category.is_required.is_(True)))
    assert category is not None
    assert category.name == "General"
    assert category.slug == "general"


async def test_setup_uses_selected_turkish_for_required_category(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "setup_token", SETUP_KEY)
    state = await get_lifecycle(db_session)
    state.installed = False
    await db_session.commit()

    page = await client.get("/setup?lang=tr")
    assert '<html lang="tr">' in page.text
    assert 'name="language" value="tr"' in page.text
    response = await client.post("/setup?lang=tr", data={
        "setup_token": SETUP_KEY,
        "site_name": "Türkçe Site",
        "username": "owner",
        "password": PASSWORD,
        "password_confirm": PASSWORD,
        "language": "tr",
        "public_url": settings.app_base_url,
        "deployment_confirmed": "yes",
    })
    assert response.status_code == 303
    category = await db_session.scalar(select(Category).where(Category.is_required.is_(True)))
    assert category is not None
    assert category.name == "Genel"
    account = await crud.get_site_settings(db_session)
    assert json.loads(account.hero_components)[1]["text"] == "Güvenli ve Ücretsiz Yazılımlar"


@pytest.mark.parametrize(
    ("language", "category_name", "hero_title"),
    [("es", "General", "Software seguro y gratuito"), ("fr", "Général", "Logiciels sûrs et gratuits")],
)
async def test_setup_seeds_selected_language_without_rewriting_it_later(
    client, db_session, monkeypatch, language, category_name, hero_title
):
    monkeypatch.setattr(settings, "setup_token", SETUP_KEY)
    state = await get_lifecycle(db_session)
    state.installed = False
    await db_session.commit()
    page = await client.get(f"/setup?lang={language}")
    assert page.status_code == 200
    assert f'<html lang="{language}">' in page.text
    assert f'name="language" value="{language}"' in page.text
    response = await client.post(f"/setup?lang={language}", data={
        "setup_token": SETUP_KEY, "site_name": "Test site", "username": "owner",
        "password": PASSWORD, "password_confirm": PASSWORD, "language": language,
        "public_url": settings.app_base_url, "deployment_confirmed": "yes",
    })
    assert response.status_code == 303
    category = await db_session.scalar(select(Category).where(Category.is_required.is_(True)))
    assert category is not None
    assert category.name == category_name
    account = await crud.get_site_settings(db_session)
    assert account.site_language == language
    assert account.content_language == language
    assert json.loads(account.hero_components)[1]["text"] == hero_title
    await crud.update_site_language(db_session, "en")
    assert category.name == category_name
    assert json.loads(account.hero_components)[1]["text"] == hero_title
    db_session.expunge(category)
    owner_user = await db_session.scalar(select(User).where(User.username == "owner"))
    fresh = await reset_site(db_session, "full", preserve_user_id=owner_user.id)
    assert fresh.site_language == "en"
    assert fresh.content_language == language
    assert json.loads(fresh.hero_components)[1]["text"] == hero_title
    restored_category = await db_session.scalar(select(Category).where(Category.is_required.is_(True)))
    assert restored_category is not None
    assert restored_category.name == category_name


async def test_setup_key_missing_and_csrf_are_closed(client, db_session, monkeypatch):
    state = await get_lifecycle(db_session)
    state.installed = False
    await db_session.commit()
    monkeypatch.setattr(settings, "setup_token", "")
    assert (await client.post("/setup", data={})).status_code == 403
    client.headers.pop("X-CSRF-Token")
    assert (await client.post("/setup", data={"setup_token": SETUP_KEY})).status_code == 403


async def test_reset_needs_password_site_name_and_fresh_confirmation(admin_client, db_session, password_hash):
    await owner(admin_client, db_session, password_hash)
    assert (await authorize(admin_client, password="wrong")).status_code == 403
    page = await authorize(admin_client)
    assert page.status_code == 200
    assert PASSWORD not in page.text
    assert (await confirm(admin_client, page, "wrong site")).status_code == 403
    assert (await confirm(admin_client, page)).status_code == 403
    assert (await get_lifecycle(db_session)).installed


async def test_reset_confirmation_expires(admin_client, db_session, password_hash, monkeypatch):
    await owner(admin_client, db_session, password_hash)
    page = await authorize(admin_client)
    now = time.time()
    monkeypatch.setattr("app.routers.setup.time.time", lambda: now + 301)
    assert (await confirm(admin_client, page)).status_code == 403


async def test_oversized_requests_rejected_before_form_parsing(client):
    assert (await client.post("/admin/login", content=b"x" * 17000)).status_code == 413

    async def chunks():
        yield b"username=ignored&password="
        yield b"x" * 17000

    response = await client.post("/admin/login", content=chunks(), headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert response.status_code == 413


@pytest.mark.parametrize("path", ["/setup", "/admin/settings/maintenance/confirm"])
async def test_slow_anonymous_confirmation_cannot_lock_public_site(client, path):
    started, release = asyncio.Event(), asyncio.Event()

    async def slow_body():
        started.set()
        await release.wait()
        yield b"invalid=form"

    pending = asyncio.create_task(client.post(path, content=slow_body(), headers={"Content-Type": "application/x-www-form-urlencoded"}))
    await started.wait()
    try:
        response = await asyncio.wait_for(client.get("/"), timeout=1)
        assert response.status_code == 200
    finally:
        release.set()
        await pending


async def test_public_admin_controls_reject_stale_session(admin_client, db_session, password_hash):
    account = await owner(admin_client, db_session, password_hash)
    download = await crud.create_download(db_session, DownloadCreate(title="Public test", external_url="https://example.com/file"))
    assert f'/admin/downloads/{download.id}/edit' in (await admin_client.get(f"/download/{download.slug}")).text
    account.session_generation = "revoked"
    await db_session.commit()
    assert f'/admin/downloads/{download.id}/edit' not in (await admin_client.get(f"/download/{download.slug}")).text


async def test_reset_has_rate_limit_and_csrf(admin_client, db_session, password_hash):
    await owner(admin_client, db_session, password_hash)
    for _ in range(5):
        assert (await authorize(admin_client, password="wrong")).status_code == 403
    assert (await authorize(admin_client)).status_code == 429
    admin_client.headers.pop("X-CSRF-Token")
    assert (await authorize(admin_client)).status_code == 403


@pytest.mark.parametrize("action", ["settings", "full", "uninstall"])
async def test_reset_scopes_preserve_only_expected_data(
    action, admin_client, db_session, password_hash, monkeypatch, tmp_path
):
    monkeypatch.setattr(settings, "setup_token", SETUP_KEY)
    account = await owner(admin_client, db_session, password_hash)
    account.seo_home_title = "Old SEO"
    await db_session.commit()
    await crud.create_download(db_session, DownloadCreate(title="Old download", external_url="https://example.com/file"))
    settings.upload_path.joinpath("icons").mkdir()
    icon = settings.upload_path / "icons" / "old.png"
    icon.write_bytes(b"old image")
    local = settings.download_path / "old.zip"
    local.write_bytes(b"old file")
    outside = tmp_path / "untouched.txt"
    outside.write_text("keep")
    (settings.upload_path / "outside").symlink_to(outside)
    old_token = admin_client.cookies.get(SESSION_COOKIE)
    page = await authorize(admin_client, action)
    assert page.status_code == 200
    result = await confirm(admin_client, page)
    assert result.status_code == 303
    db_session.expire_all()
    fresh = await crud.get_site_settings(db_session)
    assert fresh.seo_home_title is None
    assert outside.read_text() == "keep"
    assert icon.exists() == (action == "settings")
    assert local.exists() == (action == "settings")
    assert (await db_session.scalar(select(func.count()).select_from(Download))) == (1 if action == "settings" else 0)
    assert (await get_lifecycle(db_session)).installed == (action != "uninstall")
    assert bool(await db_session.scalar(select(func.count()).select_from(User).where(User.role == "admin", User.is_active.is_(True)))) == (action != "uninstall")
    assert fresh.session_generation
    expected_hero = "Safe and Free Software" if action == "uninstall" else "Güvenli ve Ücretsiz Yazılımlar"
    assert json.loads(fresh.hero_components)[1]["text"] == expected_hero
    if action == "full":
        category = await db_session.scalar(select(Category).where(Category.is_required.is_(True)))
        assert category is not None
        assert category.name == "Genel"
    elif action == "uninstall":
        assert await db_session.scalar(select(func.count()).select_from(Category)) == 0
    admin_client.cookies.set(SESSION_COOKIE, old_token, domain="test.local", path="/")
    assert (await admin_client.get("/admin")).status_code in {302, 303}
    assert "/admin/downloads/" not in (await admin_client.get("/")).text
    if action != "settings":
        assert await db_session.scalar(select(func.count()).select_from(AuditLog)) == 0
        assert await db_session.scalar(select(func.count()).select_from(MediaAsset)) == 0


async def test_uninstall_requires_reinstallation_key(admin_client, db_session, password_hash, monkeypatch):
    await owner(admin_client, db_session, password_hash)
    monkeypatch.setattr(settings, "setup_token", "")
    assert (await authorize(admin_client, "uninstall")).status_code == 422


async def test_interrupted_cleanup_blocks_access_and_can_resume(admin_client, db_session, password_hash, monkeypatch):
    from app import lifecycle
    await owner(admin_client, db_session, password_hash)
    settings.upload_path.joinpath("old.png").write_bytes(b"old")
    original = lifecycle.purge_storage

    def fail(roots):
        raise PermissionError("test cleanup failure")

    monkeypatch.setattr(lifecycle, "purge_storage", fail)
    result = await confirm(admin_client, await authorize(admin_client))
    assert result.status_code == 503
    assert (await admin_client.get("/")).status_code == 503
    db_session.expire_all()
    assert (await get_lifecycle(db_session)).pending_reset == "full"
    monkeypatch.setattr(lifecycle, "purge_storage", original)
    await finish_pending_reset(db_session)
    assert (await admin_client.get("/")).status_code == 200
    assert not (settings.upload_path / "old.png").exists()
    category = await db_session.scalar(select(Category).where(Category.is_required.is_(True)))
    assert category is not None
    assert category.name == "Genel"


def test_reset_rejects_broad_overlapping_and_symlink_roots(monkeypatch, tmp_path):
    from pathlib import Path

    safe = tmp_path / "safe"
    safe.mkdir()
    for path in (str(tmp_path.parent), str(settings.download_path), str(settings.download_path / "nested"), str(Path.cwd() / "tests"), str(Path.cwd() / ".venv/lib"), str(Path.home() / "Downloads"), "/usr/local"):
        monkeypatch.setattr(settings, "upload_dir", path)
        with pytest.raises(ValueError):
            reset_storage_roots()
    symlink = tmp_path / "link"
    symlink.symlink_to(safe, target_is_directory=True)
    monkeypatch.setattr(settings, "upload_dir", str(symlink))
    with pytest.raises(ValueError):
        reset_storage_roots()


async def test_reset_waits_for_active_requests_and_blocks_new_ones():
    gate = RequestGate()
    events = []
    release = asyncio.Event()

    async def existing_request():
        async with gate.enter(False):
            events.append("reading")
            await release.wait()
            events.append("read_done")

    async def reset():
        async with gate.enter(True):
            events.append("reset")

    reader = asyncio.create_task(existing_request())
    await asyncio.sleep(0)
    writer = asyncio.create_task(reset())
    await asyncio.sleep(0)
    assert events == ["reading"]
    release.set()
    await asyncio.gather(reader, writer)
    assert events == ["reading", "read_done", "reset"]


def test_prepare_never_overwrites_existing_configuration(tmp_path):
    from app.manage import prepare
    config = tmp_path / ".env"
    prepare(config, "http://127.0.0.1:8000")
    original = config.read_bytes()
    assert config.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        prepare(config, "https://example.com")
    assert config.read_bytes() == original


def test_only_one_process_can_own_database(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "database_url", f"sqlite+aiosqlite:///{tmp_path / 'locked.db'}")
    with single_worker_guard():
        with pytest.raises(RuntimeError):
            with single_worker_guard():
                raise AssertionError("Second owner must not start")
    with single_worker_guard():
        pass

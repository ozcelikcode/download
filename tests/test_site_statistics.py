"""Site-wide analytics role boundaries and server-side hero omission."""

import json

import pytest
from sqlalchemy import select

from app.dependencies import SESSION_COOKIE, create_admin_session_token
from app.models import Download, SiteSettings, User


@pytest.mark.parametrize('role,status', [('admin', 200), ('manager', 403), ('editor', 403)])
async def test_statistics_access(client, db_session, role, status):
    admin = await db_session.scalar(select(User).where(User.username == 'admin'))
    user = admin if role == 'admin' else User(username=f'stats-{role}', role=role, password_hash=admin.password_hash)
    db_session.add(user)
    db_session.add(Download(title='Statistics application', slug='statistics-application', download_count=123))
    await db_session.commit()
    client.cookies.set(SESSION_COOKIE, create_admin_session_token(
        user.username, user.password_hash, user_id=user.id), domain='test.local', path='/')
    page = await client.get('/panel/statistics')
    assert page.status_code == status
    canonical = await client.get('/panel/site-information')
    assert canonical.status_code == status
    if status == 200:
        assert 'Statistics application' in page.text and '123' in page.text
        assert 'FastAPI' in canonical.text and 'SQLite' in canonical.text
        assert user.password_hash not in canonical.text
    else:
        assert 'href="/panel/site-information"' not in (await client.get('/panel')).text


@pytest.mark.parametrize('language', ['en', 'es', 'fr', 'tr'])
async def test_site_information_translations(admin_client, language):
    from app.i18n import set_ui_language
    from app.locales.image_policy import STRINGS

    set_ui_language(language)
    page = await admin_client.get('/panel/site-information')
    assert page.status_code == 200
    for key in ['site_statistics', 'site_runtime', 'site_configuration', 'site_inventory', 'site_editor_quota', 'site_manager_quota']:
        assert STRINGS[language][key] in page.text


async def test_disabled_hero_is_absent_from_html(client, db_session):
    policy = await db_session.scalar(select(SiteSettings))
    policy.hero_enabled = False
    policy.hero_components = json.dumps([{'type': 'title', 'text': 'Hidden hero sentinel'}])
    await db_session.commit()
    page = await client.get('/')
    assert page.status_code == 200
    assert 'Hidden hero sentinel' not in page.text and 'id="hero"' not in page.text


async def test_statistics_long_titles_remain_inside_bounded_cards(admin_client, db_session):
    title = 'Long application title ' * 20
    db_session.add(Download(title=title, slug='long-statistics-title', download_count=10))
    await db_session.commit()
    page = await admin_client.get('/panel/site-information')
    assert page.status_code == 200
    assert 'class="min-w-0 flex-1 truncate hover:underline"' in page.text
    assert f'title="{title}"' in page.text
    assert 'p-5 bg-white dark:bg-slate-900 min-w-0' in page.text

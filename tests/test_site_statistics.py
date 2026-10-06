"""Site-wide analytics role boundaries and server-side hero omission."""

import json

import pytest
from sqlalchemy import select

from app.dependencies import SESSION_COOKIE, create_admin_session_token
from app.models import Download, SiteSettings, User


@pytest.mark.parametrize('role,status', [('admin', 200), ('manager', 200), ('editor', 403)])
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
    if status == 200:
        assert 'Statistics application' in page.text and '123' in page.text


async def test_disabled_hero_is_absent_from_html(client, db_session):
    policy = await db_session.scalar(select(SiteSettings))
    policy.hero_enabled = False
    policy.hero_components = json.dumps([{'type': 'title', 'text': 'Hidden hero sentinel'}])
    await db_session.commit()
    page = await client.get('/')
    assert page.status_code == 200
    assert 'Hidden hero sentinel' not in page.text and 'id="hero"' not in page.text

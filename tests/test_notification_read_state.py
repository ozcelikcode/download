"""Consistent read state without approving or removing pending work."""

import json
import re

import pytest
from sqlalchemy import func, select

from app.dependencies import SESSION_COOKIE, create_admin_session_token
from app.i18n import TRANSLATIONS
from app.models import EditorMessage, RegistrationRequest, User


async def test_initial_navbar_badge_and_destination_read_state(admin_client, db_session):
    db_session.add(RegistrationRequest(username="waiting", password_hash="test-only"))
    await db_session.commit()
    page = await admin_client.get('/panel', headers={'Accept': 'text/html'})
    assert page.status_code == 200
    seed = json.loads(re.search(r'id="panel-notice-data">(.*?)</script>', page.text, re.S).group(1))
    assert seed['unread'] == 1 and seed['unread_counters']['registrations'] == 1
    assert 'dashboard-update-card' in page.text and 'dashboard-updates-title' in page.text
    assert 'Tümünü okundu işaretle' in page.text
    page = await admin_client.get('/panel/registrations', headers={'Accept': 'text/html'})
    assert page.status_code == 200 and 'Görüldü' in page.text
    data = (await admin_client.get('/panel/notifications')).json()
    assert data['unread'] == 0 and data['unread_counters']['registrations'] == 0
    assert data['counters']['registrations'] == 1
    assert await db_session.scalar(select(func.count()).select_from(RegistrationRequest)) == 1


async def test_mark_all_leaves_pending_work_and_new_events_unread(admin_client, db_session):
    db_session.add(RegistrationRequest(username='first', password_hash='test-only'))
    await db_session.commit()
    response = await admin_client.post('/panel/notifications/read-all', headers={'Accept': 'application/json'})
    assert response.status_code == 200 and response.json()['unread'] == 0
    assert response.json()['items'][0]['unread'] == 0
    db_session.add(RegistrationRequest(username='second', password_hash='test-only'))
    await db_session.commit()
    data = (await admin_client.get('/panel/notifications')).json()
    assert data['unread'] == 1 and data['counters']['registrations'] == 2


async def test_mark_all_requires_authentication_and_csrf(client, admin_client):
    assert (await client.post('/panel/notifications/read-all')).status_code == 302
    admin_client.headers.pop('X-CSRF-Token')
    assert (await admin_client.post('/panel/notifications/read-all')).status_code == 403


async def test_native_mark_all_form(admin_client, db_session):
    db_session.add(RegistrationRequest(username='native', password_hash='test-only'))
    await db_session.commit()
    page = await admin_client.get('/panel', headers={'Accept': 'text/html'})
    token = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
    admin_client.headers.pop('X-CSRF-Token')
    response = await admin_client.post('/panel/notifications/read-all', data={'csrf_token': token})
    assert response.status_code == 303 and response.headers['location'] == '/panel'
    assert (await admin_client.get('/panel/notifications')).json()['unread'] == 0


async def test_read_state_cannot_cross_account_identity(admin_client, db_session):
    admin = await db_session.scalar(select(User).where(User.username == 'admin'))
    manager = User(username='another-manager', password_hash=admin.password_hash, role='manager')
    db_session.add_all([manager, RegistrationRequest(username='shared-work', password_hash='test-only')])
    await db_session.commit()
    await admin_client.post('/panel/notifications/read-all')
    admin_client.cookies.set(SESSION_COOKIE, create_admin_session_token(
        manager.username, manager.password_hash, user_id=manager.id,
    ), domain='test.local', path='/')
    assert (await admin_client.get('/panel/notifications')).json()['unread'] == 1


async def test_editor_mark_all_is_role_scoped(client, db_session):
    from datetime import datetime, timezone

    admin = await db_session.scalar(select(User).where(User.username == 'admin'))
    editor = User(username='reader-editor', password_hash=admin.password_hash, role='editor')
    db_session.add(editor)
    await db_session.flush()
    db_session.add_all([
        RegistrationRequest(username='staff-only-request', password_hash='test-only'),
        EditorMessage(sender_id=editor.id, subject='Private subject', body='Private text',
                      response='Private answer', responded_at=datetime.now(timezone.utc)),
    ])
    await db_session.commit()
    client.cookies.set(SESSION_COOKIE, create_admin_session_token(
        editor.username, editor.password_hash, user_id=editor.id,
    ), domain='test.local', path='/')
    result = await client.post('/panel/notifications/read-all', headers={'Accept': 'application/json'})
    assert result.status_code == 200 and result.json()['unread'] == 0
    assert set(result.json()['counters']) == {'contact', 'content'}
    assert 'Private' not in result.text and 'staff-only' not in result.text
    assert result.json()['items'][0]['unread'] == 0


@pytest.mark.parametrize('language', ['en', 'es', 'fr', 'tr'])
def test_read_state_translations_are_complete(language):
    for key in ('notice_unread', 'notice_read', 'notice_new', 'notice_read_all',
                'notice_read_all_done', 'notice_read_failed', 'notice_overview_title', 'notice_overview_help'):
        assert TRANSLATIONS[language][key]

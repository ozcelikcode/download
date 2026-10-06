"""Detail-page layout, anonymous issue reporting, and publication boundaries."""

import json
import re

import pytest
from sqlalchemy import func, select

from app.dependencies import SESSION_COOKIE, create_admin_session_token
from app.models import AuditLog, Download, User
from app.i18n import TRANSLATIONS
from app.locales.download_detail import STRINGS


async def item(session, **values):
    download = Download(title="Layout application", slug="layout-application", description="<p>Readable description</p>",
                        short_description="Short summary", **values)
    session.add(download)
    await session.commit()
    return download


async def test_detail_layout_keeps_header_then_description_and_right_actions(client, db_session):
    download = await item(db_session)
    page = await client.get(f"/download/{download.slug}")
    assert page.status_code == 200
    assert page.text.index('<h1') < page.text.index('download-detail-layout')
    assert page.text.index('detail-main') < page.text.index('detail-side')
    side = page.text.split('<aside class="detail-side"', 1)[1].split('</aside>', 1)[0]
    header = page.text.split('detail-identity', 1)[1].split('download-detail-layout', 1)[0]
    assert 'id="download-btn-main"' in header and f'action="/download/{download.slug}/report"' in side
    assert 'id="application-description"' in page.text and 'aria-controls="application-description"' in page.text
    assert 'Short summary' not in header and 'Readable description' in page.text
    assert 'data-detail-tab="detail-description-panel"' in page.text and 'data-detail-tab="detail-history-panel"' in page.text
    assert 'id="sidebar-search"' not in page.text


async def test_report_reaches_staff_without_link_check_claim_or_personal_data(client, admin_client, db_session):
    download = await item(db_session)
    page = await client.get(f"/download/{download.slug}")
    token = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
    client.headers.pop('X-CSRF-Token')
    for _ in range(2):
        response = await client.post(f"/download/{download.slug}/report", data={
            "reason": "broken", "csrf_token": token, "email": "not-stored@example.com",
        })
        assert response.status_code == 303
    assert await db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.entity == "visitor_reports")) == 1
    event = await db_session.scalar(select(AuditLog).where(AuditLog.entity == "visitor_reports"))
    assert event.actor == "anonymous" and json.loads(event.changes) == {"reason": [None, "detail_report_broken"]}
    assert 'not-stored' not in event.changes and 'http_status' not in event.changes
    assert TRANSLATIONS['tr']['detail_report_received'] in (await client.get(f"/download/{download.slug}")).text
    assert TRANSLATIONS['tr']['detail_report_received'] not in (await client.get(f"/download/{download.slug}")).text
    page = await admin_client.get('/panel/links/reports')
    assert page.status_code == 200 and download.title in page.text
    assert TRANSLATIONS['tr']['detail_report_broken'] in page.text
    feed = (await admin_client.get('/panel/notifications')).json()
    assert feed['counters']['reports'] == 1
    opened = await admin_client.post('/panel/notifications/open', data={'kind': 'reports'})
    assert opened.status_code == 303 and opened.headers['location'] == '/panel/links/reports'
    assert (await admin_client.get('/panel/notifications')).json()['unread_counters']['reports'] == 0


@pytest.mark.parametrize('values', [{'is_hidden': True}, {'is_draft': True}, {'is_active': False}])
async def test_reports_do_not_expose_unpublished_records(client, db_session, values):
    download = await item(db_session, **values)
    assert (await client.post(f"/download/{download.slug}/report", data={'reason': 'broken'})).status_code == 404
    assert await db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.entity == 'visitor_reports')) == 0


async def test_report_requires_csrf_valid_reason_and_throttles(client, db_session):
    download = await item(db_session)
    assert (await client.post(f'/download/{download.slug}/report', data={'reason': 'anything'})).status_code == 400
    token = client.headers.pop('X-CSRF-Token')
    assert (await client.post(f'/download/{download.slug}/report', data={'reason': 'broken'})).status_code == 403
    client.headers['X-CSRF-Token'] = token
    for _ in range(5):
        assert (await client.post(f'/download/{download.slug}/report', data={'reason': 'broken'})).status_code == 303
    response = await client.post(f'/download/{download.slug}/report', data={'reason': 'unsafe'})
    assert response.status_code == 429 and 'Retry-After' in response.headers


def test_detail_translation_keys_are_complete():
    for language in ('en', 'es', 'fr', 'tr'):
        assert set(STRINGS[language]) == set(STRINGS['en'])
        assert all(TRANSLATIONS[language][key] == value for key, value in STRINGS[language].items())


async def test_draft_preview_preserves_description_but_disables_download_and_report(admin_client, db_session):
    download = await item(db_session, is_draft=True)
    response = await admin_client.get(f"/panel/downloads/{download.id}/preview")
    assert response.status_code == 200
    assert 'Readable description' in response.text
    assert 'disabled aria-disabled="true"' in response.text
    assert f'action="/download/{download.slug}/report"' not in response.text
    assert 'detail-description is-collapsed' not in response.text


@pytest.mark.parametrize('role,status', [('manager', 200), ('editor', 403)])
async def test_visitor_report_list_has_staff_role_boundary(client, db_session, role, status):
    admin = await db_session.scalar(select(User).where(User.username == 'admin'))
    user = User(username=f'report-{role}', role=role, password_hash=admin.password_hash)
    db_session.add(user)
    await db_session.commit()
    client.cookies.set(
        SESSION_COOKIE, create_admin_session_token(user.username, user.password_hash, user_id=user.id),
        domain='test.local', path='/',
    )
    assert (await client.get('/panel/links/reports')).status_code == status
    if role == 'editor':
        data = (await client.get('/panel/notifications')).json()
        assert 'reports' not in data['counters']
        assert (await client.post('/panel/notifications/open', data={'kind': 'reports'})).status_code == 404

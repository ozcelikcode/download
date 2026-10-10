"""Application form, semantic rendering and private editor-note boundaries."""


import pytest
from sqlalchemy import select

from app.dependencies import SESSION_COOKIE, create_admin_session_token
from app.models import AuditLog, Download, Tag, User
from app.content_security import sanitize_rich_text


def sign_in(client, user):
    client.cookies.set(SESSION_COOKIE, create_admin_session_token(user.username, user.password_hash, user_id=user.id), domain='test.local', path='/')


async def test_inline_tags_select_existing_owned_names_and_preserve_other_owners(admin_client, client, db_session):
    admin = await db_session.scalar(select(User).where(User.username == 'admin'))
    editor = User(username='tag-owner', role='editor', password_hash=admin.password_hash)
    db_session.add(editor)
    await db_session.commit()
    first = await admin_client.post('/panel/tags/inline', data={'name': '#tools'})
    second = await admin_client.post('/panel/tags/inline', data={'name': 'tools'})
    assert first.status_code == second.status_code == 200
    assert first.json()['id'] == second.json()['id']
    sign_in(client, editor)
    own = await client.post('/panel/tags/inline', data={'name': 'tools'})
    assert own.status_code == 200 and own.json()['id'] != first.json()['id']
    assert (await db_session.get(Tag, own.json()['id'])).owner_id == editor.id
    assert (await client.post('/panel/tags/inline', data={'name': '  # '})).status_code == 422
    page = await client.get('/panel/downloads/new')
    assert page.status_code == 200 and 'id="tag-add-toggle"' in page.text
    assert 'class="tag-remove ml-2"' in page.text


@pytest.mark.parametrize('role', ['admin', 'manager'])
async def test_staff_notes_use_existing_editor_inbox_and_are_escaped(client, db_session, role):
    admin = await db_session.scalar(select(User).where(User.username == 'admin'))
    sender = admin if role == 'admin' else User(username='note-manager', role=role, password_hash=admin.password_hash)
    editor = User(username='note-editor', role='editor', password_hash=admin.password_hash)
    other = User(username='other-editor', role='editor', password_hash=admin.password_hash)
    db_session.add_all([sender, editor, other])
    await db_session.flush()
    item = Download(title='Editor application', slug='editor-application', owner_id=editor.id, external_url='https://example.com')
    db_session.add(item)
    await db_session.commit()
    sign_in(client, sender)
    page = await client.get('/download/editor-application')
    assert 'id="editor-note-open"' in page.text
    response = await client.post(f'/panel/content-reports/{item.id}/note', data={'note': '<script>warning</script>'})
    assert response.status_code == 303
    sign_in(client, editor)
    notices = (await client.get('/panel/notifications')).json()
    assert notices['counters']['publisher_reports'] == 1
    inbox = await client.get('/panel/content-reports')
    assert '&lt;script&gt;warning&lt;/script&gt;' in inbox.text
    assert '<script>warning</script>' not in inbox.text
    sign_in(client, other)
    assert 'warning' not in (await client.get('/panel/content-reports')).text


@pytest.mark.parametrize('role', ['admin', 'manager'])
async def test_staff_owned_content_has_no_publisher_notification(admin_client, client, db_session, role):
    admin = await db_session.scalar(select(User).where(User.username == 'admin'))
    owner = admin if role == 'admin' else User(username='staff-owner', role=role, password_hash=admin.password_hash)
    db_session.add(owner)
    await db_session.flush()
    item = Download(title='Staff app', slug='staff-app', owner_id=owner.id, external_url='https://example.com')
    db_session.add(item)
    await db_session.commit()
    page = await admin_client.get('/download/staff-app')
    assert 'name="target" value="publisher"' not in page.text
    assert 'id="editor-note-open"' not in page.text
    assert (await client.post('/download/staff-app/report', data={'target': 'publisher', 'reason': 'incorrect'})).status_code == 404
    assert (await admin_client.post(f'/panel/content-reports/{item.id}/note', data={'note': 'No staff-to-staff notes'})).status_code == 404


async def test_editor_cannot_send_staff_notes_and_csrf_is_required(admin_client, client, db_session):
    admin = await db_session.scalar(select(User).where(User.username == 'admin'))
    editor = User(username='restricted-note-editor', role='editor', password_hash=admin.password_hash)
    db_session.add(editor)
    await db_session.flush()
    item = Download(title='Note target', slug='note-target', owner_id=editor.id)
    db_session.add(item)
    await db_session.commit()
    sign_in(client, editor)
    assert (await client.post(f'/panel/content-reports/{item.id}/note', data={'note': 'Not allowed'})).status_code == 403
    admin_client.headers.pop('X-CSRF-Token')
    assert (await admin_client.post(f'/panel/content-reports/{item.id}/note', data={'note': 'Not allowed'})).status_code == 403
    assert await db_session.scalar(select(AuditLog.id).where(AuditLog.entity == 'publisher_reports')) is None


def test_quill_bullet_markers_survive_without_unsafe_attributes():
    clean = sanitize_rich_text('<ol><li data-list="bullet" onclick="bad()">Bullet</li><li data-list="evil">Invalid</li></ol>')
    assert 'data-list="bullet"' in clean
    assert 'onclick' not in clean and 'data-list="evil"' not in clean

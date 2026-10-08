"""Editorial permission and visible-text review policy regressions."""

import pytest
from sqlalchemy import select

from app.dependencies import SESSION_COOKIE, create_admin_session_token
from app.models import Download, User
from app.moderation import requires_review, visible_text


@pytest.mark.parametrize('value', ['siktir', 'SİKTİR', 's.i.k.t.i.r', 'fuck', 'putain', 'gilipollas', 'gerizekalı'])
def test_flagged_language(value):
    assert requires_review(value)


def test_visible_text_not_markup_and_no_substring_false_positive():
    assert visible_text('<p>Hello&nbsp;world</p><script>hidden</script>') == 'Hello world'
    assert not requires_review('Pictures from Scunthorpe and classical music.')


async def editor_login(client, session):
    admin = await session.scalar(select(User).where(User.username == 'admin'))
    editor = User(username='screening-editor', role='editor', password_hash=admin.password_hash, is_verified=True)
    session.add(editor)
    await session.commit()
    client.cookies.set(SESSION_COOKIE, create_admin_session_token(editor.username, editor.password_hash, user_id=editor.id), domain='test.local', path='/')
    return editor


async def test_short_new_editor_content_is_rejected(client, db_session):
    await editor_login(client, db_session)
    response = await client.post('/panel/downloads/new', data={'title': 'Too short', 'file_type': 'external', 'external_url': 'https://example.com', 'description': '<p>Short</p>' * 10, 'submission_intent': 'publish'})
    assert response.status_code == 422
    assert await db_session.scalar(select(Download.id).where(Download.title == 'Too short')) is None


@pytest.mark.parametrize('active', ['true', 'false'])
async def test_verified_flagged_editor_always_needs_review(client, db_session, active):
    await editor_login(client, db_session)
    response = await client.post('/panel/downloads/new', data={'title': 'Review required', 'file_type': 'external', 'external_url': 'https://example.com', 'description': 'Useful application documentation. ' * 10 + ' fuck', 'is_active': active, 'submission_intent': 'publish'})
    assert response.status_code == 302
    item = await db_session.scalar(select(Download).where(Download.title == 'Review required'))
    assert item.publication_pending and not item.is_active


async def test_editor_cannot_feature_or_unfeature(client, db_session):
    editor = await editor_login(client, db_session)
    item = Download(title='Staff featured', slug='staff-featured', owner_id=editor.id, is_featured=True)
    db_session.add(item)
    await db_session.commit()
    for action in ['feature', 'unfeature']:
        assert (await client.post('/panel/downloads/bulk', data={'action': action, 'download_ids': str(item.id)})).status_code == 403
    response = await client.post('/panel/downloads/new', data={'title': 'Forged feature', 'description': 'Useful application documentation. ' * 10, 'file_type': 'external', 'external_url': 'https://example.com', 'is_featured': 'true', 'submission_intent': 'publish'})
    assert response.status_code == 403
    page = await client.get(f'/panel/downloads/{item.id}/edit')
    assert 'name="is_featured"' not in page.text

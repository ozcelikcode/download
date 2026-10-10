"""Editorial permissions, visible text length and submission policy regressions."""

import pytest
from sqlalchemy import select

from app.dependencies import SESSION_COOKIE, create_admin_session_token
from app.models import Download, SiteSettings, User
from app.editorial_text import visible_text


def test_visible_text_not_markup():
    assert visible_text('<p>Hello&nbsp;world</p><script>hidden</script>') == 'Hello world'


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


@pytest.mark.parametrize('policy,verified,published', [('everyone',False,True), ('everyone',True,True), ('verified_only',False,False), ('verified_only',True,True)])
async def test_editor_submission_preference(client, db_session, policy, verified, published):
    editor = await editor_login(client, db_session)
    editor.is_verified = verified
    settings = await db_session.scalar(select(SiteSettings))
    settings.editor_publication_policy = policy
    await db_session.commit()
    response = await client.post('/panel/downloads/new', data={'title': 'Policy submission', 'file_type': 'external', 'external_url': 'https://example.com', 'description': 'Useful application documentation. ' * 10, 'is_active': 'true', 'submission_intent': 'publish'})
    assert response.status_code == 302
    item = await db_session.scalar(select(Download).where(Download.title == 'Policy submission'))
    assert item.publication_pending == (not published) and item.is_active == published


async def test_only_admin_can_change_submission_preference(admin_client, client, db_session):
    assert (await admin_client.post('/panel/users/publication-policy', data={'policy':'everyone'})).status_code == 303
    assert (await db_session.scalar(select(SiteSettings))).editor_publication_policy == 'everyone'
    assert (await admin_client.post('/panel/users/publication-policy', data={'policy':'invalid'})).status_code == 422
    actor = await editor_login(client, db_session)
    for role in ['manager', 'editor']:
        actor.role = role
        await db_session.commit()
        assert (await client.post('/panel/users/publication-policy', data={'policy':'verified_only'})).status_code == 403
        assert 'action="/panel/users/publication-policy"' not in (await client.get('/panel/users?section=publication')).text
    html = (await admin_client.get('/panel/users?section=publication')).text
    assert 'Herkes' in html and 'Sadece tikli' in html


async def test_policy_change_preserves_publications_then_reviews_new_edits(client, admin_client, db_session):
    actor = await editor_login(client, db_session)
    actor.is_verified = False
    await db_session.commit()
    assert (await admin_client.post('/panel/users/publication-policy', data={'policy':'everyone'})).status_code == 303
    data = {'title':'Policy transition', 'description':'Useful application documentation. ' * 10, 'file_type':'external', 'external_url':'https://example.com', 'is_active':'true', 'submission_intent':'publish'}
    assert (await client.post('/panel/downloads/new', data=data)).status_code == 302
    item = await db_session.scalar(select(Download).where(Download.title == data['title']))
    assert item.is_active and not item.publication_pending
    assert (await admin_client.post('/panel/users/publication-policy', data={'policy':'verified_only'})).status_code == 303
    await db_session.refresh(item)
    assert item.is_active and not item.publication_pending
    assert (await client.post(f'/panel/downloads/{item.id}/edit', data={**data,'title':'Updated title'})).status_code == 302
    await db_session.refresh(item)
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


@pytest.mark.parametrize('verified', [False, True])
async def test_nobody_locks_all_editor_submissions(client, admin_client, db_session, verified):
    editor = await editor_login(client, db_session)
    editor.is_verified = verified
    await db_session.commit()
    assert (await admin_client.post('/panel/users/publication-policy', data={'policy': 'none'})).status_code == 303
    data = {'title': 'Blocked submission', 'file_type': 'external', 'external_url': 'https://example.com', 'description': 'Useful documentation. ' * 20, 'submission_intent': 'publish'}
    assert (await client.post('/panel/downloads/new', data=data)).status_code == 403
    assert await db_session.scalar(select(Download.id).where(Download.title == data['title'])) is None
    assert (await admin_client.post('/panel/downloads/new', data=data)).status_code == 302
    html = (await client.get('/panel/downloads/new')).text
    assert 'Editör gönderimleri kapalı' in html and '<fieldset class="contents" disabled>' in html
    editor.role = 'manager'
    await db_session.commit()
    assert (await client.post('/panel/downloads/new', data={**data, 'title': 'Manager submission'})).status_code == 302

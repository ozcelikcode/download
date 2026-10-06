"""Public publisher visibility and isolated feedback delivery."""

import json
from io import BytesIO

import pytest
from PIL import Image
from sqlalchemy import select, update

from app.dependencies import SESSION_COOKIE, create_admin_session_token
from app.models import AuditLog, Download, User


async def test_catalog_and_feedback_are_owner_scoped(client, db_session):
    admin = await db_session.scalar(select(User).where(User.username == 'admin'))
    owners = [User(username=name, role='editor', password_hash=admin.password_hash)
              for name in ('publisher-one', 'publisher-two')]
    db_session.add_all(owners)
    await db_session.flush()
    db_session.add_all([
        Download(title='Public one', slug='public-one', owner_id=owners[0].id),
        Download(title='Hidden one', slug='hidden-one', owner_id=owners[0].id, is_hidden=True),
        Download(title='Public two', slug='public-two', owner_id=owners[1].id),
    ])
    await db_session.commit()
    page = await client.get(f'/publisher/{owners[0].id}')
    assert page.status_code == 200 and 'Public one' in page.text
    assert 'Hidden one' not in page.text and 'Public two' not in page.text
    assert (await client.post('/download/public-one/report', data={
        'target': 'publisher', 'reason': 'incorrect', 'recipient_id': owners[1].id,
    })).status_code == 303
    event = await db_session.scalar(select(AuditLog).where(AuditLog.entity == 'publisher_reports'))
    assert json.loads(event.changes)['recipient_id'][1] == owners[0].id
    for index, owner in enumerate(owners):
        client.cookies.set(SESSION_COOKIE, create_admin_session_token(
            owner.username, owner.password_hash, user_id=owner.id), domain='test.local', path='/')
        inbox = await client.get('/panel/content-reports')
        assert inbox.status_code == 200
        assert ('Public one' in inbox.text) == (index == 0)
        counts = (await client.get('/panel/notifications')).json()['counters']
        assert counts['publisher_reports'] == (1 if index == 0 else 0)


@pytest.mark.parametrize('flags', [{'is_hidden': True}, {'is_draft': True}, {'is_active': False}, {'publication_pending': True}])
async def test_unpublished_publisher_has_no_public_identity(client, db_session, flags):
    admin = await db_session.scalar(select(User).where(User.username == 'admin'))
    db_session.add(Download(title='Private application', slug='private-application', owner_id=admin.id, **flags))
    await db_session.commit()
    if flags.get('publication_pending'):
        # Construct an inconsistent legacy row without the publication hook
        # normalizing it; public visibility must still reject pending content.
        await db_session.execute(update(Download).where(Download.slug == 'private-application').values(publication_pending=True))
        await db_session.commit()
    assert (await client.get(f'/publisher/{admin.id}')).status_code == 404
    assert (await client.get(f'/publisher/{admin.id}/photo')).status_code == 404


async def test_photo_visibility_follows_publication(client, admin_client, db_session):
    admin = await db_session.scalar(select(User).where(User.username == 'admin'))
    output = BytesIO()
    Image.new('RGB', (300, 400), 'gray').save(output, 'PNG')
    assert (await admin_client.post('/panel/account/photo', files={
        'photo': ('photo.png', output.getvalue(), 'image/png')})).status_code == 303
    assert (await client.get(f'/publisher/{admin.id}/photo')).status_code == 404
    download = Download(title='Photo publication', slug='photo-publication', owner_id=admin.id)
    db_session.add(download)
    await db_session.commit()
    photo = await client.get(f'/publisher/{admin.id}/photo')
    assert photo.status_code == 200 and photo.headers['content-type'] == 'image/webp'
    download.is_hidden = True
    await db_session.commit()
    assert (await client.get(f'/publisher/{admin.id}/photo')).status_code == 404

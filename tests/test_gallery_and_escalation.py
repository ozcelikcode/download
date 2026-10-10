"""Gallery security, compression, policy, backup compatibility and report thresholds."""

import io
import json
import zipfile

import pytest
from PIL import Image
from sqlalchemy import func, select

from app import backups
from app.config import settings
from app.dependencies import SESSION_COOKIE, create_admin_session_token
from app.models import AuditLog, Download, MediaAsset, SiteSettings, User


def png() -> bytes:
    buffer = io.BytesIO()
    Image.new('RGB', (1200, 800), 'blue').save(buffer, 'PNG')
    return buffer.getvalue()


async def editor(client, session) -> User:
    admin = await session.scalar(select(User).where(User.username == 'admin'))
    user = User(username='gallery-editor', password_hash=admin.password_hash, role='editor', is_verified=True)
    session.add(user)
    await session.commit()
    client.cookies.set(SESSION_COOKIE, create_admin_session_token(user.username, user.password_hash, user_id=user.id), domain='test.local', path='/')
    return user


async def test_gallery_upload_always_compresses_and_registers_ownership(client, db_session):
    user = await editor(client, db_session)
    policy = await db_session.scalar(select(SiteSettings))
    policy.image_compression_enabled = False
    await db_session.commit()
    response = await client.post('/panel/upload/gallery-image', files={'file': ('fake.txt', png(), 'text/plain')}, data={'skip_compression': 'true'})
    assert response.status_code == 200
    path = response.json()['path']
    with Image.open(settings.upload_path / path.removeprefix('/static/uploads/')) as image:
        assert image.format == 'WEBP' and not image.getexif()
    asset = await db_session.scalar(select(MediaAsset).where(MediaAsset.path == path))
    assert asset.owner_id == user.id
    response = await client.post('/panel/upload/gallery-image', files={'file': ('bad.svg', b'<svg onload="alert(1)"></svg>', 'image/svg+xml')})
    assert response.status_code == 400


@pytest.mark.parametrize('limit', [3,5,10,15,20,25])
async def test_gallery_limit_admin_only(admin_client, client, db_session, limit):
    assert (await admin_client.post('/panel/settings/gallery', data={'limit': limit})).status_code == 303
    assert (await db_session.scalar(select(SiteSettings))).gallery_image_limit == limit
    user = await editor(client, db_session)
    for role in ['editor', 'manager']:
        user.role = role
        await db_session.commit()
        assert (await client.post('/panel/settings/gallery', data={'limit': 3})).status_code == 403
    assert (await admin_client.post('/panel/settings/gallery', data={'limit': 4})).status_code == 422


async def test_gallery_deduplicates_bytes_not_names(client, db_session):
    await editor(client, db_session)
    first = await client.post('/panel/upload/gallery-image', files={'file': ('one.png', png(), 'image/png')})
    db_session.add(Download(title='Published image', slug='published-image', gallery_images=json.dumps([first.json()['path']]), owner_id=(await db_session.scalar(select(User.id).where(User.username == 'gallery-editor')))))
    await db_session.commit()
    same = await client.post('/panel/upload/gallery-image', files={'file': ('different-name.png', png(), 'image/png')})
    assert first.json()['path'] == same.json()['path']
    buffer = io.BytesIO()
    Image.new('RGB', (1200, 800), 'red').save(buffer, 'PNG')
    different = await client.post('/panel/upload/gallery-image', files={'file': ('one.png', buffer.getvalue(), 'image/png')})
    assert different.json()['path'] != first.json()['path']
    assert await db_session.scalar(select(func.count()).select_from(MediaAsset)) == 2


async def test_gallery_dedup_does_not_disclose_another_editors_assets(client, db_session):
    first_actor = await editor(client, db_session)
    first = await client.post('/panel/upload/gallery-image', files={'file': ('same.png', png(), 'image/png')})
    other = User(username='another-editor', password_hash=first_actor.password_hash, role='editor')
    db_session.add(other)
    await db_session.commit()
    client.cookies.set(SESSION_COOKIE, create_admin_session_token(other.username, other.password_hash, user_id=other.id), domain='test.local', path='/')
    second = await client.post('/panel/upload/gallery-image', files={'file': ('same.png', png(), 'image/png')})
    assert second.status_code == 200 and first.json()['path'] != second.json()['path']


async def test_shared_icon_edits_copy_instead_of_changing_other_publications(admin_client, db_session):
    first = await admin_client.post('/panel/upload/icon-image', files={'file': ('one.png', png(), 'image/png')})
    same = await admin_client.post('/panel/upload/icon-image', files={'file': ('renamed.png', png(), 'image/png')})
    assert first.json()['path'] == same.json()['path']
    path = first.json()['path']
    original = settings.upload_path / path.removeprefix('/static/uploads/')
    original_bytes = original.read_bytes()
    for index in range(2):
        db_session.add(Download(title=f'Shared illustration {index}', slug=f'shared-illustration-{index}', icon_image_path=path))
    await db_session.commit()
    buffer = io.BytesIO()
    Image.new('RGB', (100, 100), 'red').save(buffer, 'PNG')
    replaced = await admin_client.post('/panel/upload/icon-image', files={'file': ('one.png', buffer.getvalue(), 'image/png')}, data={'replace_path': path})
    assert replaced.status_code == 200 and replaced.json()['path'] != path
    assert original.read_bytes() == original_bytes


async def test_gallery_form_public_tabs_and_media_usage(admin_client, db_session):
    from app.media import media_usage
    response = await admin_client.post('/panel/upload/gallery-image', files={'file': ('screen.png', png(), 'image/png')})
    path = response.json()['path']
    response = await admin_client.post('/panel/downloads/new', data={'title': 'Gallery application', 'description': 'Useful application documentation. ' * 10, 'file_type': 'external', 'external_url': 'https://example.com', 'gallery_images': json.dumps([path]), 'submission_intent': 'publish', 'is_active': 'true'})
    assert response.status_code == 302
    item = await db_session.scalar(select(Download).where(Download.title == 'Gallery application'))
    assert json.loads(item.gallery_images) == [path]
    html = (await admin_client.get(f'/download/{item.slug}')).text
    assert 'detail-gallery-tab' in html and 'gallery-lightbox' in html and path in html
    usage = await media_usage(db_session)
    assert any(row['id'] == item.id for rows in usage.values() for row in rows)
    assert 'detail-gallery-tab' not in (await admin_client.get('/download/not-real')).text


async def test_gallery_ownership_paths_and_limits(client, db_session):
    await editor(client, db_session)
    data = {'title': 'Rejected gallery', 'description': 'Useful application documentation. ' * 10, 'file_type': 'external', 'external_url': 'https://example.com', 'submission_intent': 'publish'}
    foreign = '/static/uploads/gallery/' + 'a' * 32 + '.webp'
    db_session.add(MediaAsset(path=foreign, owner_id=1))
    await db_session.commit()
    assert (await client.post('/panel/downloads/new', data={**data, 'gallery_images': json.dumps([foreign])})).status_code == 404
    for paths in [['https://example.com/image.png'], ['/static/uploads/gallery/../../private'], [foreign] * 6]:
        assert (await client.post('/panel/downloads/new', data={**data, 'gallery_images': json.dumps(paths)})).status_code == 422


async def test_previous_gallery_backup_schema_is_strict(db_session, tmp_path):
    path = tmp_path / 'incoming.zip'
    backups.write_archive(path)
    with zipfile.ZipFile(path) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        data = json.loads(archive.read('data.json'))
    manifest['schema'] = backups.schema_fingerprint(before_gallery=True)
    del data['site_settings'][0]['gallery_image_limit']
    del data['site_settings'][0]['editor_publication_policy']
    for row in data['downloads']:
        del row['gallery_images']
    for row in data['users']:
        del row['publisher_report_count']
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('manifest.json', json.dumps(manifest))
        archive.writestr('data.json', json.dumps(data))
    _, imported = backups.validate_archive(tmp_path)
    assert imported['site_settings'][0]['gallery_image_limit'] == 5
    assert all(row['publisher_report_count'] == 0 for row in imported['users'])


async def test_previous_submission_policy_backup_defaults(db_session, tmp_path):
    path = tmp_path / 'incoming.zip'
    backups.write_archive(path)
    with zipfile.ZipFile(path) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        data = json.loads(archive.read('data.json'))
    manifest['schema'] = backups.schema_fingerprint(before_publication_policy=True)
    del data['site_settings'][0]['editor_publication_policy']
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('manifest.json', json.dumps(manifest))
        archive.writestr('data.json', json.dumps(data))
    _, imported = backups.validate_archive(tmp_path)
    assert imported['site_settings'][0]['editor_publication_policy'] == 'verified_only'


async def test_ten_new_editor_reports_create_one_staff_alert(client, admin_client, db_session, monkeypatch):
    from app.routers import visitor_reports
    async def no_rate_limit(*args):
        await args[0].commit()
        return 0
    monkeypatch.setattr(visitor_reports, 'reserve_login_attempt', no_rate_limit)
    publisher = await editor(client, db_session)
    items = [Download(title=f'Reported {index}', slug=f'reported-{index}', owner_id=publisher.id) for index in range(10)]
    db_session.add_all(items)
    await db_session.commit()
    for item in items:
        assert (await client.post(f'/download/{item.slug}/report', data={'reason': 'incorrect', 'target': 'publisher'})).status_code == 303
    assert (await client.post(f'/download/{items[0].slug}/report', data={'reason': 'incorrect', 'target': 'publisher'})).status_code == 303
    await db_session.refresh(publisher)
    assert publisher.publisher_report_count == 10
    assert await db_session.scalar(select(func.count(AuditLog.id)).where(AuditLog.entity == 'publisher_alerts')) == 1
    notices = (await admin_client.get('/panel/notifications')).json()
    assert notices['counters']['publisher_alerts'] == 1
    own = (await client.get('/panel/notifications')).json()
    assert own['counters']['publisher_reports'] == 10 and 'publisher_alerts' not in own['counters']

"""Compression policy, quality bounds, and role enforcement."""

import pytest
from PIL import Image
from sqlalchemy import select

from app.dependencies import SESSION_COOKIE, create_admin_session_token
from app.imaging import COMPRESSION_PROFILES, compress_image_file
from app.models import SiteSettings, User


async def test_admin_saves_policy_and_upload_uses_default(admin_client, db_session):
    response = await admin_client.post('/panel/settings/image-compression', data={'level': 4})
    assert response.status_code == 303
    db_session.expire_all()
    policy = await db_session.scalar(select(SiteSettings))
    assert policy.image_compression_level == 4 and not policy.image_compression_enabled
    assert (await admin_client.post('/panel/settings/image-compression', data={'level': 5})).status_code == 422
    form = await admin_client.get('/panel/downloads/new')
    assert 'id="content-image-compression" type="checkbox" >' in form.text
    assert (await admin_client.get('/panel/settings/appearance')).status_code == 200


@pytest.mark.parametrize('role', ['manager', 'editor'])
async def test_non_admin_cannot_change_policy(client, db_session, role):
    admin = await db_session.scalar(select(User).where(User.username == 'admin'))
    user = User(username=f'compression-{role}', role=role, password_hash=admin.password_hash)
    db_session.add(user)
    await db_session.commit()
    client.cookies.set(SESSION_COOKIE, create_admin_session_token(
        user.username, user.password_hash, user_id=user.id), domain='test.local', path='/')
    assert (await client.post('/panel/settings/image-compression', data={'level': 4})).status_code == 403


@pytest.mark.parametrize('level', range(5))
def test_levels_preserve_alpha_and_bound_dimensions(tmp_path, level):
    path = tmp_path / 'sample.png'
    Image.new('RGBA', (4200, 12), (40, 80, 100, 90)).save(path)
    compress_image_file(path, level=level)
    with Image.open(path) as result:
        assert result.width == COMPRESSION_PROFILES[level][0]
        assert result.getpixel((0, 0))[3] == 90


def test_invalid_level_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        compress_image_file(tmp_path / 'sample.png', level=5)

"""The immediately preceding backup schema adapts only missing known fields."""

import json
import zipfile

import pytest
from sqlalchemy import select

from app import backups
from app.models import User


async def test_manual_lucide_profile_icon_survives_backup_validation(db_session, tmp_path):
    user = await db_session.scalar(select(User).where(User.username == 'admin'))
    user.profile_icon = 'rocket'
    await db_session.commit()
    backups.write_archive(tmp_path / 'incoming.zip')
    _, data = backups.validate_archive(tmp_path)
    assert next(row for row in data['users'] if row['id'] == user.id)['profile_icon'] == 'rocket'


@pytest.mark.parametrize('mixed', [False, True])
async def test_previous_image_policy_schema(db_session, tmp_path, mixed):
    path = tmp_path / 'incoming.zip'
    backups.write_archive(path)
    with zipfile.ZipFile(path) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        data = json.loads(archive.read('data.json'))
    manifest['schema'] = backups.schema_fingerprint(before_image_policy=True)
    del data['site_settings'][0]['image_compression_enabled']
    del data['site_settings'][0]['image_compression_level']
    for user in data['users']:
        del user['profile_icon']
    if mixed:
        data['site_settings'][0]['image_compression_level'] = 4
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('manifest.json', json.dumps(manifest))
        archive.writestr('data.json', json.dumps(data))
    if mixed:
        with pytest.raises(backups.BackupError):
            backups.validate_archive(tmp_path)
    else:
        _, adapted = backups.validate_archive(tmp_path)
        assert adapted['site_settings'][0]['image_compression_enabled'] is True
        assert adapted['site_settings'][0]['image_compression_level'] == 2
        assert all(user['profile_icon'] == 'user-circle' for user in adapted['users'])

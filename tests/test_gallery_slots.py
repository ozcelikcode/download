"""Gallery slot presentation, natural file ordering and theme-aware panel regressions."""
import os
from pathlib import Path
import shutil
import subprocess

import pytest
from sqlalchemy import select

from app.dependencies import SESSION_COOKIE, create_admin_session_token
from app.models import Download, User


def test_gallery_slot_interactions():
    node = os.environ.get('BACKUP_TEST_NODE') or shutil.which('node')
    if not node:
        pytest.skip('Node is required for gallery interaction checks')
    script = Path(__file__).parent / 'js' / 'gallery-slots.mjs'
    subprocess.run([node, str(script)], check=True, capture_output=True, text=True)


async def test_editor_recent_details_and_gallery_controls(client, db_session):
    admin = await db_session.scalar(select(User).where(User.username == 'admin'))
    user = User(username='slot-editor', role='editor', password_hash=admin.password_hash)
    db_session.add(user)
    await db_session.flush()
    item = Download(title='My detailed content', slug='my-detailed-content', owner_id=user.id, version='2.4', download_count=1234)
    db_session.add(item)
    await db_session.commit()
    client.cookies.set(SESSION_COOKIE, create_admin_session_token(user.username, user.password_hash, user_id=user.id), domain='test.local', path='/')
    html = (await client.get('/panel')).text
    assert 'editor-recent-meta' in html and '2.4' in html and '1.234' in html
    html = (await client.get(f'/panel/downloads/{item.id}/edit')).text
    assert 'id="gallery-dropzone"' in html and 'id="gallery-more"' in html
    assert '<script src="/static/js/gallery-editor.js" type="module">' in html
    html = (await client.get('/panel/content-reports')).text
    assert 'report-empty' in html and 'class="mb-6"' in html
    html = (await client.get('/panel/media')).text
    assert 'media-image-toolbar' in html and 'media-image-search' in html

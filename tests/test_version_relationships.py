"""Version families remain shallow and preserve automatic history snapshots."""
import pytest

from app import crud
from app.schemas import DownloadCreate, DownloadUpdate


async def test_version_relationships_reject_self_nested_and_reparented_roots(db_session):
    root = await crud.create_download(db_session, DownloadCreate(title='Root', external_url='https://example.com'))
    other = await crud.create_download(db_session, DownloadCreate(title='Other', external_url='https://example.com'))
    child = await crud.create_download(db_session, DownloadCreate(title='Child', external_url='https://example.com', parent_id=root.id))
    for item, parent in [(root, root), (child, child), (other, child), (root, other)]:
        with pytest.raises(ValueError, match='Invalid version relationship'):
            await crud.update_download(db_session, item, DownloadUpdate(parent_id=parent.id))
    assert root.parent_id is None and child.parent_id == root.id


async def test_unchanged_versions_do_not_create_history_and_real_changes_do(db_session):
    from sqlalchemy import select
    from app.models import DownloadVersionHistory
    item = await crud.create_download(db_session, DownloadCreate(title='Versioned', external_url='https://example.com', version='1.0', file_size_bytes=123))
    await crud.update_download(db_session, item, DownloadUpdate(version='1.0'))
    assert list(await db_session.scalars(select(DownloadVersionHistory))) == []
    await crud.update_download(db_session, item, DownloadUpdate(version='2.0', file_size_bytes=456))
    history = list(await db_session.scalars(select(DownloadVersionHistory)))
    assert len(history) == 1 and history[0].version == '1.0' and history[0].file_size_bytes == 123
    assert item.version == '2.0' and item.file_size_bytes == 456

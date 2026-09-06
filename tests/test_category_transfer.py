from sqlalchemy import select

from app import crud
from app.models import Download, FileType, IconType, MenuItem
from app.schemas import CategoryCreate


async def test_renaming_category_updates_slug_menu_and_related_content(admin_client, db_session):
    source = await crud.create_category(db_session, CategoryCreate(name="Eski Ad"))
    target = await crud.create_category(db_session, CategoryCreate(name="Hedef"))
    source_id, target_id = source.id, target.id
    item = MenuItem(label="Eski", url=f"/category/{source.slug}")
    download = Download(title="Araç", slug="arac", file_type=FileType.external, icon_type=IconType.auto, external_url="https://example.com", category_id=source_id)
    db_session.add_all([item, download])
    await db_session.commit()
    item_id, download_id = item.id, download.id

    response = await admin_client.post(f"/admin/categories/{source_id}/edit", data={"name": "Yeni Ad", "description": "Yeni açıklama"})
    assert response.status_code == 302
    db_session.expire_all()
    updated = await crud.get_category_by_id(db_session, source_id)
    assert updated is not None and updated.slug == "yeni-ad"
    assert (await db_session.scalar(select(MenuItem.url).where(MenuItem.id == item_id))) == "/category/yeni-ad"
    assert (await db_session.scalar(select(Download.category_id).where(Download.id == download_id))) == source_id

    response = await admin_client.post(f"/admin/categories/{source_id}/delete", data={"target_category_id": str(target_id)})
    assert response.status_code == 302
    db_session.expire_all()
    assert await crud.get_category_by_id(db_session, source_id) is None
    assert (await db_session.scalar(select(Download.category_id).where(Download.id == download_id))) == target_id


async def test_required_category_cannot_be_deleted(admin_client, db_session):
    required = await crud.ensure_required_category(db_session)
    required_id = required.id
    response = await admin_client.post(f"/admin/categories/{required_id}/delete", data={"target_category_id": str(required_id)})
    assert response.status_code == 302
    assert await crud.get_category_by_id(db_session, required_id) is not None

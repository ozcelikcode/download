from sqlalchemy import func, select

from app import crud
from app.models import Download, DownloadLog
from app.schemas import DownloadCreate


async def test_download_moves_to_trash_then_permanent_delete_cascades_logs(admin_client, db_session):
    download = await crud.create_download(
        db_session, DownloadCreate(title="Silinecek", external_url="https://example.com/archive.zip")
    )
    from app.security import client_key
    db_session.add(DownloadLog(download_id=download.id, client_key=client_key("127.0.0.1", context="download")))
    await db_session.commit()

    response = await admin_client.post(
        f"/admin/downloads/{download.id}/delete?return_to=/admin/downloads?page=2"
    )

    assert response.status_code == 302
    assert response.headers["location"] == "/admin/downloads?page=2"
    db_session.expunge_all()
    trashed = await db_session.get(Download, download.id)
    assert trashed is not None and trashed.deleted_at is not None
    assert await db_session.scalar(select(func.count()).select_from(DownloadLog)) == 1
    assert (await admin_client.get(f"/download/{download.slug}")).status_code == 404
    assert (await admin_client.get(f"/dl/{download.slug}")).status_code == 404
    assert "Silinecek" in (await admin_client.get("/admin/downloads/trash")).text

    restore = await admin_client.post("/admin/downloads/trash/bulk", data={"action": "restore", "download_ids": str(download.id)})
    assert restore.status_code == 302
    db_session.expunge_all()
    restored = await db_session.get(Download, download.id)
    assert restored is not None and restored.deleted_at is None
    assert (await admin_client.get(f"/download/{download.slug}")).status_code == 200

    await admin_client.post(f"/admin/downloads/{download.id}/delete")
    purge = await admin_client.post("/admin/downloads/trash/bulk", data={"action": "purge", "download_ids": str(download.id)})
    assert purge.status_code == 302
    db_session.expunge_all()
    assert await db_session.get(Download, download.id) is None
    assert await db_session.scalar(select(func.count()).select_from(DownloadLog)) == 0


async def test_bulk_trash_hides_items_from_list_and_sitemap_and_restores(admin_client, db_session):
    first = await crud.create_download(db_session, DownloadCreate(title="Birinci silinen", external_url="https://example.com/one"))
    second = await crud.create_download(db_session, DownloadCreate(title="İkinci silinen", external_url="https://example.com/two"))
    response = await admin_client.post("/admin/downloads/bulk", data={
        "action": "delete", "download_ids": [str(first.id), str(second.id)],
    })
    assert response.status_code == 302
    assert "Birinci silinen" not in (await admin_client.get("/admin/downloads")).text
    assert "birinci-silinen" not in (await admin_client.get("/sitemap.xml")).text
    trash = await admin_client.get("/admin/downloads/trash")
    assert "Birinci silinen" in trash.text and "İkinci silinen" in trash.text
    restored = await admin_client.post("/admin/downloads/trash/bulk", data={
        "action": "restore", "download_ids": [str(first.id), str(second.id)],
    })
    assert restored.status_code == 302
    assert "Birinci silinen" in (await admin_client.get("/admin/downloads")).text


async def test_trash_requires_admin_and_rejects_active_items(client, admin_client, db_session):
    download = await crud.create_download(db_session, DownloadCreate(title="Korunan", external_url="https://example.com/keep"))
    assert (await client.get("/admin/downloads/trash")).status_code in {302, 303, 401, 403}
    response = await admin_client.post("/admin/downloads/trash/bulk", data={"action": "purge", "download_ids": str(download.id)})
    assert response.status_code == 302
    db_session.expunge_all()
    assert await db_session.get(Download, download.id) is not None


async def test_trashing_parent_groups_child_version_and_restores_both(admin_client, db_session):
    parent = await crud.create_download(db_session, DownloadCreate(title="Ana sürüm", external_url="https://example.com/main"))
    child = await crud.create_download(db_session, DownloadCreate(title="Eski sürüm", external_url="https://example.com/old", parent_id=parent.id))
    parent_id, child_id, child_slug = parent.id, child.id, child.slug

    await admin_client.post(f"/admin/downloads/{parent_id}/delete")
    db_session.expire_all()
    assert (await db_session.get(Download, parent_id)).deleted_at is not None
    assert (await db_session.get(Download, child_id)).deleted_at is not None
    trash = await admin_client.get("/admin/downloads/trash")
    assert "Ana sürüm" in trash.text
    assert "Eski sürüm" not in trash.text
    assert (await admin_client.get(f"/download/{child_slug}")).status_code == 404

    await admin_client.post("/admin/downloads/trash/bulk", data={"action": "restore", "download_ids": str(parent_id)})
    db_session.expire_all()
    assert (await db_session.get(Download, parent_id)).deleted_at is None
    assert (await db_session.get(Download, child_id)).deleted_at is None


async def test_delete_rejects_external_redirect_target(admin_client, db_session):
    download = await crud.create_download(
        db_session, DownloadCreate(title="Kalsın", external_url="https://example.com/archive.zip")
    )

    response = await admin_client.post(
        f"/admin/downloads/{download.id}/delete?return_to=https://example.invalid"
    )

    assert response.status_code == 302
    assert response.headers["location"] == "/admin/downloads"


async def test_delete_rejects_non_admin_or_malformed_return_target(admin_client, db_session):
    for target in ("/download/elsewhere", "//example.invalid", "/admin\\example.invalid"):
        download = await crud.create_download(
            db_session, DownloadCreate(title=f"Kalsın {target}", external_url="https://example.com/archive.zip")
        )
        db_session.expunge(download)
        response = await admin_client.post(
            f"/admin/downloads/{download.id}/delete", params={"return_to": target}
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/admin/downloads"


async def test_new_download_returns_to_content_list(admin_client):
    response = await admin_client.post(
        "/admin/downloads/new",
        data={
            "title": "Yeni kayıt",
            "file_type": "external",
            "external_url": "https://example.com/new.zip",
            "icon_type": "auto",
            "submission_intent": "publish",
            "is_active": "true",
        },
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/admin/downloads"
    content_list = await admin_client.get("/admin/downloads")
    assert "Yeni kayıt” uygulaması eklendi." in content_list.text


async def test_delete_preserves_every_list_filter_in_return_url(admin_client, db_session):
    download = await crud.create_download(
        db_session, DownloadCreate(title="Filtreli", external_url="https://example.com/archive.zip")
    )
    return_to = "/admin/downloads?page=3&q=demo&status_filter=active&file_type_filter=external"
    response = await admin_client.post(
        f"/admin/downloads/{download.id}/delete",
        params={"return_to": return_to},
    )
    assert response.headers["location"] == return_to

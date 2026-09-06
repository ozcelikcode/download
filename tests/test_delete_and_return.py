from sqlalchemy import func, select

from app import crud
from app.models import Download, DownloadLog
from app.schemas import DownloadCreate


async def test_deleting_download_with_logs_uses_database_cascade(admin_client, db_session):
    download = await crud.create_download(
        db_session, DownloadCreate(title="Silinecek", external_url="https://example.com/archive.zip")
    )
    await crud.create_download_log(db_session, download.id, "127.0.0.1", "test")

    response = await admin_client.post(
        f"/admin/downloads/{download.id}/delete?return_to=/admin/downloads?page=2"
    )

    assert response.status_code == 302
    assert response.headers["location"] == "/admin/downloads?page=2"
    db_session.expunge_all()
    assert await db_session.get(Download, download.id) is None
    assert await db_session.scalar(select(func.count()).select_from(DownloadLog)) == 0


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

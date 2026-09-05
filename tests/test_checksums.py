import hashlib

from app import crud
from app.config import settings
from app.schemas import DownloadCreate


async def test_checksum_matches_file_and_refreshes_after_replace(client, admin_client, db_session):
    path = settings.upload_path / "package.zip"
    path.write_bytes(b"original")
    download = await crud.create_download(db_session, DownloadCreate(title="Package", file_type="local", file_path=str(path)))
    original_digest = hashlib.sha256(b"original").hexdigest()
    response = await client.get(f"/download/{download.slug}")
    assert original_digest in response.text
    replaced = await admin_client.post("/admin/media/replace-file", data={"path": "/static/uploads/package.zip"}, files={"file": ("package.zip", b"replaced", "application/zip")})
    assert replaced.status_code == 200
    updated = await client.get(f"/download/{download.slug}")
    assert hashlib.sha256(b"replaced").hexdigest() in updated.text
    assert original_digest not in updated.text


async def test_external_link_has_no_invented_checksum(client, db_session):
    download = await crud.create_download(db_session, DownloadCreate(title="External", external_url="https://example.com"))
    response = await client.get(f"/download/{download.slug}")
    assert "SHA-256" not in response.text

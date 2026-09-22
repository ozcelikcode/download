from __future__ import annotations

from app.config import settings
from app.health import get_admin_health
from app.models import Category, Download, FileType, LinkCheck


async def test_admin_health_counts_database_and_storage_issues(db_session):
    category = Category(name="Araçlar", slug="araclar")
    db_session.add(category)
    await db_session.flush()

    private_root = settings.download_path.resolve()
    linked_file = private_root / "linked.zip"
    linked_file.write_bytes(b"abc")
    orphan_file = private_root / "orphan.zip"
    orphan_file.write_bytes(b"12345")
    (private_root / ".gitkeep").touch()

    icon_root = settings.upload_path / "icons"
    icon_root.mkdir(parents=True, exist_ok=True)
    (icon_root / "orphan.png").write_bytes(b"png")

    broken = Download(
        title="Kırık bağlantı",
        slug="kirik-baglanti",
        file_type=FileType.external,
        external_url="https://example.com/missing",
        category_id=category.id,
    )
    missing = Download(
        title="Eksik dosya",
        slug="eksik-dosya",
        file_type=FileType.local,
        file_path=str(private_root / "missing.zip"),
        category_id=category.id,
    )
    linked = Download(
        title="Bağlı dosya",
        slug="bagli-dosya",
        file_type=FileType.local,
        file_path=str(linked_file),
        category_id=category.id,
    )
    uncategorized = Download(
        title="Kategorisiz",
        slug="kategorisiz",
        file_type=FileType.external,
        external_url="https://example.com/download",
    )
    db_session.add_all([broken, missing, linked, uncategorized])
    await db_session.flush()
    db_session.add(
        LinkCheck(
            download_id=broken.id,
            url=broken.external_url,
            status="broken",
            http_status=404,
            message="HTTP 404",
        )
    )
    await db_session.commit()

    health = await get_admin_health(db_session)

    assert health.broken_links == 1
    assert health.missing_local_files == 1
    assert health.unused_media == 2
    assert health.uncategorized_content == 1
    assert health.private_storage_bytes == 8
    assert health.private_file_count == 2
    assert health.attention_count == 5


async def test_admin_dashboard_renders_health_center(admin_client):
    response = await admin_client.get("/admin")

    assert response.status_code == 200
    assert "Sağlık Merkezi" in response.text
    assert "Kontrol edilen alanlarda sorun görünmüyor" in response.text
    assert 'href="/admin/links?state=broken"' in response.text
    assert 'href="/admin/downloads?status_filter=draft"' in response.text
    assert 'href="/admin/downloads?category_id=uncategorized"' in response.text
    assert "0.0 B" in response.text


async def test_admin_uncategorized_health_link_filters_content(admin_client, db_session):
    category = Category(name="Belgeler", slug="belgeler")
    db_session.add(category)
    await db_session.flush()
    db_session.add_all(
        [
            Download(
                title="Kategorili kayıt",
                slug="kategorili-kayit",
                file_type=FileType.external,
                external_url="https://example.com/categorized",
                category_id=category.id,
            ),
            Download(
                title="Kategorisiz kayıt",
                slug="kategorisiz-kayit",
                file_type=FileType.external,
                external_url="https://example.com/uncategorized",
            ),
            Download(
                title="Kategorisiz taslak",
                slug="kategorisiz-taslak",
                file_type=FileType.external,
                external_url="https://example.com/draft",
                is_draft=True,
            ),
        ]
    )
    await db_session.commit()

    response = await admin_client.get("/admin/downloads?category_id=uncategorized")

    assert response.status_code == 200
    assert "Kategorisiz kayıt" in response.text
    assert "Kategorili kayıt" not in response.text
    assert "Kategorisiz taslak" not in response.text
    assert 'value="uncategorized" selected' in response.text

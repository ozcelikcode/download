from __future__ import annotations

from xml.etree import ElementTree

from app.config import settings
from app.models import Category, Download, FileType, LinkCheck, Tag


async def test_site_health_page_groups_technical_and_seo_findings(admin_client, db_session):
    category = Category(name="Utilities", slug="utilities")
    long_category = Category(
        name="Long Description",
        slug="long-description",
        description="Search-oriented category summary. " * 8,
    )
    db_session.add_all([category, long_category])
    await db_session.flush()

    broken = Download(
        title="Broken external package",
        slug="broken-package",
        file_type=FileType.external,
        external_url="https://example.com/broken",
        category_id=category.id,
    )
    missing = Download(
        title="Missing local package",
        slug="missing-package",
        file_type=FileType.local,
        file_path=str(settings.download_path / "missing.zip"),
    )
    missing_description = Download(
        title="An exceptionally long application title that exceeds sixty characters",
        slug="description-gap",
        file_type=FileType.external,
        external_url="https://example.com/description-gap",
        category_id=category.id,
    )
    categorized_item = Download(
        title="Long description category item",
        slug="long-category-item",
        file_type=FileType.external,
        external_url="https://example.com/long-category-item",
        category_id=long_category.id,
    )
    db_session.add_all([broken, missing, missing_description, categorized_item])
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

    response = await admin_client.get("/admin/site-health")

    assert response.status_code == 200
    assert "Site Sağlığı" in response.text
    assert "Teknik Sağlık" in response.text
    assert "Kırık dış bağlantılar" in response.text
    assert "Eksik yerel dosyalar" in response.text
    assert "Açıklaması olmayan yayınlar" in response.text
    assert "Uzun başlıklar" in response.text
    assert "Uzun kategori açıklamaları" in response.text
    assert "/admin/downloads/1/edit" in response.text
    assert "/sitemap.xml" in response.text
    assert "/robots.txt" in response.text


async def test_site_health_requires_admin(client):
    response = await client.get("/admin/site-health", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "/admin/login"


async def test_robots_and_sitemap_only_advertise_public_pages(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "app_base_url", "https://downloads.example.com")
    category = Category(name="Tools", slug="tools")
    tag = Tag(name="Utilities", slug="utilities")
    empty_category = Category(name="Empty", slug="empty")
    unused_tag = Tag(name="Unused", slug="unused")
    db_session.add_all([category, tag, empty_category, unused_tag])
    await db_session.flush()
    published = Download(
        title="Public package",
        slug="public-package",
        file_type=FileType.external,
        external_url="https://example.com/download",
        category_id=category.id,
        tags=[tag],
    )
    draft = Download(
        title="Draft package",
        slug="draft-package",
        file_type=FileType.external,
        external_url="https://example.com/draft",
        is_draft=True,
    )
    inactive = Download(
        title="Inactive package",
        slug="inactive-package",
        file_type=FileType.external,
        external_url="https://example.com/inactive",
        is_active=False,
    )
    db_session.add_all([published, draft, inactive])
    await db_session.commit()

    robots = await client.get("/robots.txt")
    sitemap = await client.get("/sitemap.xml")

    assert robots.status_code == 200
    assert "Disallow: /admin" in robots.text
    assert "Disallow: /dl/" in robots.text
    assert "Sitemap: https://downloads.example.com/sitemap.xml" in robots.text
    assert sitemap.status_code == 200
    assert sitemap.headers["content-type"].startswith("application/xml")
    root = ElementTree.fromstring(sitemap.content)
    locations = [node.text for node in root.findall("{*}url/{*}loc")]
    assert "https://downloads.example.com/" in locations
    assert "https://downloads.example.com/category/tools" in locations
    assert "https://downloads.example.com/tag/utilities" in locations
    assert "https://downloads.example.com/download/public-package" in locations
    assert "https://downloads.example.com/category/empty" not in locations
    assert "https://downloads.example.com/tag/unused" not in locations
    assert not any("draft-package" in url or "inactive-package" in url for url in locations)


async def test_invalid_base_url_does_not_publish_broken_sitemap_reference(client, monkeypatch):
    monkeypatch.setattr(settings, "app_base_url", "javascript:alert(1)")

    robots = await client.get("/robots.txt")
    sitemap = await client.get("/sitemap.xml")

    assert robots.status_code == 200
    assert "Sitemap:" not in robots.text
    assert sitemap.status_code == 503


async def test_base_url_rejects_line_breaks_in_robots_and_canonical(client, monkeypatch):
    monkeypatch.setattr(
        settings,
        "app_base_url",
        "https://site.example\r\nSitemap: https://attacker.example",
    )

    robots = await client.get("/robots.txt")
    homepage = await client.get("/")

    assert robots.status_code == 200
    assert robots.text.count("Sitemap:") == 0
    assert 'rel="canonical"' not in homepage.text


async def test_search_and_filtered_pages_are_noindex_with_clean_canonical(client, monkeypatch):
    monkeypatch.setattr(settings, "app_base_url", "https://site.example")
    search = await client.get("/search?q=some+term")
    filtered = await client.get("/?sort=popular&os=linux")

    assert '<meta name="robots" content="noindex,follow">' in search.text
    assert 'rel="canonical" href="https://site.example/search"' in search.text
    assert '<meta name="robots" content="noindex,follow">' in filtered.text
    assert 'rel="canonical" href="https://site.example/"' in filtered.text


async def test_detail_uses_short_description_as_search_metadata(client, db_session):
    download = Download(
        title="Metadata example",
        slug="metadata-example",
        short_description="A concise search result summary.",
        file_type=FileType.external,
        external_url="https://example.com/metadata",
    )
    db_session.add(download)
    await db_session.commit()

    response = await client.get("/download/metadata-example")

    assert response.status_code == 200
    assert '<meta name="description" content="A concise search result summary.">' in response.text


async def test_category_search_metadata_is_limited_to_160_characters(client, db_session):
    category = Category(
        name="Long Summary",
        slug="long-summary",
        description="A" * 190,
    )
    db_session.add(category)
    await db_session.flush()
    db_session.add(
        Download(
            title="Category item",
            slug="category-item",
            file_type=FileType.external,
            external_url="https://example.com/category-item",
            category_id=category.id,
        )
    )
    await db_session.commit()

    response = await client.get("/category/long-summary")

    assert response.status_code == 200
    assert f'<meta name="description" content="{"A" * 160}">' in response.text

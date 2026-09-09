from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.schemas import DownloadCreate


async def test_language_cookie_translates_chrome_and_keeps_content(
    client: AsyncClient, db_session: AsyncSession
):
    download = await crud.create_download(
        db_session,
        DownloadCreate(
            title="Türkçe Uygulama Adı",
            description="İçerik açıklaması çevrilmemeli.",
            file_type="external",
            external_url="https://example.com/app",
        ),
    )

    selected = await client.get(
        f"/language/en?return_to=/download/{download.slug}", follow_redirects=False
    )
    assert selected.status_code == 302
    assert selected.headers["location"] == f"/download/{download.slug}"

    page = await client.get(selected.headers["location"])
    assert '<html lang="en">' in page.text
    assert "Download Now" not in page.text
    assert "Open Link" in page.text
    assert "File Information" in page.text
    assert "Compatibility" in page.text
    assert "Not specified" in page.text
    assert "Türkçe Uygulama Adı" in page.text
    assert "İçerik açıklaması çevrilmemeli." in page.text


async def test_language_return_rejects_external_redirect(client: AsyncClient):
    response = await client.get(
        "/language/en?return_to=https://example.com", follow_redirects=False
    )
    assert response.headers["location"] == "/"


async def test_custom_menu_label_follows_public_language(
    admin_client: AsyncClient, client: AsyncClient
):
    response = await admin_client.post(
        "/admin/settings/menu",
        data={
            "label": "Hakkımızda",
            "label_en": "About",
            "url": "/about",
            "location": "navbar",
            "is_active": "true",
        },
    )
    assert response.status_code == 302

    turkish = await client.get("/")
    assert "Hakkımızda" in turkish.text
    client.cookies.set("ui_language", "en")
    english = await client.get("/")
    assert "About" in english.text
    assert "Hakkımızda" not in english.text


async def test_hero_has_live_preview_and_separate_english_text(
    admin_client: AsyncClient, client: AsyncClient
):
    appearance = await admin_client.get("/admin/settings/appearance")
    assert 'id="hero-live-preview"' in appearance.text
    assert 'name="component_text_en"' in appearance.text
    assert "hero-preview-language" not in appearance.text

    response = await admin_client.post(
        "/admin/settings/appearance",
        data={
            "logo_mode": "icon_text",
            "hero_enabled": "true",
            "hero_background": "mesh",
            "component_type": ["title", "search"],
            "component_text": ["Türkçe Hero", "Uygulama ara"],
            "component_text_en": ["English Hero", "Search applications"],
        },
    )
    assert response.status_code == 302

    client.cookies.set("ui_language", "en")
    home = await client.get("/")
    assert "English Hero" in home.text
    assert 'placeholder="Search applications"' in home.text
    assert "Türkçe Hero" not in home.text

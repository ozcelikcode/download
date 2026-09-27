from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.schemas import DownloadCreate, TagCreate
from app.models import LinkCheck


async def _set_language(admin_client: AsyncClient, language: str) -> None:
    response = await admin_client.post(
        "/admin/settings/language",
        data={"language": language},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/admin/settings/general"


async def test_admin_language_controls_site_and_admin_without_translating_content(
    admin_client: AsyncClient, client: AsyncClient, db_session: AsyncSession
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
    await _set_language(admin_client, "en")

    public_page = await client.get(f"/download/{download.slug}")
    assert '<html lang="en">' in public_page.text
    assert "Open Link" in public_page.text
    assert "File Information" in public_page.text
    assert "Türkçe Uygulama Adı" in public_page.text
    assert "İçerik açıklaması çevrilmemeli." in public_page.text
    assert 'property="og:locale" content="en_US"' in public_page.text
    assert 'rel="canonical"' in public_page.text

    admin_page = await admin_client.get("/admin/settings/general")
    assert '<html lang="en">' in admin_page.text
    assert "Site and Admin Language" in admin_page.text
    assert "Save Language" in admin_page.text
    assert "Activity Log" in admin_page.text


async def test_public_cookie_and_removed_language_route_cannot_override_setting(
    admin_client: AsyncClient, client: AsyncClient
):
    await _set_language(admin_client, "en")
    client.cookies.set("ui_language", "tr")
    home = await client.get("/")
    assert '<html lang="en">' in home.text
    assert 'placeholder="Search downloads..."' in home.text
    assert (await client.get("/language/tr", follow_redirects=False)).status_code == 404


async def test_custom_menu_and_hero_follow_global_site_language(
    admin_client: AsyncClient, client: AsyncClient
):
    response = await admin_client.post(
        "/admin/settings/menu",
        data={"label": "Hakkımızda", "label_en": "About", "url": "/about", "location": "navbar", "is_active": "true"},
    )
    assert response.status_code == 302
    response = await admin_client.post(
        "/admin/settings/appearance",
        data={
            "logo_mode": "icon_text", "hero_enabled": "true", "hero_background": "mesh",
            "component_type": ["title", "search"], "component_text": ["Türkçe Hero", "Uygulama ara"],
            "component_text_en": ["English Hero", "Search applications"],
        },
    )
    assert response.status_code == 302

    await _set_language(admin_client, "en")
    home = await client.get("/")
    assert "About" in home.text
    assert "Hakkımızda" not in home.text
    assert "English Hero" in home.text
    assert 'placeholder="Search applications"' in home.text
    assert "Türkçe Hero" not in home.text


async def test_invalid_language_is_rejected_and_current_language_remains(admin_client: AsyncClient):
    await _set_language(admin_client, "en")
    response = await admin_client.post(
        "/admin/settings/language", data={"language": "de"}, follow_redirects=False
    )
    assert response.status_code == 302
    page = await admin_client.get("/admin/settings/general")
    assert '<html lang="en">' in page.text
    assert 'value="en" class="peer sr-only" checked' in page.text


async def test_english_admin_pages_render_from_the_shared_setting(
    admin_client: AsyncClient, db_session: AsyncSession
):
    await _set_language(admin_client, "en")
    await crud.create_tag(db_session, TagCreate(name="Rendered tag"))
    pages = {
        "/admin": "Overview and site statistics",
        "/admin/site-health": "Technical checks",
        "/admin/downloads": "Search by title",
        "/admin/downloads/new": "Add New Download",
        "/admin/categories": "New Category",
        "/admin/tags": "New Tag",
        "/admin/media": "All images and files uploaded",
        "/admin/links": "Latest check results",
        "/admin/audit": "Admin changes and errors",
        "/admin/settings/account": "Admin Account",
        "/admin/settings/appearance": "Live Preview",
        "/admin/settings/menu": "Visibility Limits",
    }
    for path, expected in pages.items():
        response = await admin_client.get(path)
        assert response.status_code == 200, path
        assert '<html lang="en">' in response.text, path
        assert expected in response.text, path


async def test_language_switch_translates_saved_reports_filters_and_detail(
    admin_client: AsyncClient, client: AsyncClient, db_session: AsyncSession
):
    download = await crud.create_download(db_session, DownloadCreate(
        title="Kullanıcının Başlığı", external_url="https://example.com/file",
        os_compatibility=["windows", "linux"], is_official_source=True,
    ))
    db_session.add(LinkCheck(
        download_id=download.id, url=download.external_url, status="broken",
        http_status=404, message="Hedef dosya veya sayfa bulunamadı.",
    ))
    await db_session.commit()
    for language, expected, archive, audio, per_page, compatibility in (
        ("en", "The destination file or page was not found.", "Archive", "Audio", "per page", "Compatibility"),
        ("tr", "Hedef dosya veya sayfa bulunamadı.", "Arşiv", "Ses", "sayfa", "Uyumluluk"),
    ):
        await _set_language(admin_client, language)
        for path in ("/admin/links", "/admin/site-health"):
            page = await admin_client.get(path)
            assert page.status_code == 200
            assert expected in page.text
            assert "Kullanıcının Başlığı" in page.text
        media = await admin_client.get("/admin/media?tab=files")
        assert f'>{archive}</option>' in media.text
        assert f'>{audio}</option>' in media.text
        assert f'24 / {per_page}</option>' in media.text
        detail = await client.get(f"/download/{download.slug}")
        assert detail.status_code == 200
        assert detail.text.count(f'>{compatibility}</dt>') == 1
        assert 'cta_os_labels' not in detail.text
        assert detail.text.count('example.com') == 2  # source label and its link


async def test_english_publish_error_and_saved_success_report(
    admin_client: AsyncClient, db_session: AsyncSession
):
    await _set_language(admin_client, "en")
    draft = await crud.create_download_draft(db_session, "english-error", "Deneme")
    response = await admin_client.post(f"/admin/downloads/{draft.id}/edit", data={
        "title": "Deneme", "file_type": "external", "external_url": "invalid",
        "submission_intent": "publish", "icon_type": "auto",
    }, headers={"Accept": "application/json"})
    assert response.status_code == 422
    assert response.json()["message"] == "External URL: Enter a complete HTTP or HTTPS URL."
    db_session.add(LinkCheck(
        download_id=draft.id, url=draft.external_url or "", status="ok",
        http_status=200, message="Bağlantı erişilebilir.",
    ))
    await db_session.commit()
    # Existing Turkish diagnostics are translated at display time.
    from app.i18n import system_message
    assert system_message(None, "Bağlantı erişilebilir.") == "Link is accessible."
    await _set_language(admin_client, "tr")
    assert system_message(None, "Link is accessible.") == "Bağlantı erişilebilir."


async def test_form_length_errors_follow_language(admin_client: AsyncClient):
    from pydantic import ValidationError
    from app.routers.admin import _download_form_error
    from app.schemas import DownloadUpdate

    for language, expected in (("tr", "En fazla 300 karakter girin."), ("en", "Enter at most 300 characters.")):
        await _set_language(admin_client, language)
        try:
            DownloadUpdate(short_description="x" * 301)
        except ValidationError as exc:
            message = _download_form_error(None, exc)
        else:
            raise AssertionError("Expected length validation")
        assert expected in message
        assert "validation error" not in message

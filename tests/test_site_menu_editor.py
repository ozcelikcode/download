"""
Menü Düzenleme sayfasının yeni bölümleri: site kimliği, navbar/footer
konumu ayrımı, kategori sıralaması ve kategori açıklaması.
"""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.schemas import CategoryCreate


async def test_branding_update_reflects_on_public_pages(
    admin_client: AsyncClient, client: AsyncClient
):
    response = await admin_client.post(
        "/panel/settings/branding",
        data={"site_name": "Yeni Site Adı", "site_icon": "rocket", "site_icon_color": "purple"},
    )
    assert response.status_code == 302

    home = await client.get("/")
    assert "Yeni Site Adı" in home.text
    assert 'data-lucide="rocket"' in home.text


async def test_branding_update_requires_admin(client: AsyncClient):
    response = await client.post(
        "/panel/settings/branding",
        data={"site_name": "X", "site_icon": "home", "site_icon_color": "blue"},
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/login"


async def test_theme_color_is_reflected_in_public_and_admin_pages(
    admin_client: AsyncClient, client: AsyncClient
):
    response = await admin_client.post(
        "/panel/settings/branding",
        data={"site_name": "Tema", "site_icon": "palette", "theme_color": "green"},
    )
    assert response.status_code == 302
    home = await client.get("/")
    admin_login = await client.get("/login")
    assert 'data-theme-color="green"' in home.text
    assert "--accent: #247a4d" in home.text
    assert 'data-theme-color="green"' in admin_login.text


async def test_theme_is_managed_from_appearance_without_changing_site_identity(
    admin_client: AsyncClient, client: AsyncClient
):
    appearance = await admin_client.get("/panel/settings/appearance")
    general = await admin_client.get("/panel/settings/general")
    assert 'action="/panel/settings/theme"' in appearance.text
    assert 'name="theme_color"' not in general.text
    assert 'action="/panel/settings/seo"' not in general.text
    assert 'action="/panel/settings/audit-log-limit"' not in general.text

    response = await admin_client.post(
        "/panel/settings/theme", data={"theme_color": "amoled"}
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/panel/settings/appearance"
    home = await client.get("/")
    assert 'data-theme-color="amoled"' in home.text
    assert "Download Sitesi" in home.text

    await admin_client.post(
        "/panel/settings/branding",
        data={"site_name": "Yeni İsim", "site_icon": "star"},
    )
    updated = await client.get("/")
    assert 'data-theme-color="amoled"' in updated.text
    assert "Yeni İsim" in updated.text

    invalid = await admin_client.post(
        "/panel/settings/theme", data={"theme_color": "unknown"}
    )
    assert invalid.status_code == 422
    assert 'data-theme-color="amoled"' in (await client.get("/")).text


async def test_amoled_admin_navigation_receives_neutral_theme_palette(admin_client: AsyncClient):
    response = await admin_client.post(
        "/panel/settings/branding",
        data={"site_name": "AMOLED", "site_icon": "palette", "theme_color": "amoled"},
    )
    assert response.status_code == 302
    content = await admin_client.get("/panel/downloads")
    assert 'data-theme-color="amoled"' in content.text
    assert '--accent-dark: #c4c4ca' in content.text
    assert 'class="admin-nav-link is-active"' in content.text


async def test_navbar_and_footer_items_are_independent(
    admin_client: AsyncClient, client: AsyncClient, db_session: AsyncSession
):
    await admin_client.post(
        "/panel/settings/menu",
        data={"label": "Navbar Öğesi", "url": "/x", "location": "navbar", "is_active": "true"},
    )
    await admin_client.post(
        "/panel/settings/menu",
        data={"label": "Footer Öğesi", "url": "/y", "location": "footer", "is_active": "true"},
    )

    navbar = await crud.get_menu_items(db_session, location="navbar")
    footer = await crud.get_menu_items(db_session, location="footer")
    assert [i.label for i in navbar] == ["Navbar Öğesi"]
    assert [i.label for i in footer] == ["Footer Öğesi"]

    home = await client.get("/")
    # Footer öğesi sitede footer'da görünmeli, navbar öğesi üst menüde.
    assert "Navbar Öğesi" in home.text
    assert "Footer Öğesi" in home.text


async def test_category_reorder_changes_sidebar_order(
    admin_client: AsyncClient, client: AsyncClient, db_session: AsyncSession
):
    cat_a = await crud.create_category(db_session, CategoryCreate(name="Araçlar"))
    cat_b = await crud.create_category(db_session, CategoryCreate(name="Oyunlar"))

    ordered = await crud.get_categories_ordered(db_session)
    assert [c.id for c in ordered] == [cat_a.id, cat_b.id]

    response = await admin_client.post(
        "/panel/settings/categories/reorder", json={"ids": [cat_b.id, cat_a.id]}
    )
    assert response.status_code == 200

    reordered = await crud.get_categories_ordered(db_session)
    assert [c.id for c in reordered] == [cat_b.id, cat_a.id]

    home = await client.get("/")
    assert home.text.index("Oyunlar") < home.text.index("Araçlar")


async def test_category_description_shown_on_category_page(
    client: AsyncClient, db_session: AsyncSession
):
    cat = await crud.create_category(
        db_session,
        CategoryCreate(name="Geliştirici Araçları", description="IDE ve terminal araçları."),
    )
    page = await client.get(f"/category/{cat.slug}")
    assert page.status_code == 200
    assert "IDE ve terminal araçları." in page.text


async def test_menu_editor_page_renders_all_sections(admin_client: AsyncClient):
    response = await admin_client.get("/panel/settings/menu")
    assert response.status_code == 200
    assert "Üst Menü (Navbar)" in response.text
    assert "Kategori Menüsü (Sidebar)" in response.text
    assert "Footer" in response.text


async def test_settings_general_page_renders(admin_client: AsyncClient):
    response = await admin_client.get("/panel/settings/general")
    assert response.status_code == 200
    assert "Site Kimliği" in response.text


async def test_settings_account_page_renders(admin_client: AsyncClient):
    response = await admin_client.get("/panel/settings/account")
    assert response.status_code == 200
    assert "Hesabınız" in response.text


async def test_settings_appearance_page_renders(admin_client: AsyncClient):
    response = await admin_client.get("/panel/settings/appearance")
    assert response.status_code == 200
    assert "Hero alanı" in response.text
    assert "Karanlık tema logosu" in response.text


async def test_settings_root_redirects_to_general(admin_client: AsyncClient):
    response = await admin_client.get("/panel/settings", follow_redirects=False)
    assert response.status_code in (302, 303, 307)
    assert response.headers["location"].endswith("/panel/settings/general")


async def test_appearance_settings_drive_public_hero_and_limits(
    admin_client: AsyncClient, client: AsyncClient, db_session: AsyncSession
):
    for index in range(7):
        await admin_client.post(
            "/panel/settings/menu",
            data={"label": f"Link {index}", "url": f"/link-{index}", "location": "navbar", "is_active": "true"},
        )
    response = await admin_client.post(
        "/panel/settings/appearance",
        data={
            "logo_mode": "icon_text", "hero_enabled": "true", "hero_background": "lines",
            "component_type": ["title", "search"],
            "component_text": ["Özel Hero Başlığı", "Program ara"],
        },
    )
    assert response.status_code == 302
    assert (await admin_client.post("/panel/settings/menu-limits", data={"navbar_limit": 3, "footer_limit": 4, "sidebar_category_limit": 5, "sidebar_tag_limit": 25})).status_code == 302
    home = await client.get("/")
    assert "Özel Hero Başlığı" in home.text
    assert 'placeholder="Program ara"' in home.text
    assert 'hero-bg-lines' in home.text
    assert sum(f"Link {index}" in home.text for index in range(7)) == 3


async def test_menu_can_pull_one_category_and_reject_duplicate(
    admin_client: AsyncClient, db_session: AsyncSession
):
    category = await crud.create_category(db_session, CategoryCreate(name="Grafik"))
    data = {"source_type": "category", "source_id": category.id, "location": "navbar"}
    assert (await admin_client.post("/panel/settings/menu/from-source", data=data)).status_code == 302
    assert (await admin_client.post("/panel/settings/menu/from-source", data=data)).status_code == 302
    items = await crud.get_menu_items(db_session, location="navbar")
    assert len(items) == 1
    assert items[0].url == f"/category/{category.slug}"

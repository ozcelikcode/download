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
        "/admin/settings/branding",
        data={"site_name": "Yeni Site Adı", "site_icon": "rocket", "site_icon_color": "purple"},
    )
    assert response.status_code == 302

    home = await client.get("/")
    assert "Yeni Site Adı" in home.text
    assert 'data-lucide="rocket"' in home.text


async def test_branding_update_requires_admin(client: AsyncClient):
    response = await client.post(
        "/admin/settings/branding",
        data={"site_name": "X", "site_icon": "home", "site_icon_color": "blue"},
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/admin/login"


async def test_navbar_and_footer_items_are_independent(
    admin_client: AsyncClient, client: AsyncClient, db_session: AsyncSession
):
    await admin_client.post(
        "/admin/settings/menu",
        data={"label": "Navbar Öğesi", "url": "/x", "location": "navbar", "is_active": "true"},
    )
    await admin_client.post(
        "/admin/settings/menu",
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
        "/admin/settings/categories/reorder", json={"ids": [cat_b.id, cat_a.id]}
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
    response = await admin_client.get("/admin/settings/menu")
    assert response.status_code == 200
    assert "Üst Menü (Navbar)" in response.text
    assert "Kategori Menüsü (Sidebar)" in response.text
    assert "Footer" in response.text


async def test_settings_general_page_renders(admin_client: AsyncClient):
    response = await admin_client.get("/admin/settings/general")
    assert response.status_code == 200
    assert "Site Kimliği" in response.text


async def test_settings_account_page_renders(admin_client: AsyncClient):
    response = await admin_client.get("/admin/settings/account")
    assert response.status_code == 200
    assert "Admin Hesabı" in response.text


async def test_settings_root_redirects_to_general(admin_client: AsyncClient):
    response = await admin_client.get("/admin/settings", follow_redirects=False)
    assert response.status_code in (302, 303, 307)
    assert response.headers["location"].endswith("/admin/settings/general")

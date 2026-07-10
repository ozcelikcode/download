"""
Menü Düzenleme özelliği için testler.

Kapsam:
  - Menü boşken site navigasyonunun boş kalması (otomatik/fallback yok)
  - Menü öğesi oluşturma → sitede görünmesi
  - Sıralamanın (drag & drop) kalıcı olması
  - Pasif öğelerin herkese açık sitede gösterilmemesi
  - Güncelleme ve silme
  - Admin oturumu olmadan erişilememesi
"""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud


async def test_nav_is_empty_without_menu_items(client: AsyncClient):
    response = await client.get("/")
    assert response.status_code == 200
    assert "Tümü" not in response.text  # eski otomatik menü kalıntısı olmamalı


async def test_create_menu_item_appears_in_public_nav(
    admin_client: AsyncClient, db_session: AsyncSession
):
    response = await admin_client.post(
        "/admin/settings/menu",
        data={
            "label": "Blog",
            "url": "/blog",
            "icon": "newspaper",
            "is_active": "true",
            "open_in_new_tab": "false",
        },
    )
    assert response.status_code == 302

    items = await crud.get_menu_items(db_session)
    assert len(items) == 1
    assert items[0].label == "Blog"
    assert items[0].url == "/blog"
    assert items[0].icon == "newspaper"

    home = await admin_client.get("/")
    assert "Blog" in home.text


async def test_reorder_persists_position(admin_client: AsyncClient, db_session: AsyncSession):
    await admin_client.post("/admin/settings/menu", data={"label": "Birinci", "url": "/a"})
    await admin_client.post("/admin/settings/menu", data={"label": "İkinci", "url": "/b"})

    items = await crud.get_menu_items(db_session)
    assert [i.label for i in items] == ["Birinci", "İkinci"]

    reversed_ids = [i.id for i in reversed(items)]
    response = await admin_client.post(
        "/admin/settings/menu/reorder", json={"ids": reversed_ids}
    )
    assert response.status_code == 200
    assert response.json() == {"ok": True}

    reordered = await crud.get_menu_items(db_session)
    assert [i.label for i in reordered] == ["İkinci", "Birinci"]


async def test_inactive_menu_item_hidden_from_public_nav(
    admin_client: AsyncClient, db_session: AsyncSession
):
    await admin_client.post(
        "/admin/settings/menu",
        data={"label": "Taslak Sayfa", "url": "/taslak", "is_active": "true"},
    )
    item = (await crud.get_menu_items(db_session))[0]

    # is_active alanı formda gönderilmezse False'a düşer (checkbox mantığı)
    await admin_client.post(
        f"/admin/settings/menu/{item.id}/edit",
        data={"label": "Taslak Sayfa", "url": "/taslak"},
    )

    active_items = await crud.get_menu_items(db_session, active_only=True)
    assert active_items == []

    home = await admin_client.get("/")
    assert "Taslak Sayfa" not in home.text


async def test_update_menu_item(admin_client: AsyncClient, db_session: AsyncSession):
    await admin_client.post("/admin/settings/menu", data={"label": "Eski Ad", "url": "/x"})
    item_id = (await crud.get_menu_items(db_session))[0].id

    response = await admin_client.post(
        f"/admin/settings/menu/{item_id}/edit",
        data={
            "label": "Yeni Ad",
            "url": "/y",
            "icon": "star",
            "is_active": "true",
            "open_in_new_tab": "true",
        },
    )
    assert response.status_code == 302

    # Güncelleme, admin_client'ın kendi (farklı) session'ında yapıldı;
    # db_session'ın identity map'indeki eski nesneyi tazelemek gerekir.
    db_session.expire_all()
    updated = await crud.get_menu_item_by_id(db_session, item_id)
    assert updated.label == "Yeni Ad"
    assert updated.url == "/y"
    assert updated.icon == "star"
    assert updated.open_in_new_tab is True


async def test_delete_menu_item(admin_client: AsyncClient, db_session: AsyncSession):
    await admin_client.post("/admin/settings/menu", data={"label": "Silinecek", "url": "/z"})
    item = (await crud.get_menu_items(db_session))[0]

    response = await admin_client.post(f"/admin/settings/menu/{item.id}/delete")
    assert response.status_code == 302

    assert await crud.get_menu_items(db_session) == []


async def test_menu_settings_requires_admin_session(client: AsyncClient):
    response = await client.get("/admin/settings/menu")
    assert response.status_code == 302
    assert response.headers["location"] == "/admin/login"

    response = await client.post(
        "/admin/settings/menu", data={"label": "X", "url": "/x"}
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/admin/login"

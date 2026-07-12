"""
İndirme kayıtları — kaynak türü (resmî / üçüncü parti) ve kaynak adresi testleri.
"""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.models import Download
from app.schemas import DownloadCreate


async def _create_external(session: AsyncSession, **overrides) -> Download:
    data = DownloadCreate(
        title=overrides.pop("title", "VS Code"),
        file_type="external",
        external_url=overrides.pop("external_url", "https://code.visualstudio.com/sha/download?build=stable"),
        **overrides,
    )
    return await crud.create_download(session, data)


async def test_source_domain_includes_subdomain(db_session: AsyncSession):
    d = await _create_external(db_session)
    assert d.source_domain == "code.visualstudio.com"
    assert d.source_root_url == "https://code.visualstudio.com"


async def test_official_source_badge_on_detail_page(
    client: AsyncClient, db_session: AsyncSession
):
    d = await _create_external(db_session, is_official_source=True)
    page = await client.get(f"/download/{d.slug}")
    assert page.status_code == 200
    assert "Resmî Site" in page.text
    assert "Üçüncü Parti Site" not in page.text
    # Kaynak linki derin URL'ye değil, sitenin ana adresine gitmeli.
    assert 'href="https://code.visualstudio.com"' in page.text


async def test_third_party_source_badge_on_detail_page(
    client: AsyncClient, db_session: AsyncSession
):
    d = await _create_external(
        db_session, title="VS Code Mirror",
        external_url="https://mirror.example.com/vscode.exe",
        is_official_source=False,
    )
    page = await client.get(f"/download/{d.slug}")
    assert "Üçüncü Parti Site" in page.text


async def test_detail_cta_says_baglantiya_git_for_external(
    client: AsyncClient, db_session: AsyncSession
):
    d = await _create_external(db_session)
    page = await client.get(f"/download/{d.slug}")
    assert "Bağlantıya Git" in page.text
    assert "Şimdi Bağlantıya Git" not in page.text


async def test_index_card_always_says_indir(client: AsyncClient, db_session: AsyncSession):
    d = await _create_external(db_session)
    home = await client.get("/")
    assert "Bağlantıya Git" not in home.text
    # Kart butonu detay sayfasına gitmeli.
    assert f'href="/download/{d.slug}" class="btn-download"' in home.text


async def test_admin_form_sets_official_source(
    admin_client: AsyncClient, db_session: AsyncSession
):
    response = await admin_client.post(
        "/admin/downloads/new",
        data={
            "title": "Üçüncü Parti Araç",
            "file_type": "external",
            "external_url": "https://ucuncu-parti.example.com/arac.zip",
            "icon_type": "auto",
            "is_active": "true",
            "is_official_source": "false",
        },
    )
    assert response.status_code == 302

    items, _ = await crud.get_downloads_paginated(db_session, include_inactive=True)
    assert items[0].is_official_source is False

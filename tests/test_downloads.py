"""
İndirme kayıtları — kaynak türü (resmî / üçüncü parti) ve kaynak adresi testleri.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.models import Download, DownloadLog
from app.schemas import DownloadCreate
from pydantic import ValidationError
import pytest


async def _create_external(session: AsyncSession, **overrides) -> Download:
    data = DownloadCreate(
        title=overrides.pop("title", "VS Code"),
        file_type="external",
        external_url=overrides.pop("external_url", "https://code.visualstudio.com/sha/download?build=stable"),
        **overrides,
    )
    return await crud.create_download(session, data)


async def test_latest_version_external_link_is_localized(
    admin_client: AsyncClient, client: AsyncClient, db_session: AsyncSession
):
    response = await admin_client.post(
        "/panel/downloads/new",
        data={
            "title": "Always Fresh",
            "version": "v1.0",
            "is_latest_version": "true",
            "file_type": "external",
            "external_url": "https://example.com/latest",
            "icon_type": "auto",
            "submission_intent": "publish",
            "is_active": "true",
            "is_official_source": "true",
        },
    )
    assert response.status_code == 302
    download = await crud.get_download_by_slug(db_session, "always-fresh")
    assert download is not None
    assert download.is_latest_version is True
    assert download.version is None

    turkish = await client.get(f"/download/{download.slug}")
    assert "Güncel sürüm" in turkish.text
    assert "Güncel sürüm" in (await client.get("/")).text
    language_response = await admin_client.post(
        "/panel/settings/language", data={"language": "en"}
    )
    assert language_response.status_code == 302
    english = await client.get(f"/download/{download.slug}")
    assert "Latest version" in english.text
    assert "Latest version" in (await client.get("/")).text


def test_latest_version_rejects_local_source():
    with pytest.raises(ValidationError):
        DownloadCreate(
            title="Local",
            file_type="local",
            file_path="/tmp/local.zip",
            is_latest_version=True,
        )


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


@pytest.mark.parametrize("state", ["deleted", "inactive", "draft"])
async def test_download_log_rejects_content_hidden_before_recording(
    db_session: AsyncSession, state: str
):
    download = await _create_external(db_session, title=f"Hidden {state}")
    if state == "deleted":
        download.deleted_at = datetime.now(timezone.utc)
    elif state == "inactive":
        download.is_active = False
    else:
        download.is_draft = True
    await db_session.commit()

    allowed = await crud.record_download_if_allowed(
        db_session, download.id, "127.0.0.1", 100
    )
    assert allowed is False
    assert await db_session.scalar(select(func.count()).select_from(DownloadLog)) == 0


async def test_download_log_does_not_store_client_address(db_session: AsyncSession):
    download = await _create_external(db_session, title="Privacy check")
    download_id = download.id
    assert await crud.record_download_if_allowed(db_session, download_id, "192.0.2.42", 100)

    log = await db_session.scalar(select(DownloadLog).where(DownloadLog.download_id == download_id))
    assert log is not None
    assert len(log.client_key) == 64
    assert "192.0.2.42" not in log.client_key
    assert not hasattr(log, "ip_address")
    assert not hasattr(log, "user_agent")


async def test_editor_keeps_optional_fields_available_without_crowding_new_form(
    admin_client: AsyncClient, db_session: AsyncSession,
):
    new_form = await admin_client.get("/panel/downloads/new")
    assert new_form.status_code == 200
    icon_section = re.search(r'<details id="icon-options"[^>]*>', new_form.text)
    assert icon_section is not None and " open" not in icon_section.group()
    assert 'name="icon_type"' in new_form.text
    assert 'name="parent_id"' in new_form.text
    assert 'name="os_tags"' in new_form.text
    assert 'id="application-publish-button"' in new_form.text
    assert 'id="application-save-button"' in new_form.text

    download = await _create_external(db_session, title="Icon settings", icon_type="zip")
    edit_form = await admin_client.get(f"/panel/downloads/{download.id}/edit")
    icon_section = re.search(r'<details id="icon-options"[^>]*>', edit_form.text)
    assert icon_section is not None and " open" in icon_section.group()


async def test_active_draft_is_not_publicly_visible_or_downloadable(
    client: AsyncClient, db_session: AsyncSession
):
    download = await _create_external(db_session, title="Hidden draft")
    download.is_draft = True
    await db_session.commit()

    assert (await client.get(f"/download/{download.slug}")).status_code == 404
    assert (await client.get(f"/dl/{download.slug}")).status_code == 404


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
        "/panel/downloads/new",
        data={
            "title": "Üçüncü Parti Araç",
            "file_type": "external",
            "external_url": "https://ucuncu-parti.example.com/arac.zip",
            "icon_type": "auto",
            "submission_intent": "publish",
            "is_active": "true",
            "is_official_source": "false",
        },
    )
    assert response.status_code == 302

    items, _ = await crud.get_downloads_paginated(db_session, include_inactive=True)
    assert items[0].is_official_source is False

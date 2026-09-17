"""Zengin metin ve yönetilen URL güvenlik sınırları."""

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.content_security import normalize_http_url, normalize_navigation_url, sanitize_rich_text
from app.models import Download, FileType, IconType
from app.schemas import DownloadCreate, MenuItemCreate


def test_rich_text_sanitizer_preserves_editor_formatting_and_removes_active_content():
    cleaned = sanitize_rich_text(
        '<p class="ql-align-center" onclick="alert(1)">'
        '<strong>Güvenli</strong><span style="color:red;position:fixed"> metin</span>'
        '<img src="/static/uploads/icon.png" onerror="alert(2)">'
        '<script>alert(3)</script></p>'
    )

    assert cleaned is not None
    assert "Güvenli" in cleaned
    assert 'class="ql-align-center"' in cleaned
    assert "color:red" in cleaned
    assert 'src="/static/uploads/icon.png"' in cleaned
    assert "onclick" not in cleaned
    assert "onerror" not in cleaned
    assert "position" not in cleaned
    assert "script" not in cleaned
    assert "alert(3)" not in cleaned


def test_rich_text_sanitizer_blocks_unsafe_link_schemes():
    cleaned = sanitize_rich_text(
        '<a href="javascript:alert(1)" target="_blank">kötü</a>'
        '<a href="https://example.com" target="_blank">iyi</a>'
    )
    assert 'javascript:' not in (cleaned or "")
    assert 'href="https://example.com"' in (cleaned or "")
    assert 'rel="noopener noreferrer"' in (cleaned or "")


@pytest.mark.parametrize(
    "url",
    ["javascript:alert(1)", "data:text/html,x", "//evil.example/x", "https://user:pass@example.com"],
)
def test_unsafe_urls_are_rejected_by_schemas(url: str):
    with pytest.raises(ValidationError):
        DownloadCreate(title="Riskli", external_url=url)
    with pytest.raises(ValidationError):
        MenuItemCreate(label="Riskli", url=url)


def test_safe_http_and_navigation_urls_are_normalized():
    assert normalize_http_url(" https://example.com/file.zip?q=1 ") == "https://example.com/file.zip?q=1"
    assert normalize_navigation_url("/category/tools?page=2") == "/category/tools?page=2"
    assert normalize_navigation_url("#downloads") == "#downloads"


async def test_menu_route_rejects_unsafe_url(admin_client, db_session: AsyncSession):
    response = await admin_client.post(
        "/admin/settings/menu",
        data={"label": "Riskli", "url": "javascript:alert(1)", "is_active": "true"},
    )
    assert response.status_code == 422
    assert await crud.get_menu_items(db_session) == []


async def test_legacy_description_is_sanitized_when_rendered(client, db_session: AsyncSession):
    download = Download(
        title="Eski kayıt",
        slug="eski-kayit",
        description='<strong>Güvenli</strong><img src="x" onerror="alert(1)"><script>alert(2)</script>',
        file_type=FileType.external,
        icon_type=IconType.link,
        external_url="https://example.com/file.zip",
        is_active=True,
    )
    db_session.add(download)
    await db_session.commit()

    response = await client.get("/download/eski-kayit")
    assert response.status_code == 200
    assert "<strong>Güvenli</strong>" in response.text
    assert "onerror" not in response.text
    assert "alert(2)" not in response.text


async def test_legacy_unsafe_download_redirect_is_blocked(client, db_session: AsyncSession):
    download = Download(
        title="Riskli yönlendirme",
        slug="riskli-yonlendirme",
        file_type=FileType.external,
        icon_type=IconType.link,
        external_url="javascript:alert(1)",
        is_active=True,
    )
    db_session.add(download)
    await db_session.commit()

    response = await client.get("/dl/riskli-yonlendirme")
    assert response.status_code == 404

"""Shared administration navigation and page heading smoke tests."""

import re

import pytest
from httpx import AsyncClient


@pytest.mark.parametrize(
    "path",
    [
        "/panel/downloads", "/panel/downloads/trash", "/panel/pages",
        "/panel/pages/trash", "/panel/categories", "/panel/tags",
        "/panel/media", "/panel/links", "/panel/audit", "/panel/users",
        "/panel/settings/maintenance",
    ],
)
async def test_admin_pages_share_breadcrumb_and_description(admin_client: AsyncClient, path: str):
    response = await admin_client.get(path)
    assert response.status_code == 200
    assert '<nav class="breadcrumb' in response.text
    assert 'href="/panel"' in response.text
    assert re.search(r"<h1\b[^>]*>.+?</h1>", response.text, re.S)


async def test_user_page_keeps_management_navigation_open(admin_client: AsyncClient):
    response = await admin_client.get("/panel/users")
    assert response.status_code == 200
    assert re.search(r'<details class="admin-nav-group" open>\s*<summary[^>]*>.*?/panel/users', response.text, re.S)
    assert 'href="/panel/users" class="admin-nav-link is-active"' in response.text


async def test_account_page_renders_without_redirect(admin_client: AsyncClient):
    response = await admin_client.get("/panel/settings/account", follow_redirects=False)
    assert response.status_code == 200
    assert 'href="/panel/settings/account" class="admin-nav-link is-active"' in response.text

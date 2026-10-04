import re


async def test_content_navigation_opens_current_group_and_keeps_trash_action_inline(admin_client):
    response = await admin_client.get("/panel/downloads")
    assert response.status_code == 200
    html = response.text
    assert re.search(r'<details class="admin-nav-group" open>\s*<summary[^>]*>.*?Tüm içerikler', html, re.S)
    assert 'name="admin-sidebar"' not in html
    assert 'href="/panel/downloads" class="admin-nav-link is-active" aria-current="page"' in html
    assert 'btn-secondary py-2 px-3 text-sm shrink-0' in html


async def test_management_navigation_opens_on_category_page(admin_client):
    response = await admin_client.get("/panel/categories")
    assert response.status_code == 200
    html = response.text
    assert re.search(r'<details class="admin-nav-group" open>\s*<summary[^>]*>.*?Kategoriler', html, re.S)
    assert 'href="/panel/categories" class="admin-nav-link is-active" aria-current="page"' in html

"""Access, publication, sanitization, and lifecycle of standalone pages."""

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Page


async def test_page_draft_then_publication_and_html_sanitization(
    admin_client: AsyncClient, client: AsyncClient, db_session: AsyncSession,
):
    created = await admin_client.post("/admin/pages", data={
        "title": "About us", "slug": "about-us",
        "body_html": "<p>Hello visitors</p><script>alert(1)</script>",
        "visibility": "public", "is_published": "false",
    }, follow_redirects=False)
    assert created.status_code == 303
    assert created.headers["location"].startswith("/admin/pages/")
    assert (await client.get("/page/about-us")).status_code == 404
    preview = await admin_client.get("/page/about-us")
    assert preview.status_code == 200
    assert "no-store" in preview.headers["cache-control"]
    assert preview.headers["x-robots-tag"].startswith("noindex")
    assert "alert(1)" not in preview.text

    page = await db_session.scalar(select(Page).where(Page.slug == "about-us"))
    published = await admin_client.post(f"/admin/pages/{page.id}/edit", data={
        "title": "About us", "slug": "about-us",
        "body_html": "<p>Hello visitors</p><script>alert(1)</script>",
        "visibility": "public", "is_published": "true",
    }, follow_redirects=False)
    assert published.status_code == 303
    public = await client.get("/page/about-us")
    assert public.status_code == 200
    assert "Hello visitors" in public.text
    assert "alert(1)" not in public.text
    assert "noindex" not in public.headers.get("x-robots-tag", "")
    sitemap = await client.get("/sitemap.xml")
    assert sitemap.status_code == 200
    assert "/page/about-us" in sitemap.text


async def test_private_page_requires_admin_and_never_leaks_into_menu(
    admin_client: AsyncClient, client: AsyncClient, db_session: AsyncSession,
):
    created = await admin_client.post("/admin/pages", data={
        "title": "Secret notes", "slug": "secret-notes",
        "body_html": "<p>Confidential text</p>",
        "visibility": "public", "is_published": "true",
    }, follow_redirects=False)
    assert created.status_code == 303
    page = await db_session.scalar(select(Page).where(Page.slug == "secret-notes"))
    menu = await admin_client.post("/admin/settings/menu", data={
        "label": "Notes", "url": "/page/secret-notes", "location": "navbar", "is_active": "true",
    }, follow_redirects=False)
    assert menu.status_code == 302
    assert "/page/secret-notes" in (await client.get("/")).text

    changed = await admin_client.post(f"/admin/pages/{page.id}/edit", data={
        "title": "Secret notes", "slug": "secret-notes",
        "body_html": "<p>Confidential text</p>",
        "visibility": "private", "is_published": "true",
    }, follow_redirects=False)
    assert changed.status_code == 303
    visitor = await client.get("/page/secret-notes")
    assert visitor.status_code == 404
    assert "Confidential text" not in visitor.text
    assert visitor.headers["cache-control"] == "no-store"
    assert "/page/secret-notes" not in (await client.get("/")).text
    assert "/page/secret-notes" not in (await client.get("/sitemap.xml")).text
    admin_view = await admin_client.get("/page/secret-notes")
    assert admin_view.status_code == 200
    assert "Confidential text" in admin_view.text
    assert admin_view.headers["cache-control"].startswith("private, no-store")
    assert admin_view.headers["x-robots-tag"] == "noindex, nofollow, noarchive"
    assert admin_view.headers["referrer-policy"] == "no-referrer"
    assert "img-src 'self'" in admin_view.headers["content-security-policy"]
    rejected = await admin_client.post("/admin/settings/menu", data={
        "label": "Secret", "url": "/page/secret-notes", "location": "navbar", "is_active": "true",
    }, follow_redirects=False)
    assert rejected.status_code == 422


async def test_page_trash_restore_and_purge_are_admin_only(
    admin_client: AsyncClient, client: AsyncClient, db_session: AsyncSession,
):
    created = await admin_client.post("/admin/pages", data={
        "title": "Temporary", "body_html": "<p>Temporary body</p>",
        "visibility": "public", "is_published": "true",
    }, follow_redirects=False)
    assert created.status_code == 303
    page = await db_session.scalar(select(Page).where(Page.slug == "temporary"))
    page_id = page.id
    assert (await admin_client.post(f"/admin/pages/{page_id}/delete", headers={"X-CSRF-Token": "invalid"})).status_code == 403
    assert (await client.post(f"/admin/pages/{page_id}/delete", follow_redirects=False)).status_code in {302, 403}
    trashed = await admin_client.post(f"/admin/pages/{page_id}/delete", follow_redirects=False)
    assert trashed.status_code == 303
    assert (await client.get("/page/temporary")).status_code == 404
    assert "Temporary" in (await admin_client.get("/admin/pages/trash")).text
    restored = await admin_client.post(f"/admin/pages/{page_id}/restore", follow_redirects=False)
    assert restored.status_code == 303
    assert (await client.get("/page/temporary")).status_code == 404
    assert (await admin_client.get("/page/temporary")).status_code == 200
    await admin_client.post(f"/admin/pages/{page_id}/delete")
    purged = await admin_client.post(f"/admin/pages/{page_id}/purge", follow_redirects=False)
    assert purged.status_code == 303
    await db_session.rollback()
    db_session.expire_all()
    assert await db_session.get(Page, page_id) is None

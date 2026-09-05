import asyncio
import re

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, func

from app.main import app
from app.models import LoginAttempt


async def test_csrf_missing_and_wrong_token_rejected(admin_client):
    admin_client.headers.pop("X-CSRF-Token")
    missing = await admin_client.post("/admin/categories", data={"name": "Denied"})
    wrong = await admin_client.post("/admin/categories", data={"name": "Denied", "csrf_token": "wrong"})
    assert missing.status_code == wrong.status_code == 403


async def test_csrf_hidden_form_token_works(admin_client):
    token = admin_client.headers.pop("X-CSRF-Token")
    response = await admin_client.post("/admin/categories", data={"name": "Allowed", "csrf_token": token})
    assert response.status_code == 302


async def test_csrf_token_is_bound_to_session(admin_client):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as other:
        page = await other.get("/admin/login")
        other_token = re.search(r'name="csrf-token" content="([^"]+)"', page.text).group(1)
    response = await admin_client.post("/admin/categories", data={"name": "Denied"}, headers={"X-CSRF-Token": other_token})
    assert response.status_code == 403


async def test_json_reorder_requires_csrf(admin_client):
    token = admin_client.headers.pop("X-CSRF-Token")
    assert (await admin_client.post("/admin/settings/tags/reorder", json={"ids": []})).status_code == 403
    response = await admin_client.post("/admin/settings/tags/reorder", json={"ids": []}, headers={"X-CSRF-Token": token})
    assert response.status_code == 200


async def test_parallel_login_attempts_share_limit(client, db_session):
    responses = await asyncio.gather(*[
        client.post("/admin/login", data={"username": "incorrect", "password": "incorrect"}) for _ in range(6)
    ])
    assert sorted(r.status_code for r in responses) == [401] * 5 + [429]
    limited = next(r for r in responses if r.status_code == 429)
    assert 1 <= int(limited.headers["Retry-After"]) <= 900
    assert "giriş denemesi" in limited.text
    assert await db_session.scalar(select(func.count()).select_from(LoginAttempt)) == 5


async def test_logout_requires_post_and_csrf(admin_client):
    assert (await admin_client.get("/admin/logout")).status_code == 405
    response = await admin_client.post("/admin/logout")
    assert response.status_code == 302
    assert (await admin_client.get("/admin")).status_code == 302

"""Bounded hostile-input and concurrency checks using disposable site storage."""

import asyncio
import io
import statistics
import time

import pytest
from PIL import Image
from sqlalchemy import func, select, text

from app.config import settings
from app.models import Download, LoginAttempt, MediaAsset


@pytest.mark.parametrize("path", ["/panel/downloads", "/panel/downloads/trash", "/panel/pages", "/panel/audit", "/panel/links", "/panel/content-reports"])
async def test_oversized_page_number_is_rejected_without_server_error(admin_client, path):
    response = await admin_client.get(path, params={"page": "9" * 80})
    assert response.status_code == 422


@pytest.mark.parametrize("path", ["/panel/downloads/{id}/edit", "/panel/pages/{id}/edit", "/publisher/{id}", "/publisher/{id}/photo"])
async def test_oversized_record_id_is_rejected(admin_client, path):
    assert (await admin_client.get(path.format(id="9" * 80))).status_code == 422


@pytest.mark.parametrize("path,data", [
    ("/panel/users/{id}/role", {"role": "admin"}),
    ("/panel/categories/{id}/delete", {}),
    ("/panel/downloads/bulk", {"action": "publish", "download_ids": "9" * 80}),
    ("/panel/settings/tags/reorder", {"ids": [10 ** 80]}),
])
async def test_oversized_mutation_ids_do_not_reach_sqlite(admin_client, path, data):
    path = path.format(id="9" * 80)
    response = await admin_client.post(path, json=data) if "reorder" in path else await admin_client.post(path, data=data)
    assert response.status_code == 422


async def test_oversized_optional_category_filter_does_not_crash(admin_client):
    response = await admin_client.get("/panel/downloads", params={"category_id": "9" * 80})
    assert response.status_code == 200


async def test_oversized_optional_category_transfer_target_is_rejected(admin_client):
    response = await admin_client.post('/panel/categories/1/delete', data={'target_category_id': '9' * 80})
    assert response.status_code == 422


async def test_bounded_bruteforce_and_forwarded_spoofing_share_limit(client, db_session):
    limiter = asyncio.Semaphore(2)

    async def attempt(index):
        async with limiter:
            return await client.post("/login", data={"username": "admin' OR 1=1--", "password": "invalid-test-password"}, headers={"X-Forwarded-For": f"192.0.2.{index+1}"})

    async with asyncio.timeout(15):
        responses = await asyncio.gather(*(attempt(index) for index in range(12)))
    assert sorted(response.status_code for response in responses) == [401] * 5 + [429] * 7
    assert all(int(response.headers["retry-after"]) > 0 for response in responses if response.status_code == 429)
    assert await db_session.scalar(select(func.count()).select_from(LoginAttempt)) == 5


async def test_bounded_panel_read_load_preserves_database(admin_client, db_session):
    db_session.add_all([Download(title=f"Load fixture {index}", slug=f"load-fixture-{index}", external_url="https://example.com/app") for index in range(300)])
    await db_session.commit()
    paths = ("/panel", "/panel/downloads", "/panel/users", "/panel/notifications", "/panel/settings/general")
    limiter = asyncio.Semaphore(4)
    latencies = []
    started = time.perf_counter()

    async def request(index):
        async with limiter:
            before = time.perf_counter()
            response = await admin_client.get(paths[index % len(paths)])
            latencies.append(time.perf_counter() - before)
            assert response.status_code == 200
            assert response.headers["cache-control"] == "no-store"

    async with asyncio.timeout(30):
        await asyncio.gather(*(request(index) for index in range(180)))
    assert await db_session.scalar(select(func.count()).select_from(Download)) == 300
    assert await db_session.scalar(text("PRAGMA integrity_check")) == "ok"
    assert not (await db_session.execute(text("PRAGMA foreign_key_check"))).all()
    ordered = sorted(latencies)
    print(f"Panel load: requests=180 concurrency=4 elapsed={time.perf_counter()-started:.2f}s mean={statistics.mean(latencies)*1000:.1f}ms p95={ordered[int(len(ordered)*.95)-1]*1000:.1f}ms")


async def test_bounded_parallel_gallery_uploads_do_not_duplicate_or_lose_files(admin_client, db_session):
    limiter = asyncio.Semaphore(3)

    async def upload(index):
        buffer = io.BytesIO()
        Image.new("RGB", (48, 32), "red" if index % 2 else "blue").save(buffer, "PNG")
        async with limiter:
            response = await admin_client.post("/panel/upload/gallery-image", files={"file": ("same-name.png", buffer.getvalue(), "image/png")})
            assert response.status_code == 200
            return response.json()["path"]

    async with asyncio.timeout(20):
        paths = await asyncio.gather(*(upload(index) for index in range(18)))
    assert len(set(paths)) == 2
    assert await db_session.scalar(select(func.count()).select_from(MediaAsset)) == 2
    assert len(list((settings.upload_path / "gallery").iterdir())) == 2
    assert await db_session.scalar(text("PRAGMA integrity_check")) == "ok"

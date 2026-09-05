import socket

import httpx
import pytest
from sqlalchemy import select

from app import crud, link_checks
from app.models import LinkCheck
from app.schemas import DownloadCreate


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "192.168.1.2"])
async def test_private_network_destinations_are_blocked(monkeypatch, address):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 80))])
    result = await link_checks.check_link("http://example.com/file")
    assert result.status == "blocked"


@pytest.mark.parametrize("code,expected", [(200, "ok"), (404, "broken"), (410, "broken"), (403, "restricted"), (429, "restricted"), (500, "error")])
async def test_status_classification_and_dns_pinning(monkeypatch, code, expected):
    async def resolve(url):
        return "93.184.216.34"
    def handle(request):
        assert request.url.host == "93.184.216.34"
        assert request.headers["host"] == "example.com"
        assert request.extensions["sni_hostname"] == "example.com"
        return httpx.Response(code)
    client_class = httpx.AsyncClient
    monkeypatch.setattr(link_checks, "resolve_public_url", resolve)
    monkeypatch.setattr(link_checks.httpx, "AsyncClient", lambda **kw: client_class(transport=httpx.MockTransport(handle), **kw))
    assert (await link_checks.check_link("https://example.com/file")).status == expected


async def test_redirect_to_private_network_is_blocked(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, *a, **kw: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1" if host == "localhost" else "93.184.216.34", 80))])
    requests = []
    def handle(request):
        requests.append(request)
        return httpx.Response(302, headers={"location": "http://localhost/secret"})
    client_class = httpx.AsyncClient
    monkeypatch.setattr(link_checks.httpx, "AsyncClient", lambda **kw: client_class(transport=httpx.MockTransport(handle), **kw))
    assert (await link_checks.check_link("https://example.com")).status == "blocked"
    assert len(requests) == 1


async def test_head_fallback_does_not_consume_download(monkeypatch):
    class NeverRead(httpx.AsyncByteStream):
        async def __aiter__(self):
            raise AssertionError("File body must not be downloaded")
            yield b""
    async def resolve(url):
        return "93.184.216.34"
    methods = []
    def handle(request):
        methods.append(request.method)
        return httpx.Response(405 if request.method == "HEAD" else 200, stream=NeverRead())
    client_class = httpx.AsyncClient
    monkeypatch.setattr(link_checks, "resolve_public_url", resolve)
    monkeypatch.setattr(link_checks.httpx, "AsyncClient", lambda **kw: client_class(transport=httpx.MockTransport(handle), **kw))
    assert (await link_checks.check_link("https://example.com")).status == "ok"
    assert methods == ["HEAD", "GET"]


async def test_report_saves_results_and_hides_stale_checks(admin_client, db_session, monkeypatch):
    from app.routers import reports
    from app.schemas import DownloadUpdate
    download = await crud.create_download(db_session, DownloadCreate(title="Broken link", external_url="https://example.com/old"))
    async def check(url):
        return link_checks.LinkResult(status="broken", http_status=404, message="Bulunamadı")
    monkeypatch.setattr(reports, "check_link", check)
    assert (await admin_client.post(f"/admin/links/{download.id}/check")).status_code == 303
    result = await db_session.get(LinkCheck, download.id)
    assert result.http_status == 404
    page = await admin_client.get("/admin/links?state=broken")
    assert "Broken link" in page.text
    await crud.update_download(db_session, download, DownloadUpdate(external_url="https://example.com/new"))
    page = await admin_client.get("/admin/links?state=unchecked")
    assert "Broken link" in page.text

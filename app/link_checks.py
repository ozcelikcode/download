"""Dış indirme bağlantılarını dosyayı indirmeden ve özel ağlara erişmeden kontrol eder."""

import ipaddress
import logging
import socket
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin

import anyio
import httpx
from pydantic import BaseModel
from sqlalchemy import literal, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models import Download, FileType, LinkCheck

logger = logging.getLogger(__name__)
_click_checks_in_flight: set[int] = set()
CLICK_CHECK_INTERVAL = timedelta(hours=1)
MAX_CLICK_CHECKS = 4


class LinkResult(BaseModel):
    status: str
    http_status: int | None = None
    message: str


async def save_link_result(
    session: AsyncSession, download_id: int, url: str,
    result: LinkResult, started_at: datetime,
) -> None:
    """Silinen/değiştirilen bağlantıyı ve daha yeni kontrolü atomik olarak koru."""
    values = {"url": url, **result.model_dump(), "checked_at": datetime.now(timezone.utc)}
    source = select(literal(download_id), *(literal(value) for value in values.values())).where(
        select(Download.id).where(
            Download.id == download_id, Download.external_url == url,
            Download.file_type == FileType.external,
            Download.deleted_at.is_(None),
        ).exists()
    )
    statement = insert(LinkCheck).from_select(["download_id", *values], source)
    await session.execute(statement.on_conflict_do_update(
        index_elements=[LinkCheck.download_id], set_=values,
        where=LinkCheck.checked_at <= started_at,
    ))


async def check_clicked_link(download_id: int, url: str) -> None:
    """Yönlendirme gönderildikten sonra sınırlı, tekrarsız kontrol çalıştır."""
    if download_id in _click_checks_in_flight or len(_click_checks_in_flight) >= MAX_CLICK_CHECKS:
        return
    _click_checks_in_flight.add(download_id)
    try:
        started_at = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as session:
            current = await session.scalar(select(Download.external_url).where(
                Download.id == download_id, Download.file_type == FileType.external,
                Download.is_active.is_(True), Download.is_draft.is_(False), Download.deleted_at.is_(None),
            ))
            if current != url:
                return
            previous = await session.get(LinkCheck, download_id)
            if previous and previous.url == url:
                checked_at = previous.checked_at.replace(tzinfo=timezone.utc)
                if started_at - checked_at < CLICK_CHECK_INTERVAL:
                    return
        result = await check_link(url)
        async with AsyncSessionLocal() as session:
            await save_link_result(session, download_id, url, result, started_at)
            await session.commit()
    except Exception:
        logger.exception("Link check after click failed: download_id=%d", download_id)
    finally:
        _click_checks_in_flight.discard(download_id)


async def resolve_public_url(url: httpx.URL) -> str:
    if url.scheme not in {"http", "https"} or not url.host or url.userinfo or url.port not in {None, 80, 443}:
        raise ValueError("Yalnızca standart HTTP/HTTPS adresleri kontrol edilebilir.")
    with anyio.fail_after(5):
        addresses = await anyio.to_thread.run_sync(
            lambda: socket.getaddrinfo(url.host, url.port or (443 if url.scheme == "https" else 80), type=socket.SOCK_STREAM),
            abandon_on_cancel=True,
        )
    ips = list(dict.fromkeys(item[4][0] for item in addresses))
    if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
        raise ValueError("Yerel veya özel ağ adreslerine erişim engellendi.")
    return ips[0]


async def check_link(url: str) -> LinkResult:
    try:
        current = httpx.URL(url)
        visited: set[str] = set()
        with anyio.fail_after(20):
            # Her hedef için ayrı bağlantı: SNI/Host değerleri başka alan
            # adına ait bir havuz bağlantısıyla karışmaz. Ortam proxy'leri kullanılmaz.
            for _ in range(6):
                if str(current) in visited:
                    return LinkResult(status="error", message="Yönlendirme döngüsü tespit edildi.")
                visited.add(str(current))
                ip = await resolve_public_url(current)
                pinned = current.copy_with(host=ip)
                headers = {"Host": current.netloc.decode("ascii"), "User-Agent": "DownloadSite-LinkCheck/1.0"}
                async with httpx.AsyncClient(timeout=5, follow_redirects=False, trust_env=False) as client:
                    for method in ("HEAD", "GET"):
                        async with client.stream(method, pinned, headers=headers, extensions={"sni_hostname": current.host}) as response:
                            code = response.status_code
                            location = response.headers.get("location")
                        if code not in {405, 501} or method == "GET":
                            break
                if code in {301, 302, 303, 307, 308}:
                    if not location:
                        return LinkResult(status="error", http_status=code, message="Yönlendirme adresi eksik.")
                    current = httpx.URL(urljoin(str(current), location))
                    continue
                if 200 <= code < 300:
                    return LinkResult(status="ok", http_status=code, message="Bağlantı erişilebilir.")
                if code in {401, 403, 429}:
                    return LinkResult(status="restricted", http_status=code, message="Hedef erişimi sınırlıyor; bağlantı tarayıcıda çalışabilir.")
                if code in {404, 410}:
                    return LinkResult(status="broken", http_status=code, message="Hedef dosya veya sayfa bulunamadı.")
                return LinkResult(status="error", http_status=code, message="Hedef beklenmeyen bir yanıt verdi.")
            return LinkResult(status="error", message="Çok fazla yönlendirme.")
    except (ValueError, httpx.InvalidURL):
        return LinkResult(status="blocked", message="Adres geçersiz veya özel ağa erişim engellendi.")
    except (TimeoutError, httpx.TimeoutException):
        return LinkResult(status="error", message="Bağlantı kontrolü zaman aşımına uğradı.")
    except (OSError, httpx.HTTPError):
        return LinkResult(status="error", message="DNS, TLS veya bağlantı hatası; daha sonra tekrar deneyin.")

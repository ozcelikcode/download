"""Dış indirme bağlantılarını dosyayı indirmeden ve özel ağlara erişmeden kontrol eder."""

import ipaddress
import socket
from urllib.parse import urljoin

import anyio
import httpx
from pydantic import BaseModel


class LinkResult(BaseModel):
    status: str
    http_status: int | None = None
    message: str


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

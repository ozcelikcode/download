"""Canonical, robots ve sitemap için ortak site adresi doğrulaması."""

from __future__ import annotations

import ipaddress
from typing import Literal
from urllib.parse import urlsplit

from app.config import settings

PublicUrlStatus = Literal["ok", "info", "warning", "error"]


def inspect_public_base_url() -> tuple[str | None, PublicUrlStatus, str]:
    """APP_BASE_URL değerini doğrula ve canlı ortam uygunluğunu sınıflandır."""
    raw_value = settings.app_base_url.strip()
    try:
        parsed = urlsplit(raw_value)
        host = parsed.hostname
        port = parsed.port
    except ValueError:
        return None, "error", "base_url_invalid"

    if (
        parsed.scheme not in {"http", "https"}
        or not host
        or not parsed.netloc
        or any(character.isspace() or ord(character) < 32 for character in raw_value)
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
        or (port is not None and not 1 <= port <= 65535)
    ):
        return None, "error", "base_url_invalid"

    normalized_host = host.lower().rstrip(".")
    local_host = (
        normalized_host in {"localhost", "test"}
        or "." not in normalized_host
        or normalized_host.endswith((".localhost", ".local", ".test"))
    )
    try:
        local_host = local_host or not ipaddress.ip_address(normalized_host).is_global
    except ValueError:
        pass

    base_url = raw_value.rstrip("/")
    if local_host:
        return base_url, "info", "base_url_development"
    if parsed.scheme != "https":
        return base_url, "warning", "base_url_http"
    return base_url, "ok", "base_url_https"

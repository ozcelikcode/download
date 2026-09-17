"""Zengin metin ve kullanıcı tarafından yönetilen URL'ler için güvenlik sınırları."""

from __future__ import annotations

from html import unescape
from html.parser import HTMLParser
from urllib.parse import urlsplit

import nh3


_RICH_TEXT_TAGS = {
    "a", "b", "blockquote", "br", "code", "div", "em", "h1", "h2", "h3",
    "i", "img", "li", "ol", "p", "pre", "s", "span", "strike", "strong",
    "sub", "sup", "u", "ul",
}
_BLOCK_CLASSES = {
    "ql-align-center", "ql-align-justify", "ql-align-right", "ql-direction-rtl",
    *(f"ql-indent-{index}" for index in range(1, 9)),
}
_INLINE_CLASSES = {"ql-size-small", "ql-size-large", "ql-size-huge"}


def _filter_attribute(tag: str, attribute: str, value: str) -> str | None:
    if tag == "a" and attribute == "target":
        return "_blank" if value == "_blank" else None
    return value


_RICH_TEXT_CLEANER = nh3.Cleaner(
    tags=_RICH_TEXT_TAGS,
    clean_content_tags={"embed", "iframe", "math", "object", "script", "style", "svg", "template"},
    attributes={
        "a": {"href", "target", "title"},
        "img": {"alt", "height", "src", "title", "width"},
        "span": {"style"},
    },
    allowed_classes={
        "blockquote": _BLOCK_CLASSES,
        "div": _BLOCK_CLASSES | {"ql-code-block", "ql-code-block-container"},
        "h1": _BLOCK_CLASSES,
        "h2": _BLOCK_CLASSES,
        "h3": _BLOCK_CLASSES,
        "li": _BLOCK_CLASSES,
        "p": _BLOCK_CLASSES,
        "span": _INLINE_CLASSES,
    },
    filter_style_properties={"background-color", "color"},
    url_schemes={"http", "https", "mailto"},
    url_relative="pass_through",
    attribute_filter=_filter_attribute,
    link_rel="noopener noreferrer",
)


def sanitize_rich_text(value: str | None) -> str | None:
    """Quill çıktısını güvenli bir HTML alt kümesine indirger."""
    if value is None:
        return None
    cleaned = _RICH_TEXT_CLEANER.clean(str(value).strip()).strip()
    return cleaned or None


class _PlainTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if text := data.strip():
            self.parts.append(text)


def rich_text_to_plain_text(value: str | None) -> str:
    """Temizlenmiş zengin metni kartlar ve SEO alanları için düz metne çevirir."""
    cleaned = sanitize_rich_text(value)
    if not cleaned:
        return ""
    parser = _PlainTextExtractor()
    parser.feed(cleaned)
    return unescape(" ".join(parser.parts))


def _reject_unsafe_url_characters(value: str) -> None:
    if "\\" in value or any(character.isspace() or ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError("Adres boşluk, ters eğik çizgi veya kontrol karakteri içeremez.")


def normalize_http_url(value: str | None) -> str | None:
    """Yalnız kullanıcı bilgisi içermeyen tam HTTP/HTTPS adreslerini kabul eder."""
    if value is None or not str(value).strip():
        return None
    normalized = str(value).strip()
    _reject_unsafe_url_characters(normalized)
    parsed = urlsplit(normalized)
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Geçersiz port numarası.") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Yalnızca tam HTTP/HTTPS adresleri kullanılabilir.")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Adres içinde kullanıcı bilgisi kullanılamaz.")
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("Geçersiz port numarası.")
    return normalized


def normalize_navigation_url(value: str) -> str:
    """Menüler için güvenli yerel yol, fragment veya HTTP/HTTPS adresi döndürür."""
    normalized = str(value).strip()
    if not normalized:
        raise ValueError("Menü adresi boş olamaz.")
    _reject_unsafe_url_characters(normalized)
    if normalized.startswith("/") and not normalized.startswith("//"):
        return normalized
    if normalized.startswith("#") and len(normalized) > 1:
        return normalized
    if normalized.startswith("?") and len(normalized) > 1:
        return normalized
    http_url = normalize_http_url(normalized)
    if http_url is None:
        raise ValueError("Geçersiz menü adresi.")
    return http_url


def safe_http_url(value: str | None) -> str:
    """Eski/veritabanından gelen güvensiz bir URL'yi şablonda etkisizleştirir."""
    try:
        return normalize_http_url(value) or ""
    except ValueError:
        return ""


def safe_navigation_url(value: str | None) -> str:
    """Eski/veritabanından gelen güvensiz bir menü URL'sini etkisizleştirir."""
    try:
        return normalize_navigation_url(value or "")
    except ValueError:
        return "#"

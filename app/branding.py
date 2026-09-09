"""
Site kimliği yardımcıları — ikon rengi paleti.

Site artık önceden derlenmiş statik bir Tailwind CSS dosyası kullandığından
(bkz. tailwind.config.js content taraması), admin panelinden seçilen rengi
doğrudan bir Tailwind class'ı olarak üretemeyiz (derleme zamanında bilinmiyor).
Bunun yerine sabit bir palet tanımlayıp, seçilen rengin açık/koyu tema hex
değerlerini CSS custom property olarak inline stille veriyoruz
(bkz. app.css'teki `.site-icon-color` kuralı).
"""

from __future__ import annotations

# key → (açık tema hex, koyu tema hex) — Tailwind'in 600/400 tonlarına karşılık gelir.
SITE_ICON_COLORS: dict[str, tuple[str, str]] = {
    "blue": ("#2563eb", "#60a5fa"),
    "green": ("#16a34a", "#4ade80"),
    "red": ("#dc2626", "#f87171"),
    "amber": ("#d97706", "#fbbf24"),
    "purple": ("#9333ea", "#c084fc"),
    "pink": ("#db2777", "#f472b6"),
    "teal": ("#0d9488", "#2dd4bf"),
    "slate": ("#475569", "#94a3b8"),
    "yellow": ("#a16207", "#facc15"),
    "cream": ("#92400e", "#fde68a"),
    "amoled": ("#52525b", "#c4c4ca"),
}

# key → açık vurgu, koyu vurgu, açık yüzey, koyu yüzey, açık kenarlık, koyu kenarlık
ACCENT_THEMES: dict[str, tuple[str, str, str, str, str, str]] = {
    "blue": ("#356fd4", "#72a7e8", "#eaf2fc", "#152033", "#b8d0ee", "#36577f"),
    "green": ("#247a4d", "#66c58b", "#edf8f1", "#14271c", "#b9ddc7", "#365f45"),
    "red": ("#bf4f58", "#e68188", "#fcedee", "#2b181a", "#e7bec1", "#734247"),
    "yellow": ("#9a6a0c", "#dfbd60", "#fbf6e8", "#292313", "#e6d49b", "#6d5b2f"),
    "cream": ("#8a6735", "#d8bd8b", "#faf5e9", "#282218", "#dfcfad", "#66573c"),
    "amoled": ("#52525b", "#c4c4ca", "#f4f4f5", "#000000", "#d4d4d8", "#3f3f46"),
}

DEFAULT_ICON_COLOR = "blue"


def resolve_icon_color(color_key: str) -> tuple[str, str]:
    """Verilen renk anahtarının (açık, koyu) hex çiftini döndürür; bilinmiyorsa varsayılana düşer."""
    return SITE_ICON_COLORS.get(color_key, SITE_ICON_COLORS[DEFAULT_ICON_COLOR])


def resolve_accent_theme(theme_key: str) -> tuple[str, str, str, str, str, str]:
    return ACCENT_THEMES.get(theme_key, ACCENT_THEMES[DEFAULT_ICON_COLOR])

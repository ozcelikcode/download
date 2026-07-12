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
}

DEFAULT_ICON_COLOR = "blue"


def resolve_icon_color(color_key: str) -> tuple[str, str]:
    """Verilen renk anahtarının (açık, koyu) hex çiftini döndürür; bilinmiyorsa varsayılana düşer."""
    return SITE_ICON_COLORS.get(color_key, SITE_ICON_COLORS[DEFAULT_ICON_COLOR])

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
    "amoled": ("#111827", "#e5e7eb"),
}

# key → açık vurgu, koyu vurgu, açık yüzey, koyu yüzey, açık kenarlık, koyu kenarlık
ACCENT_THEMES: dict[str, tuple[str, str, str, str, str, str]] = {
    "blue": ("#2563eb", "#60a5fa", "#eff6ff", "#172554", "#bfdbfe", "#1d4ed8"),
    "green": ("#15803d", "#4ade80", "#f0fdf4", "#052e16", "#bbf7d0", "#166534"),
    "red": ("#dc2626", "#f87171", "#fef2f2", "#450a0a", "#fecaca", "#991b1b"),
    "yellow": ("#a16207", "#facc15", "#fefce8", "#422006", "#fde68a", "#854d0e"),
    "cream": ("#92400e", "#fde68a", "#fffbeb", "#29200d", "#fde68a", "#78350f"),
    "amoled": ("#111827", "#e5e7eb", "#f3f4f6", "#000000", "#9ca3af", "#374151"),
}

DEFAULT_ICON_COLOR = "blue"


def resolve_icon_color(color_key: str) -> tuple[str, str]:
    """Verilen renk anahtarının (açık, koyu) hex çiftini döndürür; bilinmiyorsa varsayılana düşer."""
    return SITE_ICON_COLORS.get(color_key, SITE_ICON_COLORS[DEFAULT_ICON_COLOR])


def resolve_accent_theme(theme_key: str) -> tuple[str, str, str, str, str, str]:
    return ACCENT_THEMES.get(theme_key, ACCENT_THEMES[DEFAULT_ICON_COLOR])

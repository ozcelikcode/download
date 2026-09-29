"""Content seeded once during installation or a full site reset."""

from __future__ import annotations

import json


REQUIRED_CATEGORY_NAMES = {
    "en": "General",
    "es": "General",
    "fr": "Général",
    "tr": "Genel",
}

HERO_TEXT = {
    "en": ("Download Center", "Safe and Free Software", "Find the software you need and download it in one click.", "Search for software, tools, or categories…"),
    "es": ("Centro de descargas", "Software seguro y gratuito", "Encuentra el software que necesitas y descárgalo con un solo clic.", "Busca software, herramientas o categorías…"),
    "fr": ("Centre de téléchargement", "Logiciels sûrs et gratuits", "Trouvez le logiciel dont vous avez besoin et téléchargez-le en un clic.", "Rechercher des logiciels, des outils ou des catégories…"),
    "tr": ("İndirme Merkezi", "Güvenli ve Ücretsiz Yazılımlar", "Aradığınız yazılımı bulun, tek tıkla indirin.", "Yazılım, araç veya kategori ara…"),
}
def default_hero_components(language: str = "en") -> str:
    """Store one chosen language; later UI changes must not rewrite seeded content."""
    eyebrow, title, description, search = HERO_TEXT.get(language, HERO_TEXT["en"])
    return json.dumps([
        {"type": "eyebrow", "text": eyebrow},
        {"type": "title", "text": title},
        {"type": "description", "text": description},
        {"type": "search", "text": search},
        {"type": "stats", "text": ""},
    ], ensure_ascii=False)

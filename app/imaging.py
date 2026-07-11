"""
Görsel işleme yardımcıları — otomatik sıkıştırma ve kare ikon kırpma.

Pillow ile senkron çalışır (CPU-bound, tek bir görsel için milisaniyeler
sürer). Sunucuya yüklenen her ikon görseli, site şişmesin diye burada
sıkıştırılır; "İkon Olarak Ayarla" eylemi de kare kırpmayı burada yapar.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

MAX_DIMENSION = 1600
JPEG_QUALITY = 82
WEBP_QUALITY = 82

# Pillow tarafından açılamayan (ör. HEIC, SVG) formatlara dokunulmaz.
_SKIP_SUFFIXES = {".svg"}


def compress_image_file(path: Path, max_dimension: int = MAX_DIMENSION) -> None:
    """
    Görseli yerinde sıkıştırır: gerekiyorsa büyük kenarı `max_dimension`'a
    küçültür, formatına uygun kalite/optimize ayarıyla yeniden kaydeder.
    Şeffaflık korunur. Desteklenmeyen/bozuk dosyalarda sessizce vazgeçer.
    """
    if path.suffix.lower() in _SKIP_SUFFIXES:
        return

    try:
        with Image.open(path) as img:
            img = ImageOps.exif_transpose(img)  # telefon fotoğraflarının rotasyonunu düzelt

            if img.width > max_dimension or img.height > max_dimension:
                img.thumbnail((max_dimension, max_dimension), Image.LANCZOS)

            fmt = (img.format or "").upper()
            suffix = path.suffix.lower()

            if fmt in ("JPEG", "JPG") or suffix in (".jpg", ".jpeg"):
                if img.mode in ("RGBA", "P", "LA"):
                    img = img.convert("RGB")
            elif fmt == "WEBP" or suffix == ".webp":
                pass
            else:
                # PNG, GIF, BMP, ICO vb. → optimize edilmiş PNG
                if img.mode not in ("RGBA", "RGB", "P", "L"):
                    img = img.convert("RGBA")
            img.load()  # kaynak dosyadan bağımsız, tam belleğe alınmış hale getir

        # `with` bloğu burada kapanır (kaynak dosya handle'ı serbest); ancak
        # yerinde (aynı yola) yazılacağı için kaydetme işlemi handle kapandıktan
        # sonra yapılır.
        if fmt in ("JPEG", "JPG") or suffix in (".jpg", ".jpeg"):
            img.save(path, format="JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
        elif fmt == "WEBP" or suffix == ".webp":
            img.save(path, format="WEBP", quality=WEBP_QUALITY, method=6)
        else:
            img.save(path, format="PNG", optimize=True)

        after = path.stat().st_size
        logger.info("Görsel sıkıştırıldı: %s (%.1f KB)", path.name, after / 1024)
    except Exception as exc:
        logger.warning("Görsel sıkıştırılamadı (%s): %s", path, exc)


def make_square_icon(src_path: Path, dest_path: Path, size: int = 256) -> None:
    """
    Görseli ortadan kare olacak şekilde kırpar, verilen boyuta küçültür ve
    dest_path'e optimize edilmiş PNG olarak kaydeder (şeffaflık korunur).
    `dest_path`, `src_path` ile aynı olabilir (yerinde güncelleme / link
    değişmez) — kaynak dosya handle'ı kaydetmeden önce kapatılır.
    """
    with Image.open(src_path) as img:
        img = ImageOps.exif_transpose(img)
        if img.mode not in ("RGBA", "RGB", "L"):
            img = img.convert("RGBA")

        width, height = img.size
        side = min(width, height)
        left = (width - side) // 2
        top = (height - side) // 2
        img = img.crop((left, top, left + side, top + side))
        img = img.resize((size, size), Image.LANCZOS)
        img.load()

    # `with` bloğu kapandı (kaynak handle serbest) — artık aynı yola güvenle yazabiliriz.
    img.save(dest_path, format="PNG", optimize=True)
    logger.info("Otomatik ikon oluşturuldu: %s (%dx%d)", dest_path.name, size, size)

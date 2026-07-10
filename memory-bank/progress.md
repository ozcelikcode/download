# Progress

## What works
- **Veritabanı şeması**: Category, Tag, Download (self-ref sürüm geçmişi), DownloadTag (M2M), DownloadLog — tamamlanmış, 2 alembic migration uygulanmış.
- **Public routes** (`app/routers/public.py`): anasayfa, kategori filtreleme, arama, etiket filtreleme, detay sayfası, indirme tetikleyici (`/dl/{slug}`).
- **Admin routes** (`app/routers/admin.py`): login/logout, dashboard, dosya ekle/düzenle/sil, kategori CRUD, etiket CRUD.
- **Auth**: bcrypt + imzalı session cookie tabanlı admin girişi çalışıyor.
- **Rate limiting altyapısı**: `DownloadLog` + indeks mevcut, saatlik limit config'den okunuyor.
- **Hata sayfaları**: 404/429/500 için özel Jinja2 template + handler.
- **Computed alanlar**: `file_size_human`, `source_domain` model üzerinde.
- **Admin panelinde os_compatibility / icon_image_path / icon_image_url** alanları (ikinci migration ile) eklenmiş — uygulama ikonu ve OS uyumluluğu gösterimi.

## What's left / unknown (kod incelemesinden görülemeyen)
- Test suite var mı belirsiz — repo kökünde `tests/` klasörü görünmüyor, doğrulanmalı.
- CSRF koruması prompt.txt'de hedef olarak belirtilmiş; `dependencies.py`/`main.py` içinde açık bir CSRF middleware/token mekanizması görülmedi — kontrol edilmesi gerekebilir.
- SEO (dinamik meta etiketleri) template'lerde ne kadar uygulanmış, doğrulanmadı.

## Current status
Proje fonksiyonel bir MVP durumunda görünüyor: tüm ana route'lar, admin paneli ve DB şeması mevcut. `download.db` dosyası repoda commit edilmiş (gerçek/test verisi olabilir).

## Known issues
- Admin varsayılan şifresi (`admin123`) prod'da değiştirilmediyse güvenlik riski (README'de uyarılmış).
- `.env` içindeki `APP_SECRET_KEY` varsayılan/placeholder ise session imzalama zayıf olur.
- `download.db-wal` boyutu 0 ama `-shm` dosyası var — WAL checkpoint durumu kontrol edilebilir, önemli değilse temizlenebilir.

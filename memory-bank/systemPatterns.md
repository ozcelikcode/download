# System Patterns

## Architecture

- Katmanlı FastAPI monolith: `routers`, `crud`, `models`, `schemas`, `templates` ayrımı korunur.
- Rotalar ve SQLAlchemy işlemleri asenkrondur; DB sorguları mümkün olduğunca `app/crud.py` içinde tutulur.
- Router ayrımı: `public.py`, `admin.py`, rapor/denetim için `reports.py`.
- Pydantic v2 giriş doğrulaması ve SQLAlchemy async session kullanılır.

## Data and storage

- SQLite + Alembic; model değişiklikleri migration gerektirir.
- Yerel indirilebilir dosyalar `app/static` dışında özel depoda tutulur ve yalnız kontrollü rotalardan sunulur.
- Public görseller `app/static/uploads`, indirme paketleri `storage/downloads` altında tutulur.
- Sayfalama her zaman `?page=x` query parametresiyle yapılır.

## Security and observability

- CSRF koruması, imzalı admin oturumu, giriş/indirme rate limit'i ve güvenlik başlıkları aktiftir.
- Zengin metin `nh3` ile temizlenir; dış ve navigasyon URL'leri izin verilen şemalarla sınırlandırılır.
- Yüklemeler boyut ve gerçek içerik türü bakımından doğrulanır; yazma işlemleri geçici dosya üzerinden atomik yapılır.
- Admin değişiklikleri `AuditLog`, dış bağlantı sonuçları `LinkCheck` ile izlenir.
- Dashboard dosya sistemi kontrolleri `app/health.py` içinde, bloklayan tarama işi threadpool'da çalışır.
- Admin Site Sağlığı teknik ve SEO bulgularını `app/health.py` içinde üretir; rapor şemaları `app/schemas.py` ile tiplenir. İlk kayıt örnekleri sınırlı sayıda gösterilir ve güvenli admin hedeflerine bağlanır.
- Ana sayfa SEO varsayılanları `SiteSettings` içinde nullable `seo_home_title` / `seo_meta_description` alanlarında tutulur ve `app/routers/admin.py` üzerinden Pydantic v2 ile doğrulanır. Boş değerler yerelleştirilmiş varsayılanlara döner; bu alan değişikliği Alembic migration gerektirir.
- Sağlık bulguları düzeltme bağlantısı ve gerektiğinde öneri anahtarı taşır; teknik yapılandırma kontrolleri de çözüm adımı sunabilir. Kritik/uyarı özeti kullanıcıya görünür, form sonucu ortak admin toast'ı ile bildirilir.
- `app/seo.py`, canonical, sitemap ve robots için `APP_BASE_URL` değerini tek noktada doğrular. Sitemap'e yalnız aktif yayınlar ile kullanılan kategori/etiket sayfaları eklenir; arama/filtre varyantları `noindex` durumundadır.

## UI patterns

- Jinja2 + Tailwind; yalnız `rounded-sm`, ölçülü gölge ve minimum JavaScript.
- Public ve admin için ayrı base template vardır; tema, erişilebilirlik ve toast JavaScript'i ortaktır.
- Tema açık/koyu/sistem seçeneklerini ve merkezi vurgu rengini destekler.
- Ortak toast API'si `window.AppToast`; kısa başarılı/uyarı/hata/bilgi geri bildirimleri içindir. İlerleme göstergeleri ve onay dialogları ayrı kalır.

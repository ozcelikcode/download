# Progress

## Working system

- Public indirme kataloğu, kategori/etiket/arama, filtreleme, detay, ilgili içerik ve güvenli indirme akışı.
- Async FastAPI + SQLAlchemy, SQLite ve Alembic migration düzeni.
- Admin içerik/kategori/etiket/menü/medya/ayar yönetimi, taslaklar ve toplu işlemler.
- TR/EN arayüz, açık/koyu/sistem teması ve yönetilebilir marka/hero görünümü.
- CSRF, oturum güvenliği, giriş ve indirme rate limit'i, audit log, bağlantı denetimi ve özel dosya deposu.
- HTML/URL sanitizasyonu, güvenli görsel yükleme ve depo sınırı kontrolleri.
- Özel 404/429/500 sayfaları ve güvenlik başlıkları.
- Erişilebilir ortak UI davranışları ve ortak toast bildirim sistemi.
- Admin içerik tablosu sıralaması, etkin filtre etiketleri ve mobil kart sunumu.
- Admin sağlık merkezi: kırık bağlantı, eksik yerel dosya, kullanılmayan medya, taslak, kategorisiz içerik ve depo kullanımı.
- Admin Site Sağlığı ekranı: kritik teknik bulgular, içerik/SEO önerileri, canonical, sitemap, robots ve `APP_BASE_URL` uygunluğu; örnek kayıtlar admin düzenleme ekranlarına bağlanır.
- Arama ve filtre sayfaları `noindex,follow` kullanır; canonical URL'ler filtre parametrelerini taşımaz. İndirme detayında kısa açıklama meta açıklamasında önceliklidir.
- Dinamik `sitemap.xml` yalnız aktif yayınları ve kullanılan kategori/etiket sayfalarını içerir; `robots.txt` sitemap'i tanıtır ve admin/indirme uçlarını dışarıda tutar.
- Ana sayfanın SEO başlığı ve meta açıklaması artık Genel Ayarlar'dan düzenlenebilir; özel başlık `<title>`/Open Graph'ta, açıklama meta ve Open Graph alanlarında gösterilir. Boş ayarlar mevcut yerelleştirilmiş varsayılanlara döner.
- Site Sağlığı ana sayfa metaverisi eksikliği ve uzun metinler için açıklamalı öneriler/doğrudan ayar bağlantısı verir; APP_BASE_URL hatalarında yapılandırma düzeltmesini açıklar, kritik/uyarı bulgularını sayfa üstü erişilebilir bildirimde özetler.
- SEO ayarları için uzunluk doğrulaması ve başarı/hata toast'ları eklendi. Yeni nullable sütunlar Alembic migration ile eklenir; var olan kayıtların davranışı değişmez.

## Remaining UI roadmap

- Gelişmiş toplu kategori/etiket/işletim sistemi işlemleri.
- İsteğe bağlı ekran görüntüsü galerisi, sistem gereksinimleri, lisans, mimari ve değişiklik günlüğü alanları.

## Verification

Tam test paketi her orta ölçekli parçadan sonra çalıştırılır. Ana sayfa manuel SEO ayarları ve sağlık önerileri sonrası tam paket: **193 geçti**; `pip check`, Python derleme kontrolü, Alembic head ve boş SQLite veritabanına tam migration zinciri yükseltme kontrolü, ayrıca `git diff --check` temiz.

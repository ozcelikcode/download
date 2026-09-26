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

## Remaining UI roadmap

- Gelişmiş toplu kategori/etiket/işletim sistemi işlemleri.
- İsteğe bağlı ekran görüntüsü galerisi, sistem gereksinimleri, lisans, mimari ve değişiklik günlüğü alanları.

## Verification

Tam test paketi her orta ölçekli parçadan sonra çalıştırılır. Site Sağlığı/SEO çalışması sonrası tam paket: **188 geçti**; `pip check` ve `git diff --check` temiz.

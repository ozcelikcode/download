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
- Admin sağlık merkezi: kırık bağlantı, eksik yerel dosya, kullanılmayan medya, taslak, kategorisiz içerik ve depo kullanımı.

## Remaining UI roadmap

- Admin içerik tablosu sıralama ve mobil görünüm iyileştirmeleri.
- Gelişmiş toplu kategori/etiket/işletim sistemi işlemleri.
- İsteğe bağlı ekran görüntüsü galerisi, sistem gereksinimleri, lisans, mimari ve değişiklik günlüğü alanları.

## Verification

Tam test paketi her orta ölçekli parçadan sonra çalıştırılır. Güncel test sayısı teslim notunda belirtilmelidir.

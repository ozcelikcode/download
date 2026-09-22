# Product Context

## Why this project exists
Kullanıcıların bir uygulama/dosya için "indirme sayfası" arayışında karşılaştığı reklam dolu, karmaşık indirme sitelerinin (adfly benzeri) yerine geçecek; sahibinin kendi dosyalarını (lokal upload) veya başka kaynaklara (dış link, örn. GitHub) yönlendiren linkleri tek, temiz bir arayüzde sunmasını sağlar.

## Problems it solves
- Dağınık indirme linklerini tek bir kategorize edilmiş sitede toplamak.
- Sürüm geçmişini (changelog benzeri) kullanıcıya şeffaf göstermek.
- Kaynak şeffaflığı: dış linkse hangi domainden geldiğini (örn. `github.com`) açıkça belirtmek.
- Basit spam/kötüye kullanım önleme (rate limiting) — karmaşık auth olmadan.

## How it should work
- Ziyaretçi anasayfada arama + kategori/etiket filtreleriyle dosya bulur.
- Detay sayfasında: boyut, sürüm, açıklama, ikon, kaynak domain, breadcrumb (`Anasayfa > Kategori > Dosya`), eski sürümler listesi.
- `/dl/{slug}` indirmeyi tetikler, sayaç artar, log/rate-limit kaydı düşer.
- Admin `/admin/login` ile giriş yapar, `/admin` panelinden dosya/kategori/etiket yönetir.

## UX goals
- "Tıkla ve indir" — az tıklamayla hedefe ulaşmak, gereksiz adım yok.
- Minimal, yönetilebilir vurgu renkleri; açık/koyu/sistem temalarında tutarlı görünüm.
- Responsive içerik + kategori/etiket sidebar düzeni; küçük ekranlarda tek sütuna düşer.
- Sade hero alanı, abartısız karşılama.

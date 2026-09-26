# Active Context

## Current focus

Projenin güvenlik ve temel backend sağlamlaştırması tamamlandı. Çalışma şu anda UI kullanılabilirliği ve içerik keşfi geliştirmelerinde.

## Recently completed

- Ortak erişilebilirlik davranışları: skip link, focus-visible, dialog focus trap, Escape ile kapatma, `aria-expanded`, reduced-motion ve dokunmatik işlem görünürlüğü.
- Public listeleme: query-param tabanlı sıralama, işletim sistemi, kaynak türü ve kaynak güveni filtreleri.
- Detay sayfası: ilgili içerikler, güçlendirilmiş indirme kartı, mobil CTA ve SHA-256 kopyalama.
- Admin dashboard: sağlık merkezi ve son işlem akışı.
- Ortak toast sistemi: public/admin layout, sunucu flash mesajları ve kopyalama geri bildirimleri.
- Admin içerik listesi: yeni/popüler/alfabetik sıralama, kaldırılabilir etkin filtre etiketleri ve mobil kart görünümü; mobil seçimler var olan toplu işlem formuna bağlanır.
- Admin etiket sayfasındaki döngü değişkeni çeviri yardımcısını gölgeleyip dolu listede 500 üretiyordu; değişken ayrıştırıldı ve regresyon testi eklendi.
- Etiket ve kategori ekleme/düzenleme/silme işlemleri sağ üstte ortak başarı toast'ı gösterir; yinelenen/geçersiz adlar hata toast'ı verir. Medya arşivinde işlem sonrası yenileme toast'ı kaybettiriyordu; sonuç artık yenileme boyunca korunup listede gösterilir.
- Yeni indirme taslaklarında kısmi/geçersiz URL otomatik kaydedilir; yalnız `Yayınla` taslağı aktif olarak kesinleştirir ve HTTP/HTTPS doğrulamasını uygular. `Uygulamayı kaydet` taslağı kaydeder, kullanıcıyı düzenleme ekranında tutar.
- Dosya boyutu alanında birim seçicisi sabit genişlikte `MB/KB/GB/B` seçeneklerini gösterir; dar yüzde genişliğinden kaynaklanan taşma giderildi.
- Admin'e ayrı **Site Sağlığı** ekranı eklendi: teknik sorunlar, SEO içerik önerileri ve canonical/sitemap/robots/site-adresi kontrolleri tek yerde gruplanır; ilk kayıtlar doğrudan düzenleme ekranına bağlanır.
- `/sitemap.xml` yayınlanmış içerikleri ve kullanılan kategori/etiket sayfalarını listeler; `/robots.txt` admin ve indirme uçlarını dışarıda tutar. Arama/filtre varyantları `noindex` olur, canonical adresleri gereksiz filtre parametrelerini taşımaz.
- İndirme detaylarında kısa açıklama varsa arama meta açıklaması olarak kullanılır. Site adresi tek yardımcıda doğrulanır; geçersiz değer sitemap/canonical üretimini bozmaz.

## Next UI work

1. Yeni Site Sağlığı ekranını canlı ortam verisiyle gözden geçirip önerilen bulguların uygunluğunu doğrulamak.
2. Ancak ihtiyaç kesinleşirse migration gerektiren ekran görüntüsü galerisi ve zengin içerik alanları.

## Operational note

`.venv` daha önce bulunmayan Python 3.13 yoluna bağlıydı; Git'ten çıkarıldı ve geliştirme ortamı Python 3.12 ile yeniden kurularak Git dışında tutuldu. `make dev` reload izlemesi yalnızca `app/` ile sınırlı. Test/önbellek çıktıları ve derleme sonrası Tailwind CLI temiz tutulur; uygulamanın servis ettiği derlenmiş CSS korunur. Eski yüklemeleri özel depoya taşıyan başlangıç göçü `.gitkeep` işaret dosyasını atlar. CSS derleme aracı gerektiğinde `make tailwind-cli` ile yeniden indirilir.

# Active Context

## Current focus

Projenin güvenlik ve temel backend sağlamlaştırması tamamlandı. Site Sağlığı/SEO bölümü; bulguları açıklayıp öneri sunacak ve ana sayfa SEO metinlerinin admin'den yönetilmesini sağlayacak şekilde genişletildi.

## Recently completed

- Sunucu anahtarıyla korunan ilk kurulum (`/setup`), alan adı/HTTPS/debug/depolama kontrolleri ve tarayıcıdan yönetici hesabı oluşturma eklendi. `make setup` yeni .env üretir; `make setup-key` yeniden kurulum anahtarını yeniler. Mevcut siteler Alembic geçişinde kurulu kalır.
- Ayarlar → Bakım ve Sıfırlama: ayarlar / tüm site / hesabı kaldırıp kuruluma dönme kapsamları. Parola + beş dakikalık oturuma bağlı onay + birebir site adı gerekir. Yenileme kuşağı tüm eski yönetici oturumlarını public/admin tarafında geçersiz kılar.
- Tam silme yalnız özel veri dizinlerini temizler; kod/.env/hosting korunur. Kesilen temizlik kalıcı bakım durumunda yeniden başlatmayla sürer. Tek worker OS kilidiyle zorunludur; sıfırlama aktif istekleri ve arka plan görsel indirmelerini bekler.
- Güvenlik bakımı: hesap parolası doğrulamasına kota ve threadpool, istek gövdesine akış dahil sınır, SQLite secure_delete ve eski dosya taşımasında symlink hedef koruması. Bildirimli bağımlılıklar güncellendi; kurulum/yayın/sıfırlama sınırları README ve SECURITY içinde belgeli.
- Doğrulama: 227 test geçti; bağımlılık taramasında bilinen açık ve pip uyumsuzluğu bulunmadı. Kurulum ve bakım ekranları izole sunucuda tarayıcıyla kontrol edildi. Mevcut DB migration'ı veri korunarak uygulandı; migration öncesi yedek proje dışında saklandı.

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
- Genel Ayarlar'a ana sayfa SEO başlığı ve meta açıklaması eklendi; değerler ana sayfanın `<title>`, meta description ve Open Graph açıklamasında kullanılır. Alanlar boşsa dil bazlı geçerli varsayılanlar korunur.
- Site Sağlığı, eksik/uzun ana sayfa SEO metinlerini hata gibi göstermeden öneri olarak sınıflandırır; APP_BASE_URL yapılandırma hataları için çözüm adımı verir, ilgili ayar bağlantısını ve kritik/uyarı bulguları için görünür bir uyarı özeti sunar.
- SEO formu karakter sınırlarını sunucuda doğrular; başarılı/kötü sonuçlar ortak toast ile bildirilir. İki nullable alanı ekleyen geriye uyumlu Alembic migration eklendi.

## Next UI work

- Dil kontrolü: bağlantı raporu ve Site Sağlığı'ndaki geçmiş sistem açıklamaları görüntüleme sırasında TR/EN çevrilir; kullanıcı içerikleri korunur. Medya türü/sayfa boyutu filtreleri ve kayıt/yükleme hata mesajları ortak dil ayarını kullanır.
- Detay ekranında uyumluluk, kaynak, sürüm ve sayaç gibi bilgiler Dosya Bilgileri bölümünde toplandı; ana indirme alanındaki tekrarlar kaldırıldı, mobil işlem düğmesi korundu.

1. Site Sağlığı ekranını canlı ortam verisiyle gözden geçirip gerçek bulguların ve SEO önerilerinin uygunluğunu doğrulamak.
2. Ancak ihtiyaç kesinleşirse migration gerektiren ekran görüntüsü galerisi ve zengin içerik alanları.

## Operational note

`.venv` daha önce bulunmayan Python 3.13 yoluna bağlıydı; Git'ten çıkarıldı ve geliştirme ortamı Python 3.12 ile yeniden kurularak Git dışında tutuldu. `make dev` reload izlemesi yalnızca `app/` ile sınırlı. Test/önbellek çıktıları ve derleme sonrası Tailwind CLI temiz tutulur; uygulamanın servis ettiği derlenmiş CSS korunur. Eski yüklemeleri özel depoya taşıyan başlangıç göçü `.gitkeep` işaret dosyasını atlar. CSS derleme aracı gerektiğinde `make tailwind-cli` ile yeniden indirilir.

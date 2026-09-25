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
- Yeni indirme taslaklarında kısmi/geçersiz URL otomatik kaydedilir; yayınlama sırasında HTTP/HTTPS doğrulaması korunur.

## Next UI work

1. Sağlık merkezi kartlarının eksik dosya/kullanılmayan medya için tam filtrelenmiş hedeflere bağlanması.
2. Ancak ihtiyaç kesinleşirse migration gerektiren ekran görüntüsü galerisi ve zengin içerik alanları.

## Operational note

`.venv` yanlışlıkla Git'e eklenmiş ve artık bulunmayan Python 3.13 yoluna bağlıydı; Git'ten çıkarıldı. Yerel geliştirme ortamı Python 3.12 ile yeniden kuruldu ve Git dışında tutuluyor. `make dev` reload izlemesi yalnızca `app/` ile sınırlı. Test/önbellek çıktıları ile indirilen Tailwind CLI temizlendi; test kaynakları ve uygulamanın servis ettiği derlenmiş CSS korundu. Eski yüklemeleri özel depoya taşıyan başlangıç göçü `.gitkeep` işaret dosyasını atlar. CSS derleme aracı gerektiğinde `make tailwind-cli` ile yeniden indirilir.

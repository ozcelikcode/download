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

## Next UI work

1. Sağlık merkezi kartlarının eksik dosya/kullanılmayan medya için tam filtrelenmiş hedeflere bağlanması.
2. Ancak ihtiyaç kesinleşirse migration gerektiren ekran görüntüsü galerisi ve zengin içerik alanları.

## Operational note

Repo içindeki `.venv`, artık bulunmayan bir Python 3.13 yoluna bağlı. Testler geçici Python 3.12 ortamında çalıştırılıyor; yerel geliştirme ortamı yeniden oluşturulmalı.

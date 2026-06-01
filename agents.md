# Agent Görev ve Kuralları

Bu proje, FastAPI ve Tailwind CSS kullanılarak geliştirilen minimal bir indirme sitesidir. AI asistanı olarak aşağıdaki kurallara kesinlikle uymalısın.

## 1. Kodlama Standartları
- **Dil:** Backend için modern Python (3.12+), tip belirteçleri (Type Hints) ve Pydantic v2 zorunludur.
- **Asenkron Yapı:** FastAPI rotaları ve veritabanı sorguları (SQLAlchemy) asenkron (`async def`, `await`) olarak yazılmalıdır.
- **Modülerlik:** Kodları tek bir `main.py` dosyasına yığmak yerine `routers`, `models`, `schemas`, `templates` klasörlerine böl.
- **Tasarım Dili:** Tailwind CSS sınıflarında sadece `rounded-sm` kullan. Abartılı gölgelerden (shadow-2xl vb.) kaçın, minimalizmi koru.

## 2. Çalışma Prensibi (Pacing)
- Görevleri "Orta Ölçekli Parçalar" (Medium Chunks) halinde ele al.
- "Her şeyi tek seferde yapma" ve "Satır satır onay bekleme" mantığının tam ortasını bul.
- Tamamlanmış çalışan bir parça sunmadan diğer özelliğe geçme (Örn: Veritabanı bitmeden UI'a geçme).
- Değişiklik yapmadan önce dosyanın mevcut durumunu analiz et.

## 3. Mimari Kurallar
- **Veritabanı:** SQLite. migration işlemleri için Alembic kullanılacak.
- **Frontend:** Jinja2 kullanılacak. JavaScript minimum düzeyde, sadece gerekli olduğunda (örn: mobil menü aç/kapat, admin paneli silme onayı) kullanılacak.
- **İkonlar:** Lucide Icons SVG veya CDN üzerinden entegre edilecek.
- **Sayfalandırma:** Dinamik içerikler her zaman `?page=x` query parametresi ile çalışacak. Path parametresi (`/page/2`) KULLANILMAYACAK.

## 4. Hata Yönetimi ve Loglama
- Son kullanıcıya dönen hatalar (404, 500) için özel Jinja2 şablonları oluştur.
- Backend tarafındaki hatalar net açıklamalarla loglanmalı. Python `logging` modülünü aktif kullan.

## 5. İletişim Tonu
- Yanıtlarında doğrudan ol, gereksiz nezaket ifadelerinden (özür dilemek, uzun giriş cümleleri) kaçın.
- Sadece yapılan teknik değişikliği ve sıradaki adımı açıkla.
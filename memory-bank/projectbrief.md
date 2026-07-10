# Project Brief

**Download Sitesi** — minimal, "tıkla ve indir" mantığıyla çalışan bir FastAPI indirme (download) sitesi.

## Core Requirements
- Kullanıcı yormayan, yalın ve güvenilir bir dosya/uygulama indirme portalı.
- İki indirme türü: sunucuda barınan **lokal dosya** veya **dış link** (URL).
- Kategori + etiket (tag) tabanlı organizasyon, sidebar'da arama ve anlık sayım.
- Sürüm geçmişi: aynı uygulamanın eski sürümleri parent-child ilişkisiyle bağlı.
- İndirme sayacı + IP başına saatlik rate limiting.
- Şifre korumalı, yalın bir admin paneli (dosya/kategori/etiket CRUD).
- Dark mode YOK — sadece açık, minimal mavi tonlarında bir tasarım.

## Scope Source
Kaynak talimatlar [prompt.txt](../prompt.txt) ve [agents.md](../agents.md) dosyalarında; bu ikisi projenin orijinal "brief"idir ve değişmemesi beklenir.

## Out of Scope
- Kullanıcı kayıt/girişi (yalnızca tek admin hesabı var).
- Path-parametre tabanlı sayfalama (`/page/2`) — sadece `?page=x` kullanılacak.
- Abartılı gölge/animasyon içeren UI (minimalizm zorunlu, `rounded-sm` dışında köşe yuvarlama yok).

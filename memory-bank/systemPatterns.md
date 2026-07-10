# System Patterns

## Architecture
Klasik katmanlı FastAPI monolith — `app/` altında modüler ayrım:

```
app/
├── main.py         # App factory, lifespan, middleware, exception handlers
├── config.py       # pydantic-settings tabanlı .env okuyucu (singleton `settings`)
├── database.py     # Async SQLAlchemy engine/session, Base, get_db
├── models.py       # ORM modelleri (Category, Tag, Download, DownloadTag, DownloadLog)
├── schemas.py      # Pydantic v2 şemaları
├── crud.py         # Tüm async DB işlemleri (routerlar doğrudan SQLAlchemy yazmaz)
├── dependencies.py # get_db re-export, get_request_ip, require_admin, session imzalama
├── templating.py   # Jinja2Templates instance + custom filtreler
├── routers/
│   ├── public.py   # Herkese açık: /, /category/{slug}, /search, /tag/{slug}, /download/{slug}, /dl/{slug}
│   └── admin.py    # Admin: /admin/login, /admin, /admin/downloads/*, /admin/categories, /admin/tags
├── templates/      # Jinja2 (base.html + admin/base_admin.html iki ayrı layout)
└── static/         # css/app.css, uploads/
```

## Key technical decisions
- **Async her yerde**: FastAPI route'ları ve SQLAlchemy sorguları `async def`/`await`.
- **CRUD katmanı zorunlu**: DB erişimi router'larda değil `crud.py` içinde — router ince kalır.
- **Self-referencing Download**: `parent_id` ile sürüm geçmişi (`versions` / `parent` relationship'leri, `Download.models.py:157-199`).
- **Session tabanlı admin auth**: `itsdangerous.URLSafeTimedSerializer` ile imzalı cookie (`admin_session`), bcrypt şifre karşılaştırma — JWT/OAuth yok, kasıtlı olarak minimal.
- **Rate limiting**: `DownloadLog` tablosu + `ix_download_logs_ip_time` indeksiyle IP+zaman sorgusu; saatlik limit `settings.rate_limit_downloads_per_hour`.
- **Sayfalama**: her zaman query param (`?page=x`), path parametresi asla kullanılmaz (agents.md kuralı).
- **Computed properties model üzerinde**: `file_size_human`, `source_domain` gibi türetilmiş alanlar `Download` modelinde property olarak tanımlı, DB'de saklanmaz.
- **Migration**: Alembic — model değişikliği sonrası mutlaka migration üretilir (`make migration msg="..."`).

## Component relationships
- `Category` 1—N `Download` (SET NULL on delete).
- `Tag` M2M `Download` (junction: `DownloadTag`, CASCADE on delete).
- `Download` 1—N `Download` (self-ref, `parent_id`, SET NULL on delete) — sürüm geçmişi.
- `Download` 1—N `DownloadLog` (CASCADE on delete) — indirme logu/rate limit.

## Design/UI patterns
- Tailwind: sadece `rounded-sm`, gölge kullanımı minimal.
- İki farklı base template: `templates/base.html` (public) ve `templates/admin/base_admin.html` (admin panel).
- Hata sayfaları özel: `errors/404.html`, `errors/429.html`, `errors/500.html` — `main.py` içindeki exception handler'lar bunları render eder ve sidebar context'ini boş geçer.

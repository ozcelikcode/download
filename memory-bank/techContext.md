# Tech Context

## Stack

- Python 3.12+, FastAPI, Pydantic v2
- Async SQLAlchemy + aiosqlite, SQLite, Alembic
- Jinja2, Tailwind CSS, Lucide Icons
- Küçük vanilla JavaScript modülleri: tema, erişilebilirlik, CSRF ve toast
- pytest + pytest-asyncio

## Main paths

- `app/routers/`: public, admin ve rapor rotaları
- `app/health.py` ve `app/seo.py`: admin sağlık denetimleri ile ortak SEO adres doğrulaması
- `app/models.py` / `app/routers/admin.py`: SiteSettings üzerinden admin tarafından yönetilen ana sayfa SEO başlığı ve meta açıklaması
- `app/templates/`: public/admin Jinja şablonları
- `app/static/css/app.css`: ortak bileşen stilleri
- `app/static/js/`: ortak tarayıcı davranışları
- `storage/downloads`: public statik kökün dışındaki özel indirme deposu
- `tests/`: izole geçici SQLite ve yükleme dizinleri kullanan testler

## Development commands

```bash
make install
make migrate
make dev
make css
pytest -q
```

Model değişikliğinde Alembic migration üretilmeli. Python/JS sözdizimi, `pip check`, tam test paketi ve `git diff --check` teslim öncesi çalıştırılmalı.

Ana sayfa SEO alanları `site_settings.seo_home_title` ve `site_settings.seo_meta_description` nullable sütunlarıdır; giriş uzunlukları sırasıyla 100 ve 320 karakterle sınırlanır. Sağlık ekranındaki 60/160 karakter kontrolleri yaklaşık editoryal eşiklerdir, sabit arama motoru sınırı olarak sunulmaz ve hata değil bilgi önerisi sayılır.

## Environment note

`.venv` daha önce bozuk Python 3.13 symlink'i içeriyordu; Python 3.12 ile yeniden oluşturuldu. Bu turda testler `.venv/bin/pytest` ile çalıştırıldı.

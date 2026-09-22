# Tech Context

## Stack

- Python 3.12+, FastAPI, Pydantic v2
- Async SQLAlchemy + aiosqlite, SQLite, Alembic
- Jinja2, Tailwind CSS, Lucide Icons
- Küçük vanilla JavaScript modülleri: tema, erişilebilirlik, CSRF ve toast
- pytest + pytest-asyncio

## Main paths

- `app/routers/`: public, admin ve rapor rotaları
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

## Environment note

Mevcut `.venv` bozuk Python 3.13 symlink'i içeriyor. Python 3.12 ile yeniden oluşturulmadan doğrudan kullanılamaz.

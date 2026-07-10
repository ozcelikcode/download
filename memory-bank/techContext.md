# Tech Context

## Stack
- **Backend**: Python 3.12+, FastAPI, type hints zorunlu.
- **ORM**: SQLAlchemy (async), `aiosqlite` driver.
- **Veritabanı**: SQLite (`download.db`, dosya kökünde) — WAL modu aktif (`download.db-shm`/`-wal` dosyaları mevcut).
- **Migration**: Alembic (`alembic/`, `alembic.ini`).
- **Şema doğrulama**: Pydantic v2 (`app/schemas.py`).
- **Şablon motoru**: Jinja2 (`app/templating.py`).
- **CSS**: Tailwind CSS (custom stiller `app/static/css/app.css`).
- **İkonlar**: Lucide Icons (SVG/CDN).
- **Auth**: bcrypt (şifre hash) + itsdangerous (imzalı session cookie) — harici auth kütüphanesi yok.
- **Session middleware**: Starlette `SessionMiddleware` (`app/main.py`).

## Development setup
```bash
make install   # venv + pip install -r requirements.txt
make migrate   # alembic upgrade head
make dev       # uvicorn --reload → http://127.0.0.1:8000
make prod      # 2 worker, 0.0.0.0:8000
make hash pw=x # bcrypt hash üret (admin şifresi için)
make migration msg="..."  # yeni alembic revizyonu
make freeze    # requirements.txt güncelle
```

## Config (.env)
`app/config.py` → `pydantic-settings` ile okunur, `get_settings()` `lru_cache`'li singleton.

| Değişken | Varsayılan | Not |
|---|---|---|
| `app_secret_key` | `change-me-in-production` | Session imzalama, prod'da mutlaka değiştir |
| `app_base_url` | `http://localhost:8000` | |
| `admin_username` | `admin` | |
| `admin_password_hash` | `""` | Boşsa/`placeholder` içeriyorsa admin girişi tamamen devre dışı kalır |
| `upload_dir` | `app/static/uploads` | Startup'ta otomatik oluşturulur |
| `max_upload_size_mb` | `500` | |
| `database_url` | `sqlite+aiosqlite:///./download.db` | |
| `rate_limit_downloads_per_hour` | `10` | |

## Constraints
- Path parametresi ile sayfalama YASAK — sadece `?page=x`.
- Dark mode desteklenmeyecek.
- JavaScript minimum düzeyde tutulacak (sadece mobil menü, silme onayı gibi yerlerde).
- OpenAPI/docs endpoint'leri kapalı (`docs_url=None, redoc_url=None, openapi_url=None`) — bilinçli tercih, prod'da API keşfi engellenmiş.

## Dependencies
Tam liste `requirements.txt` içinde; ana olanlar: fastapi, uvicorn, sqlalchemy, aiosqlite, alembic, pydantic-settings, jinja2, bcrypt, itsdangerous, python-multipart (upload için muhtemelen).

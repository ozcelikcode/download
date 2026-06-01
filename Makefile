.PHONY: dev migrate seed install hash

# Geliştirme sunucusu (hot-reload)
dev:
	.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# Prodüksiyon sunucusu
prod:
	.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2

# Veritabanı migrasyonu
migrate:
	.venv/bin/alembic upgrade head

# Yeni migrasyon oluştur
migration:
	.venv/bin/alembic revision --autogenerate -m "$(msg)"

# Bağımlılıkları kur
install:
	python3 -m venv .venv
	.venv/bin/pip install -U pip
	.venv/bin/pip install -r requirements.txt

# requirements.txt güncelle
freeze:
	.venv/bin/pip freeze > requirements.txt

# Admin şifre hash'i üret
# Kullanım: make hash pw=yenisifre
hash:
	.venv/bin/python3 -c "import bcrypt; h=bcrypt.hashpw(b'$(pw)', bcrypt.gensalt(12)).decode(); print(h)"

.PHONY: dev migrate seed install install-dev hash test tailwind-cli css css-watch

TAILWIND_VERSION := 3.4.19
TAILWIND_BIN := .bin/tailwindcss

UNAME_S := $(shell uname -s)
UNAME_M := $(shell uname -m)
ifeq ($(UNAME_S),Darwin)
  ifeq ($(UNAME_M),arm64)
    TAILWIND_PLATFORM := macos-arm64
  else
    TAILWIND_PLATFORM := macos-x64
  endif
else
  ifeq ($(UNAME_M),aarch64)
    TAILWIND_PLATFORM := linux-arm64
  else
    TAILWIND_PLATFORM := linux-x64
  endif
endif

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

# Bağımlılıkları kur (+ Tailwind CLI indir ve CSS'i derle)
install:
	python3 -m venv .venv
	.venv/bin/pip install -U pip
	.venv/bin/pip install -r requirements.txt
	$(MAKE) tailwind-cli
	$(MAKE) css

# Tailwind'in bağımsız CLI'ını indirir (Node/npm gerekmez)
tailwind-cli:
	mkdir -p .bin
	curl -sL -o $(TAILWIND_BIN) "https://github.com/tailwindlabs/tailwindcss/releases/download/v$(TAILWIND_VERSION)/tailwindcss-$(TAILWIND_PLATFORM)"
	chmod +x $(TAILWIND_BIN)

# Tailwind CSS'i tek seferlik derler — şablonlarda class değişikliğinden sonra çalıştırın
css:
	$(TAILWIND_BIN) -i app/static/css/tailwind_source.css -o app/static/css/tailwind.css --minify

# Şablon değişikliklerini izleyerek Tailwind CSS'i otomatik yeniden derler (geliştirme sırasında)
css-watch:
	$(TAILWIND_BIN) -i app/static/css/tailwind_source.css -o app/static/css/tailwind.css --watch

# Test bağımlılıkları dahil kur (geliştirme ortamı)
install-dev:
	python3 -m venv .venv
	.venv/bin/pip install -U pip
	.venv/bin/pip install -r requirements-dev.txt

# requirements.txt güncelle
freeze:
	.venv/bin/pip freeze > requirements.txt

# Test paketini çalıştır (tests/ — izole, geçici SQLite; download.db'ye dokunmaz)
test:
	.venv/bin/pytest -v

# Admin şifre hash'i üret
# Kullanım: make hash pw=yenisifre
hash:
	.venv/bin/python3 -c "import bcrypt; h=bcrypt.hashpw(b'$(pw)', bcrypt.gensalt(12)).decode(); print(h)"

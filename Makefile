.PHONY: dev prod migrate install install-dev hash test tailwind-cli css css-watch check-python setup setup-key

PYTHON ?= python3
SITE_URL ?= http://127.0.0.1:8000

# First-time setup never overwrites an existing .env file.
setup:
	.venv/bin/python -m app.manage prepare --url "$(SITE_URL)"
	$(MAKE) migrate

setup-key:
	.venv/bin/python -m app.manage setup-key

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

# Development server with hot reload.
dev:
	.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir app --no-access-log --log-config app/logging.json --no-use-colors

# Use one worker for SQLite and in-memory upload progress.
prod:
	.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 --no-access-log --log-config app/logging.json --no-use-colors

# Apply database migrations.
migrate:
	.venv/bin/alembic upgrade head

# Generate a new migration.
migration:
	.venv/bin/alembic revision --autogenerate -m "$(msg)"

# Install dependencies, download the Tailwind CLI, and build CSS.
check-python:
	@$(PYTHON) -c "import sys; assert sys.version_info >= (3, 12), 'Python 3.12+ required'; print(f'Python {sys.version.split()[0]} verified')"

install: check-python
	$(PYTHON) -m venv .venv
	.venv/bin/pip install -U pip
	.venv/bin/pip install -r requirements.txt
	$(MAKE) tailwind-cli
	$(MAKE) css

# Download the standalone Tailwind CLI (no Node/npm required).
tailwind-cli:
	mkdir -p .bin
	curl -sL -o $(TAILWIND_BIN) "https://github.com/tailwindlabs/tailwindcss/releases/download/v$(TAILWIND_VERSION)/tailwindcss-$(TAILWIND_PLATFORM)"
	chmod +x $(TAILWIND_BIN)

# Build Tailwind CSS once after changing classes in templates.
css:
	$(TAILWIND_BIN) -i app/static/css/tailwind_source.css -o app/static/css/tailwind.css --minify

# Watch templates and rebuild Tailwind CSS during development.
css-watch:
	$(TAILWIND_BIN) -i app/static/css/tailwind_source.css -o app/static/css/tailwind.css --watch

# Install development and test dependencies.
install-dev: check-python
	$(PYTHON) -m venv .venv
	.venv/bin/pip install -U pip
	.venv/bin/pip install -r requirements-dev.txt

# Update requirements.txt.
freeze:
	.venv/bin/pip freeze > requirements.txt

# Run tests with isolated temporary SQLite databases; download.db is untouched.
test:
	.venv/bin/pytest -v

# Generate an administrator password hash; the terminal prompts privately.
hash:
	.venv/bin/python3 -c "from getpass import getpass; from app.dependencies import hash_admin_password; print(hash_admin_password(getpass('New password: ')))"

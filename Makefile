PYTHON ?= backend/.venv/bin/python
PIP ?= backend/.venv/bin/pip
NPM ?= npm
COMPOSE ?= docker compose
FRONTEND_ROOT ?= /var/www/pcep/frontend
BACKUP_ROOT ?= /home/micu/backups/pcep

.PHONY: help install install-backend install-frontend test test-backend test-frontend audit audit-backend audit-frontend build build-frontend fetch-pyodide django-check compose-up compose-build seed-reset deploy-frontend status

help:
	@printf '%s\n' \
		'Targets:' \
		'  install          Install backend dev deps and frontend deps' \
		'  test             Run backend and frontend checks' \
		'  audit            Run Python/npm dependency audits and question audit' \
		'  build            Build the frontend production bundle' \
		'  django-check     Run Django production deploy checks' \
		'  compose-build    Rebuild Docker services' \
		'  compose-up       Start db + backend' \
		'  seed-reset       Reset and seed production DB in backend container' \
		'  deploy-frontend  Backup and publish frontend/dist to FRONTEND_ROOT' \
		'  status           Show git and docker compose status'

install: install-backend install-frontend

install-backend:
	cd backend && ../$(PIP) install -r requirements-dev.txt

install-frontend:
	cd frontend && $(NPM) ci

test: test-backend test-frontend

test-backend:
	cd backend && ../$(PYTHON) -m pytest -q

test-frontend:
	cd frontend && $(NPM) run lint && $(NPM) run format:check && $(NPM) run build

audit: audit-backend audit-frontend

audit-backend:
	cd backend && DJANGO_SETTINGS_MODULE=pcep_project.test_settings ../$(PYTHON) manage.py audit_questions --fail-on-warnings
	cd backend && ../$(PYTHON) -m pip_audit -r requirements.txt
	cd backend && ../$(PYTHON) -m pip_audit -r requirements-dev.txt

audit-frontend:
	cd frontend && $(NPM) audit --audit-level=moderate

build: build-frontend

build-frontend: fetch-pyodide
	cd frontend && $(NPM) run build

# Self-hosted Python runtime for the in-browser code runner (git-ignored, ~12 MB).
# Fetched only when missing so repeat builds stay fast.
fetch-pyodide:
	cd frontend && [ -d public/pyodide ] || $(NPM) run fetch-pyodide

django-check:
	cd backend && DJANGO_SETTINGS_MODULE=pcep_project.settings DJANGO_DEBUG=False DJANGO_SECRET_KEY=a-sufficiently-long-production-secret-key-for-local-check DJANGO_ALLOWED_HOSTS=pcep.micutu.com POSTGRES_DB=pcep_db POSTGRES_USER=pcep_user POSTGRES_PASSWORD=dummy POSTGRES_HOST=localhost POSTGRES_PORT=5432 ../$(PYTHON) manage.py check --deploy --fail-level WARNING

compose-build:
	$(COMPOSE) build

compose-up:
	$(COMPOSE) up -d

seed-reset:
	$(COMPOSE) exec backend python manage.py audit_questions --fail-on-warnings
	$(COMPOSE) exec backend python manage.py seed_questions --reset

deploy-frontend: build-frontend
	@stamp=$$(date +%Y%m%d-%H%M%S); \
	mkdir -p "$(BACKUP_ROOT)"; \
	if [ -d "$(FRONTEND_ROOT)" ]; then cp -a "$(FRONTEND_ROOT)" "$(FRONTEND_ROOT).bak.$$stamp"; fi; \
	rm -rf "$(FRONTEND_ROOT)"/*; \
	cp -a frontend/dist/. "$(FRONTEND_ROOT)"/; \
	printf 'Published frontend to %s\n' "$(FRONTEND_ROOT)"

status:
	git status --short --branch
	$(COMPOSE) ps

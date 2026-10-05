PYTHON ?= backend/.venv/bin/python
PIP ?= backend/.venv/bin/pip
LOCK_COMPILER ?= backend/.venv/bin/pip-compile
PYTHON_BIN := $(if $(findstring /,$(PYTHON)),$(abspath $(PYTHON)),$(PYTHON))
PIP_BIN := $(if $(findstring /,$(PIP)),$(abspath $(PIP)),$(PIP))
LOCK_COMPILER_BIN := $(if $(findstring /,$(LOCK_COMPILER)),$(abspath $(LOCK_COMPILER)),$(LOCK_COMPILER))
NPM ?= npm
COMPOSE ?= docker compose
FRONTEND_ROOT ?= /var/www/pcep/frontend
BACKUP_ROOT ?= /home/micu/backups/pcep
DATABASE_BACKUP_ROOT ?= $(BACKUP_ROOT)/daily
DATABASE_BACKUP_KEEP ?= 30
RELEASE_KEEP ?= 5
ASSET_RETENTION_DAYS ?= 7
RELEASE ?= $(shell git describe --always --dirty --abbrev=12 --match '__pcep_no_matching_tag__' 2>/dev/null || printf development)
BACKEND_DEPLOY_FLAGS ?=
TRIVY_IMAGE ?= ghcr.io/aquasecurity/trivy:0.75.0@sha256:af6acf9a6b85dfe389a1941505c0ce9efef52a4719635e1a962f022a3d855daa
TRIVY_CACHE ?= /tmp/pcep-trivy-cache
BACKEND_IMAGE ?= pcep_webapp-backend:latest
PRODUCTION_URL ?= https://pcep.micutu.com

.PHONY: help install install-backend install-frontend lock-backend test test-backend test-frontend audit audit-backend audit-frontend audit-secrets audit-image audit-db-image build build-frontend compose-build-frontend fetch-pyodide django-check production-smoke compose-up compose-build deploy-backend backup-database seed-reset deploy-frontend release-retention status

help:
	@printf '%s\n' \
		'Targets:' \
		'  install          Install backend dev deps and frontend deps' \
		'  lock-backend     Regenerate hashed Python dependency locks' \
		'  test             Run backend and frontend checks' \
		'  audit            Run dependency, question and tracked-secret audits' \
		'  audit-secrets    Scan tracked files and complete Git history for secrets' \
		'  audit-image      Fail on fixable high/critical backend image CVEs' \
		'  audit-db-image   Fail on fixable high/critical PostgreSQL image CVEs' \
		'  build            Build the frontend production bundle' \
		'  compose-build-frontend Build frontend through the pinned container' \
		'  django-check     Run Django production deploy checks' \
		'  production-smoke Check the read-only public production contract' \
		'  compose-build    Rebuild the backend image with its release revision' \
		'  deploy-backend   Backup, validate and deploy one backend release' \
		'  backup-database  Create and retain a verified daily-style DB backup' \
		'  compose-up       Start db + backend' \
		'  seed-reset       Reset and seed production DB in backend container' \
		'  deploy-frontend  Backup and publish frontend/dist to FRONTEND_ROOT' \
		'  release-retention Preview old release snapshots; never deletes' \
		'  status           Show git and docker compose status'

install: install-backend install-frontend

install-backend:
	"$(PIP_BIN)" install --require-hashes --only-binary=:all: -r backend/requirements-dev.lock

lock-backend:
	CUSTOM_COMPILE_COMMAND="make lock-backend" "$(LOCK_COMPILER_BIN)" --quiet --allow-unsafe --generate-hashes --resolver=backtracking --strip-extras --output-file backend/requirements.lock backend/requirements.txt
	CUSTOM_COMPILE_COMMAND="make lock-backend" "$(LOCK_COMPILER_BIN)" --quiet --allow-unsafe --generate-hashes --resolver=backtracking --strip-extras --output-file backend/requirements-dev.lock backend/requirements-dev.txt

install-frontend:
	cd frontend && $(NPM) ci

test: test-backend test-frontend

test-backend:
	cd backend && "$(PYTHON_BIN)" -m pytest -q

test-frontend: fetch-pyodide
	cd frontend && $(NPM) run test && $(NPM) run lint && $(NPM) run format:check && VITE_PCEP_RELEASE="$(RELEASE)" $(NPM) run build

audit: audit-backend audit-frontend audit-secrets

audit-backend:
	cd backend && DJANGO_SETTINGS_MODULE=pcep_project.test_settings "$(PYTHON_BIN)" manage.py audit_questions --fail-on-warnings
	cd backend && "$(PYTHON_BIN)" -m pip_audit -r requirements.lock
	cd backend && "$(PYTHON_BIN)" -m pip_audit -r requirements-dev.lock

audit-frontend:
	cd frontend && $(NPM) audit --audit-level=moderate
	cd frontend && $(NPM) audit signatures

audit-secrets:
	TRIVY_IMAGE="$(TRIVY_IMAGE)" bash scripts/check_tracked_secrets.sh

audit-image:
	mkdir -p "$(TRIVY_CACHE)"
	docker run --rm \
		-v /var/run/docker.sock:/var/run/docker.sock \
		-v "$(TRIVY_CACHE):/root/.cache/" \
		"$(TRIVY_IMAGE)" image --scanners vuln --severity HIGH,CRITICAL \
		--ignore-unfixed --exit-code 1 --no-progress "$(BACKEND_IMAGE)"

audit-db-image:
	mkdir -p "$(TRIVY_CACHE)"
	docker run --rm \
		-v /var/run/docker.sock:/var/run/docker.sock \
		-v "$(TRIVY_CACHE):/root/.cache/" \
		"$(TRIVY_IMAGE)" image --scanners vuln --severity HIGH,CRITICAL \
		--ignore-unfixed --exit-code 1 --no-progress pcep_webapp-postgres:16.15-alpine3.24

build: build-frontend

build-frontend: fetch-pyodide
	cd frontend && VITE_PCEP_RELEASE="$(RELEASE)" $(NPM) run build

# Match the bind-mounted source/output ownership instead of assuming host UID 1000.
# HOME/cache stay on the disposable container filesystem for arbitrary host UIDs.
compose-build-frontend:
	$(COMPOSE) --profile build run --rm --user "$$(id -u):$$(id -g)" --env HOME=/tmp --env NPM_CONFIG_CACHE=/tmp/npm-cache frontend-builder

# Self-hosted Python runtime for the in-browser code runner (git-ignored, ~12 MB).
# Fetched only when missing so repeat builds stay fast.
fetch-pyodide:
	cd frontend && $(NPM) run fetch-pyodide

django-check:
	cd backend && DJANGO_SETTINGS_MODULE=pcep_project.settings DJANGO_DEBUG=False DJANGO_SECRET_KEY=a-sufficiently-long-production-secret-key-for-local-check DJANGO_ALLOWED_HOSTS=pcep.micutu.com POSTGRES_DB=pcep_db POSTGRES_USER=pcep_user POSTGRES_PASSWORD=dummy POSTGRES_HOST=localhost POSTGRES_PORT=5432 "$(PYTHON_BIN)" manage.py check --deploy --fail-level WARNING

production-smoke:
	"$(PYTHON_BIN)" scripts/production_smoke.py --base-url "$(PRODUCTION_URL)"

compose-build:
	PCEP_RELEASE="$(RELEASE)" $(COMPOSE) build backend

deploy-backend:
	"$(PYTHON_BIN)" scripts/deploy_backend.py --backup-root "$(BACKUP_ROOT)" --release "$(RELEASE)" $(BACKEND_DEPLOY_FLAGS)

backup-database:
	"$(PYTHON_BIN)" scripts/database_backup.py --backup-root "$(DATABASE_BACKUP_ROOT)" --keep "$(DATABASE_BACKUP_KEEP)"

compose-up:
	$(COMPOSE) up -d

seed-reset:
	@test "$(ALLOW_QUESTION_RESET)" = "yes" || { printf "%s\n" "Reset changes live question IDs. Explicitly set ALLOW_QUESTION_RESET=yes to proceed."; exit 1; }
	$(COMPOSE) exec backend python manage.py audit_questions --fail-on-warnings
	$(COMPOSE) exec backend python manage.py seed_questions --reset

deploy-frontend: build-frontend
	"$(PYTHON_BIN)" scripts/publish_release.py frontend/dist "$(FRONTEND_ROOT)" --backup-root "$(BACKUP_ROOT)" --asset-retention-days "$(ASSET_RETENTION_DAYS)"

release-retention:
	"$(PYTHON_BIN)" scripts/release_retention.py "$(FRONTEND_ROOT)" --backup-root "$(BACKUP_ROOT)" --keep "$(RELEASE_KEEP)"

status:
	git status --short --branch
	$(COMPOSE) ps

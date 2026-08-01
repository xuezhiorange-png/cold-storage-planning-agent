UV_CACHE_DIR ?= .uv-cache

.PHONY: install dev up down migrate seed test lint format typecheck architecture-test demo clean-dev verify-slice2 production-config backend-image-build

install:
	cd backend && UV_CACHE_DIR=../$(UV_CACHE_DIR) uv sync
	cd frontend && npm install

dev:
	cd backend && PYTHONPATH=src UV_CACHE_DIR=../$(UV_CACHE_DIR) uv run uvicorn cold_storage.bootstrap.app:create_app --factory --reload

up:
	docker compose up -d

down:
	docker compose down

migrate:
	cd backend && PYTHONPATH=src UV_CACHE_DIR=../$(UV_CACHE_DIR) uv run alembic upgrade head

seed:
	cd backend && PYTHONPATH=src UV_CACHE_DIR=../$(UV_CACHE_DIR) uv run python -m cold_storage.bootstrap.seed

test:
	cd backend && UV_CACHE_DIR=../$(UV_CACHE_DIR) uv run pytest
	cd frontend && npm run test

lint:
	cd backend && UV_CACHE_DIR=../$(UV_CACHE_DIR) uv run ruff check .
	cd frontend && npm run lint

format:
	cd backend && UV_CACHE_DIR=../$(UV_CACHE_DIR) uv run ruff format .
	cd frontend && npm run format

typecheck:
	cd backend && UV_CACHE_DIR=../$(UV_CACHE_DIR) uv run mypy src
	cd frontend && npm run typecheck

architecture-test:
	cd backend && UV_CACHE_DIR=../$(UV_CACHE_DIR) uv run pytest tests/architecture

demo:
	cd backend && PYTHONPATH=src UV_CACHE_DIR=../$(UV_CACHE_DIR) uv run python -m cold_storage.bootstrap.demo

clean-dev:
	rm -rf backend/storage frontend/dist .uv-cache .pytest_cache backend/.pytest_cache

# --- TASK-012 Slice 2: production-oriented lifecycle verification ----
# These targets are deterministic and idempotent. They MUST NOT push
# to any registry, create releases, or perform destructive ops. Each
# target exits non-zero on contract failure so the CI gate is
# machine-readable.

# Root local Compose syntax check (existed pre-Slice 2).
production-config:
	docker compose -f docker-compose.production.yml config

# Backend image build with the build-identity authority file.
# F-PR76-LOW-01: the previous target only set host-side environment
# variables and never forwarded them as ``--build-arg`` to docker, so
# the Dockerfile ARGs stayed empty and the build-time fail-fast
# identity guard refused to produce an image. This target forwards
# both values explicitly with --build-arg and exits non-zero when
# either value is empty. CI MUST supply both; a zero SHA or
# "v0.0.0" placeholder is no longer a silent fallback because the
# exact-match validation in deployment_identity rejects both shapes
# before the image is written.
backend-image-build:
	@if [ -z "$${COLD_STORAGE_BUILD_COMMIT_SHA:-}" ]; then \
		echo "backend-image-build: COLD_STORAGE_BUILD_COMMIT_SHA is required" >&2; \
		exit 18; \
	fi
	@if [ -z "$${COLD_STORAGE_BUILD_VERSION:-}" ]; then \
		echo "backend-image-build: COLD_STORAGE_BUILD_VERSION is required" >&2; \
		exit 19; \
	fi
	docker build \
		-f backend/Dockerfile \
		--build-arg COLD_STORAGE_BUILD_COMMIT_SHA="$${COLD_STORAGE_BUILD_COMMIT_SHA}" \
		--build-arg COLD_STORAGE_BUILD_VERSION="$${COLD_STORAGE_BUILD_VERSION}" \
		-t "cold-storage-backend:$${COLD_STORAGE_BUILD_COMMIT_SHA}" \
		.

# Compose-validated production configuration plus a non-running
# build of the image. CI invokes this in the compose-config job.
verify-slice2:
	@echo 'verify-slice2 starting'
	@$(MAKE) --no-print-directory production-config
	@echo 'verify-slice2 ok'

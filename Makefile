UV_CACHE_DIR ?= .uv-cache

.PHONY: install dev up down migrate seed test lint format typecheck architecture-test demo clean-dev

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

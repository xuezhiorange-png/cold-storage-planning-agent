# 冷库规划设计 Agent V1

面向蓝莓及其他果蔬加工厂的冷库规划设计辅助系统。系统用于需求收集、参数结构化、确定性工程计算、方案比较、知识检索、报告草稿和自然语言辅助操作。

本系统是规划和概念设计辅助工具，不是正式施工图设计系统，不替代设计院、注册工程师、结构设计、消防审查、压力管道设计、电气施工设计或最终设备选型。

## Tech Stack

- Backend: Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, PostgreSQL, pgvector, Redis, pytest, Ruff, mypy
- Frontend: Vue 3, TypeScript, Vite, Element Plus, Vue Router, Pinia, ECharts, Vitest
- Infra: Docker Compose, PostgreSQL, Redis

## Commands

```bash
make install
make dev
make up
make down
make migrate
make seed
make test
make lint
make format
make typecheck
make architecture-test
make demo
make clean-dev
```

`make clean-dev` is for local development only and may remove local generated data.

## Local Backend

```bash
cd backend
UV_CACHE_DIR=../.uv-cache uv sync
UV_CACHE_DIR=../.uv-cache uv run uvicorn cold_storage.bootstrap.app:create_app --factory --reload
```

## Current V1 Scope

- Deterministic calculators run without any model API key.
- Fake model and embedding gateways are the default.
- Demo coefficients are explicitly unverified and require review.
- OCR is not implemented in V1; scanned PDFs are marked `requires_ocr=true`.

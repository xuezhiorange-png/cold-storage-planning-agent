UV_CACHE_DIR ?= .uv-cache
RC_BUILD_CONTEXT ?= .

.PHONY: install dev up down migrate seed seed-v04-sample seed-v05-sample seed-v06-sample seed-v07-sample smoke-v04-local smoke-v05-local verify-v06-sample verify-v07-sample smoke-v06-local smoke-v07-local verify-v05-p5-controlled-acceptance verify-v07-p7-controlled-acceptance test lint format typecheck architecture-test demo clean-dev verify-slice2 production-config backend-image-build release-evidence-test release-evidence-lint release-evidence-typecheck verify-release-evidence verify-base-image-digests verify-live-evidence-runner verify-artifact-transport recovery-foundation-test recovery-foundation-lint recovery-foundation-typecheck verify-recovery-foundation release-failure-recovery-test release-failure-recovery-lint release-failure-recovery-typecheck verify-release-failure-recovery final-release-evidence-test final-release-evidence-lint final-release-evidence-typecheck verify-final-release-evidence test-s6-07-operational-acceptance s6-07-operational-acceptance-test s6-07-operational-acceptance-lint s6-07-operational-acceptance-typecheck verify-s6-07-operational-acceptance

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

seed-v04-sample:
	cd backend && PYTHONPATH=src UV_CACHE_DIR=../$(UV_CACHE_DIR) uv run python -m cold_storage.bootstrap.v04_local_sample

seed-v05-sample:
	cd backend && PYTHONPATH=src UV_CACHE_DIR=../$(UV_CACHE_DIR) uv run python -m cold_storage.bootstrap.v05_local_sample

seed-v06-sample:
	cd backend && PYTHONPATH=src UV_CACHE_DIR=../$(UV_CACHE_DIR) uv run python -m cold_storage.bootstrap.v06_sample_loader

seed-v07-sample:
	cd backend && PYTHONPATH=src UV_CACHE_DIR=../$(UV_CACHE_DIR) uv run python -m cold_storage.bootstrap.v07_sample_loader

verify-v06-sample:
	cd backend && PYTHONPATH=src UV_CACHE_DIR=../$(UV_CACHE_DIR) uv run python -m cold_storage.bootstrap.v06_sample_loader --verify

verify-v07-sample:
	cd backend && PYTHONPATH=src UV_CACHE_DIR=../$(UV_CACHE_DIR) uv run python -m cold_storage.bootstrap.v07_sample_loader --verify

smoke-v06-local: verify-v06-sample

smoke-v07-local: verify-v07-sample

smoke-v04-local:
	cd backend && PYTHONPATH=src UV_CACHE_DIR=../$(UV_CACHE_DIR) uv run pytest tests/integration/test_v04_local_sample_boot.py -q

smoke-v05-local:
	cd backend && PYTHONPATH=src UV_CACHE_DIR=../$(UV_CACHE_DIR) uv run pytest tests/integration/test_v05_p4_local_sample_smoke.py -q

verify-v05-p5-controlled-acceptance:
	cd backend && PYTHONPATH=src UV_CACHE_DIR=../$(UV_CACHE_DIR) uv run pytest \
		tests/architecture/test_v05_p5_controlled_acceptance_contract.py \
		tests/integration/test_v05_p5_controlled_acceptance_sqlite.py \
		tests/integration/test_v05_p4_local_sample_smoke.py \
		-q

verify-v07-p7-controlled-acceptance:
	cd backend && PYTHONPATH=src UV_CACHE_DIR=../$(UV_CACHE_DIR) uv run pytest \
		tests/integration/test_v07_p7_controlled_acceptance_sqlite.py \
		tests/integration/test_v07_p7_controlled_acceptance_postgresql.py \
		-q

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

# Backend image build with an explicitly selected RC source worktree.
# The evidence-tooling checkout may be newer than the immutable RC source;
# Docker context identity must therefore be checked before any build starts.
backend-image-build:
	@set -eu; \
		context="$(RC_BUILD_CONTEXT)"; \
		commit="$${COLD_STORAGE_BUILD_COMMIT_SHA:-}"; \
		version="$${COLD_STORAGE_BUILD_VERSION:-}"; \
		if [ -z "$${commit}" ]; then \
			echo "backend-image-build: COLD_STORAGE_BUILD_COMMIT_SHA is required" >&2; \
			exit 18; \
		fi; \
		if [ -z "$${version}" ]; then \
			echo "backend-image-build: COLD_STORAGE_BUILD_VERSION is required" >&2; \
			exit 19; \
		fi; \
		if ! git -C "$${context}" cat-file -e "$${commit}^{commit}"; then \
			echo "backend-image-build: source commit does not exist: $${commit}" >&2; \
			exit 20; \
		fi; \
		context_head="$$(git -C "$${context}" rev-parse HEAD)"; \
		if [ "$${context_head}" != "$${commit}" ]; then \
			echo "backend-image-build: context HEAD ($${context_head}) does not match source commit ($${commit})" >&2; \
			exit 21; \
		fi; \
		if [ -n "$$(git -C "$${context}" status --porcelain)" ]; then \
			echo "backend-image-build: RC build context is dirty: $${context}" >&2; \
			exit 22; \
		fi; \
		source_date_epoch="$$(git -C "$${context}" show -s --format=%ct "$${commit}")"; \
		case "$${source_date_epoch}" in \
			''|*[!0-9]*) \
				echo "backend-image-build: source timestamp is not a decimal integer" >&2; \
				exit 23; \
			;; \
		esac; \
		docker build \
			-f "$${context}/backend/Dockerfile" \
			--build-arg COLD_STORAGE_BUILD_COMMIT_SHA="$${commit}" \
			--build-arg COLD_STORAGE_BUILD_VERSION="$${version}" \
			--build-arg SOURCE_DATE_EPOCH="$${source_date_epoch}" \
			-t "cold-storage-backend:$${commit}" \
			"$${context}"

# Compose-validated production configuration plus a non-running
# build of the image. CI invokes this in the compose-config job.
verify-slice2:
	@echo 'verify-slice2 starting'
	@$(MAKE) --no-print-directory production-config
	@echo 'verify-slice2 ok'

# --- TASK-012 Slice 2 R1: release-candidate evidence verification ---

# Lint the release evidence module.
release-evidence-lint:
	cd backend && UV_CACHE_DIR=../$(UV_CACHE_DIR) uv run ruff check src/cold_storage/release/ && uv run ruff format --check src/cold_storage/release/

# Typecheck the release evidence module.
release-evidence-typecheck:
	cd backend && UV_CACHE_DIR=../$(UV_CACHE_DIR) uv run mypy src/cold_storage/release/ --strict --ignore-missing-imports

# Run all release evidence tests (unit + integration + architecture).
release-evidence-test:
	cd backend && PYTHONPATH=src UV_CACHE_DIR=../$(UV_CACHE_DIR) uv run pytest \
		tests/unit/test_canonical_serialization.py \
		tests/unit/test_reproducible_build_evidence.py \
		tests/unit/test_final_image_digest.py \
		tests/unit/test_artifact_manifest.py \
		tests/unit/test_provenance_statement.py \
		tests/unit/test_promotion_record.py \
		tests/unit/test_negative_scenarios.py \
		tests/unit/test_live_evidence_runner.py \
		tests/unit/test_artifact_transport.py \
		tests/unit/test_final_release_evidence.py \
		tests/integration/test_release_candidate_evidence.py \
		tests/integration/test_live_evidence_runner.py \
		tests/integration/test_artifact_transport.py \
		tests/integration/test_final_release_evidence.py \
		tests/architecture/test_final_release_evidence_boundaries.py \
		tests/architecture/test_release_evidence_boundaries.py \
		-q

# TASK-012 V0.2 Slice 6 Package 3: deterministic final bundle tests.
final-release-evidence-test:
	cd backend && PYTHONPATH=src UV_CACHE_DIR=../$(UV_CACHE_DIR) uv run pytest \
		tests/unit/test_final_release_evidence.py \
		tests/integration/test_final_release_evidence.py \
		tests/architecture/test_final_release_evidence_boundaries.py \
		-q

final-release-evidence-lint:
	cd backend && UV_CACHE_DIR=../$(UV_CACHE_DIR) uv run ruff check \
		src/cold_storage/release/final_release_evidence.py \
		tests/unit/test_final_release_evidence.py \
		tests/integration/test_final_release_evidence.py \
		tests/architecture/test_final_release_evidence_boundaries.py
	cd backend && UV_CACHE_DIR=../$(UV_CACHE_DIR) uv run ruff format --check \
		src/cold_storage/release/final_release_evidence.py \
		tests/unit/test_final_release_evidence.py \
		tests/integration/test_final_release_evidence.py \
		tests/architecture/test_final_release_evidence_boundaries.py

final-release-evidence-typecheck:
	cd backend && UV_CACHE_DIR=../$(UV_CACHE_DIR) uv run mypy \
		src/cold_storage/release/final_release_evidence.py \
		--strict --ignore-missing-imports

verify-final-release-evidence: final-release-evidence-lint final-release-evidence-typecheck final-release-evidence-test
	@echo 'verify-final-release-evidence ok'

# TASK-012 V0.2 Slice 6 S6-07: deterministic implementation tests only.
# This target never dispatches the controlled acceptance workflow or starts
# the production-oriented Compose surface.
s6-07-operational-acceptance-test:
	cd backend && PYTHONPATH=src UV_CACHE_DIR=../$(UV_CACHE_DIR) uv run pytest \
		tests/unit/test_end_to_end_operational_acceptance.py \
		tests/integration/test_end_to_end_operational_acceptance.py \
		tests/architecture/test_end_to_end_operational_acceptance_boundaries.py \
		-q

test-s6-07-operational-acceptance: s6-07-operational-acceptance-test

s6-07-operational-acceptance-lint:
	cd backend && UV_CACHE_DIR=../$(UV_CACHE_DIR) uv run ruff check \
		src/cold_storage/release/end_to_end_operational_acceptance.py \
		src/cold_storage/bootstrap/s6_07_controlled_fixture.py \
		tests/unit/test_end_to_end_operational_acceptance.py \
		tests/integration/test_end_to_end_operational_acceptance.py \
		tests/architecture/test_end_to_end_operational_acceptance_boundaries.py
	cd backend && UV_CACHE_DIR=../$(UV_CACHE_DIR) uv run ruff format --check \
		src/cold_storage/release/end_to_end_operational_acceptance.py \
		src/cold_storage/bootstrap/s6_07_controlled_fixture.py \
		tests/unit/test_end_to_end_operational_acceptance.py \
		tests/integration/test_end_to_end_operational_acceptance.py \
		tests/architecture/test_end_to_end_operational_acceptance_boundaries.py

s6-07-operational-acceptance-typecheck:
	cd backend && UV_CACHE_DIR=../$(UV_CACHE_DIR) uv run mypy \
		src/cold_storage/release/end_to_end_operational_acceptance.py \
		src/cold_storage/bootstrap/s6_07_controlled_fixture.py \
		--strict --ignore-missing-imports

verify-s6-07-operational-acceptance: s6-07-operational-acceptance-lint s6-07-operational-acceptance-typecheck s6-07-operational-acceptance-test
	@ruby -e 'require "yaml"; YAML.load_file(".github/workflows/task012-slice6-s7-e2e-operational-acceptance.yml")'
	@echo 'verify-s6-07-operational-acceptance ok'

# Runner-only contract gate. This target uses mock/synthetic tests and never
# invokes a real Docker build, registry push, signing command, or deployment.
verify-live-evidence-runner:
	cd backend && PYTHONPATH=src UV_CACHE_DIR=../$(UV_CACHE_DIR) uv run pytest \
		tests/unit/test_live_evidence_runner.py \
		tests/integration/test_live_evidence_runner.py \
		tests/architecture/test_release_evidence_boundaries.py \
		-q

# Artifact transport-only contract gate. This target uses mock HTTP and
# synthetic ZIP packages; it never contacts GitHub or uploads/downloads data.
verify-artifact-transport:
	cd backend && PYTHONPATH=src UV_CACHE_DIR=../$(UV_CACHE_DIR) uv run pytest \
		tests/unit/test_artifact_transport.py \
		tests/integration/test_artifact_transport.py \
		tests/architecture/test_release_evidence_boundaries.py \
		-q

# --- TASK-012 V0.2 Slice 6 Package 1: data recovery foundation ---

# Recovery tests use synthetic files and, when configured, an isolated
# PostgreSQL service. They never connect to a production resource.
recovery-foundation-test:
	cd backend && PYTHONPATH=src UV_CACHE_DIR=../$(UV_CACHE_DIR) uv run pytest \
		tests/unit/test_recovery_backup.py \
		tests/unit/test_recovery_restore.py \
		tests/unit/test_recovery_verification.py \
		tests/unit/test_failure_recovery.py \
		tests/integration/test_recovery_postgresql.py \
		tests/integration/test_failure_recovery_postgresql.py \
		tests/architecture/test_recovery_boundaries.py \
		-q

recovery-foundation-lint:
	cd backend && UV_CACHE_DIR=../$(UV_CACHE_DIR) uv run ruff check \
		src/cold_storage/recovery \
		tests/unit/test_recovery_backup.py \
		tests/unit/test_recovery_restore.py \
		tests/unit/test_recovery_verification.py \
		tests/unit/test_failure_recovery.py \
		tests/integration/test_recovery_postgresql.py \
		tests/integration/test_failure_recovery_postgresql.py \
		tests/architecture/test_recovery_boundaries.py
	cd backend && UV_CACHE_DIR=../$(UV_CACHE_DIR) uv run ruff format --check \
		src/cold_storage/recovery \
		tests/unit/test_recovery_backup.py \
		tests/unit/test_recovery_restore.py \
		tests/unit/test_recovery_verification.py \
		tests/unit/test_failure_recovery.py \
		tests/integration/test_recovery_postgresql.py \
		tests/integration/test_failure_recovery_postgresql.py \
		tests/architecture/test_recovery_boundaries.py

recovery-foundation-typecheck:
	cd backend && UV_CACHE_DIR=../$(UV_CACHE_DIR) uv run mypy \
		src/cold_storage/recovery --strict --ignore-missing-imports

verify-recovery-foundation: recovery-foundation-lint recovery-foundation-typecheck recovery-foundation-test
	@echo 'verify-recovery-foundation ok'

# --- TASK-012 V0.2 Slice 6 Package 2: release failure recovery ---

release-failure-recovery-test:
	cd backend && PYTHONPATH=src UV_CACHE_DIR=../$(UV_CACHE_DIR) uv run pytest \
		tests/unit/test_failure_recovery.py \
		tests/integration/test_failure_recovery_postgresql.py \
		tests/architecture/test_recovery_boundaries.py \
		-q

release-failure-recovery-lint:
	cd backend && UV_CACHE_DIR=../$(UV_CACHE_DIR) uv run ruff check \
		src/cold_storage/recovery/failure_recovery.py \
		src/cold_storage/recovery/cli.py \
		tests/unit/test_failure_recovery.py \
		tests/integration/test_failure_recovery_postgresql.py \
		tests/architecture/test_recovery_boundaries.py
	cd backend && UV_CACHE_DIR=../$(UV_CACHE_DIR) uv run ruff format --check \
		src/cold_storage/recovery/failure_recovery.py \
		src/cold_storage/recovery/cli.py \
		tests/unit/test_failure_recovery.py \
		tests/integration/test_failure_recovery_postgresql.py \
		tests/architecture/test_recovery_boundaries.py

release-failure-recovery-typecheck:
	cd backend && UV_CACHE_DIR=../$(UV_CACHE_DIR) uv run mypy \
		src/cold_storage/recovery --strict --ignore-missing-imports

verify-release-failure-recovery: release-failure-recovery-lint release-failure-recovery-typecheck release-failure-recovery-test
	@echo 'verify-release-failure-recovery ok'

# Full release evidence verification gate.
verify-release-evidence: release-evidence-lint release-evidence-typecheck release-evidence-test
	@echo 'verify-release-evidence ok'

# Verify that base images in Dockerfile and Compose files are pinned by digest.
verify-base-image-digests:
	@echo 'checking base image digest pinning...'
	@if ! grep -q '@sha256:' backend/Dockerfile; then \
		echo 'FAIL: backend/Dockerfile does not pin base images by digest' >&2; \
		exit 1; \
	fi
	@if ! grep -q '@sha256:' docker-compose.yml; then \
		echo 'FAIL: docker-compose.yml does not pin images by digest' >&2; \
		exit 1; \
	fi
	@if ! grep -q '@sha256:' docker-compose.production.yml; then \
		echo 'FAIL: docker-compose.production.yml does not pin images by digest' >&2; \
		exit 1; \
	fi
	@echo 'verify-base-image-digests ok'

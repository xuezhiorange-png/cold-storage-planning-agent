# Evaluation Harness — Phase A

This directory contains the **evaluation and pilot readiness** tooling for
the Cold Storage Planning Agent (Task 11).

## Phase A scope

Phase A delivers the contract and harness infrastructure only:

- **`manifest.schema.json`** — strict JSON Schema for evaluation manifests.
- **`manifest.example.json`** — example manifest with one validation
  scenario (not a real pilot fixture).
- **Python evaluation module** in `backend/src/cold_storage/evaluation/`:
  - Immutable data models (`models.py`)
  - Strict manifest loader with schema + semantic validation (`manifest.py`)
  - Path safety enforcement (`paths.py`)
  - JSON canonicalization library (`canonicalize.py`)
  - Comparison library (`compare.py`)
  - Isolated run directory management (`run_directory.py`)
  - CLI skeleton (`cli.py`)
- **`backend/tests/evaluation/`** — fail-closed unit tests.

Phases B, C, and D (pilot fixtures, persisted/report verification, CI
integration, runbook) are **not yet implemented**.

## Manifest and schema

- **Schema**: `evaluation/manifest.schema.json`
- **Example**: `evaluation/manifest.example.json`

The example manifest is **not a formal pilot fixture**.  It exists to
validate the Phase A harness.

## Commands

```bash
# Strict validation (schema + path + semantics)
cd backend
PYTHONPATH=src uv run python -m cold_storage.evaluation.cli validate \
  --manifest ../evaluation/manifest.example.json

# Stable JSON summary
PYTHONPATH=src uv run python -m cold_storage.evaluation.cli inspect \
  --manifest ../evaluation/manifest.example.json

# Run is not implemented in Phase A
PYTHONPATH=src uv run python -m cold_storage.evaluation.cli run \
  --manifest ../evaluation/manifest.example.json   # → nonzero exit
```

## Rules

- **No real customer data.** All fixtures and manifests must use synthetic
  or explicitly licensed information.
- **No automatic golden updates.** Expected files are reviewed via Git.
- **`runs/` is generated output.** Each evaluation run creates a unique
  subdirectory. Stale files from old runs do not satisfy the current run.
- **Phase A does not prove production readiness.** It establishes the
  evaluation infrastructure.

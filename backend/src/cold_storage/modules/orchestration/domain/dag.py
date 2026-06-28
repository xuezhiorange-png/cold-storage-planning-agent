"""Orchestration five-stage DAG — immutable stage registry and dependency graph.

Approved design (PR #23, Head b30ccf8):
    zone -> cooling_load -> equipment -> power -> investment
"""

from __future__ import annotations

from collections.abc import Mapping

# ── Exact five-stage order ──────────────────────────────────────────────────

ORCHESTRATION_STAGE_ORDER: tuple[str, ...] = (
    "zone",
    "cooling_load",
    "equipment",
    "power",
    "investment",
)

# ── Exact calculator name for each stage ────────────────────────────────────

CALCULATOR_BINDINGS: Mapping[str, str] = {
    "zone": "cold_room_zone_plan",
    "cooling_load": "cooling_load",
    "equipment": "equipment",
    "power": "installed_power",
    "investment": "investment_estimate",
}

# ── Exact dependencies: each value is the tuple of preceding stages ─────────

STAGE_DEPENDENCIES: Mapping[str, tuple[str, ...]] = {
    "zone": (),
    "cooling_load": ("zone",),
    "equipment": ("cooling_load",),
    "power": ("equipment",),
    "investment": ("zone", "power"),
}

# ── Upstream calculation IDs provenance keys per stage ──────────────────────

STAGE_UPSTREAM_PROVENANCE_KEYS: Mapping[str, frozenset[str]] = {
    "zone": frozenset(),
    "cooling_load": frozenset({"zone"}),
    "equipment": frozenset({"cooling_load"}),
    "power": frozenset({"equipment"}),
    "investment": frozenset({"zone", "power"}),
}

# ── Allowed keys ────────────────────────────────────────────────────────────

ALLOWED_STAGES: frozenset[str] = frozenset(ORCHESTRATION_STAGE_ORDER)


# ── Validation helpers ──────────────────────────────────────────────────────


def validate_stage_acyclic() -> None:
    """Verify the DAG is acyclic and every dependency is a preceding stage."""
    for stage in ORCHESTRATION_STAGE_ORDER:
        deps = STAGE_DEPENDENCIES.get(stage, ())
        idx = ORCHESTRATION_STAGE_ORDER.index(stage)
        for dep in deps:
            if dep not in ALLOWED_STAGES:
                raise ValueError(f"Unknown dependency {dep!r} for stage {stage!r}")
            dep_idx = ORCHESTRATION_STAGE_ORDER.index(dep)
            if dep_idx >= idx:
                raise ValueError(f"Stage {stage!r} depends on later or same stage {dep!r}")


def validate_registry_consistency() -> None:
    """Verify stage order, calculator bindings, and dependencies are consistent."""
    stages = set(ORCHESTRATION_STAGE_ORDER)
    calc_stages = set(CALCULATOR_BINDINGS.keys())
    dep_stages = set(STAGE_DEPENDENCIES.keys())
    prov_stages = set(STAGE_UPSTREAM_PROVENANCE_KEYS.keys())

    if len(stages) != 5:
        raise ValueError(f"Expected exactly 5 stages, got {len(stages)}: {stages}")

    if stages != calc_stages:
        raise ValueError(f"CALCULATOR_BINDINGS keys {calc_stages} != stages {stages}")

    if stages != dep_stages:
        raise ValueError(f"STAGE_DEPENDENCIES keys {dep_stages} != stages {stages}")

    if stages != prov_stages:
        raise ValueError(f"STAGE_UPSTREAM_PROVENANCE_KEYS keys {prov_stages} != stages {stages}")

    if stages != ALLOWED_STAGES:
        raise ValueError(f"ALLOWED_STAGES {ALLOWED_STAGES} != stages {stages}")

    for stage in stages:
        provenance_keys = STAGE_UPSTREAM_PROVENANCE_KEYS.get(stage, frozenset())
        expected_deps = set(STAGE_DEPENDENCIES.get(stage, ()))
        if provenance_keys != expected_deps:
            raise ValueError(
                f"Stage {stage!r}: provenance keys {provenance_keys} != "
                f"expected dependencies {expected_deps}"
            )

    validate_stage_acyclic()


# Validate at import time for fail-fast correctness
validate_registry_consistency()

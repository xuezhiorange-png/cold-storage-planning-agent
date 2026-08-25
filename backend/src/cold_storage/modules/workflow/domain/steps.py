"""Workflow step and status vocabulary for P4 aggregation."""

from __future__ import annotations

from cold_storage.modules.orchestration.domain.consumer_bindings import (
    CANONICAL_CALCULATOR_NAMES,
)

WORKFLOW_CONTRACT_VERSION = "WorkflowAggregateV1"

REQUIRED_SCHEME_CALCULATOR_NAMES = CANONICAL_CALCULATOR_NAMES

WORKFLOW_STEPS: tuple[str, ...] = (
    "PROJECT_INPUT",
    "INPUT_COMPLETENESS",
    "DETERMINISTIC_CALCULATION",
    "SCHEME_COMPARISON",
    "REVIEW_BLOCKER",
    "HUMAN_REVIEW",
    "APPROVAL",
    "AGENT_ASSISTANCE",
    "KNOWLEDGE_PROVENANCE",
    "REPORT_ELIGIBILITY",
    "FORMAL_REPORT",
)

MAINLINE_STEPS: tuple[str, ...] = (
    "PROJECT_INPUT",
    "INPUT_COMPLETENESS",
    "DETERMINISTIC_CALCULATION",
    "SCHEME_COMPARISON",
    "REVIEW_BLOCKER",
    "HUMAN_REVIEW",
    "APPROVAL",
    "REPORT_ELIGIBILITY",
    "FORMAL_REPORT",
)

STEP_APPLICABILITY_VALUES: frozenset[str] = frozenset(
    {"REQUIRED", "OPTIONAL", "CONDITIONAL", "NOT_APPLICABLE"}
)

WORKFLOW_GOAL_FORMAL_REPORT = "formal_report"
WORKFLOW_GOAL_PLANNING_PREVIEW = "planning_preview"

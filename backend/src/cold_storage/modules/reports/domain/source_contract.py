"""Shared source authenticity contract for the reports module.

Defines which tool-call statuses are acceptable as report sources,
shared between the Assembler (selection) and Quality Gate (validation).
"""

from __future__ import annotations

from typing import Any

# Real tool name registered in planning_agent.application.tool_registry.
KNOWLEDGE_SEARCH_TOOL: str = "knowledge.search"

# Tool-call statuses that represent a successfully completed operation
# suitable for inclusion as a report source reference.
# Derived from planning_agent.domain.enums.ToolCallStatus.
#
# Note: 'confirmed' is deliberately excluded.  For planning-agent tool
# calls only 'succeeded' is a real terminal success state.  'confirmed'
# means the tool was confirmed but may not have executed yet.
# 'completed'/'success' are kept for compatibility with other source types
# (calculation results, scheme results) that use different status
# vocabularies.
SOURCE_SUCCESS_STATUSES: frozenset[str] = frozenset(
    {
        "succeeded",
        "completed",
        "success",
    }
)

# For planning-agent tool calls specifically, only 'succeeded' is terminal.
AGENT_TOOL_SUCCESS_STATUSES: frozenset[str] = frozenset({"succeeded"})


def compute_scheme_source_hash(
    run_id: str,
    recommended_scheme_code: str,
    generator_version: str,
    candidates: list[dict[str, Any]] | None = None,
) -> str:
    """Stable hash of scheme run content for provenance verification.

    Used by both SchemeQueryService (to compute persisted hash)
    and RealReportDataProvider (to verify hash matches).
    """
    import hashlib
    import json

    payload: dict[str, Any] = {
        "run_id": run_id,
        "recommended_scheme_code": recommended_scheme_code or "",
        "generator_version": generator_version or "",
    }
    if candidates:
        payload["candidates"] = [
            {
                "id": c.get("id", ""),
                "scheme_code": c.get("scheme_code", ""),
                "total_score": c.get("total_score"),
                "rank": c.get("rank"),
            }
            for c in sorted(candidates, key=lambda x: x.get("id", ""))
        ]
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()

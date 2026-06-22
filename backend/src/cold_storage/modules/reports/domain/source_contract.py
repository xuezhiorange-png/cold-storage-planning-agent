"""Shared source authenticity contract for the reports module.

Defines which tool-call statuses are acceptable as report sources,
shared between the Assembler (selection) and Quality Gate (validation).
"""

from __future__ import annotations

# Tool-call statuses that represent a successfully completed operation
# suitable for inclusion as a report source reference.
# Derived from planning_agent.domain.enums.ToolCallStatus.
SOURCE_SUCCESS_STATUSES: frozenset[str] = frozenset(
    {
        "succeeded",
        "confirmed",
        "completed",
        "success",
    }
)

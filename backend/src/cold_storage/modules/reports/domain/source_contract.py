"""Shared source authenticity contract for the reports module.

Defines which tool-call statuses are acceptable as report sources,
shared between the Assembler (selection) and Quality Gate (validation).
"""

from __future__ import annotations

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

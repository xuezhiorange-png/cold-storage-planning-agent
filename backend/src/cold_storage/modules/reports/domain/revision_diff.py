"""Deterministic revision diff — no LLM, no guessing.

Compares two report revision content dicts and produces a structured
list of changes.
"""

from __future__ import annotations

from typing import Any


def diff_revisions(
    before: dict[str, Any],
    after: dict[str, Any],
    _path: str = "",
) -> list[dict[str, Any]]:
    """Produce a deterministic diff between two report content dicts.

    Returns a list of change records:
        {"field_path": "...", "change_type": "added|removed|modified",
         "before": ..., "after": ...}
    """
    changes: list[dict[str, Any]] = []
    all_keys = set(before.keys()) | set(after.keys())

    for key in sorted(all_keys):
        cur = f"{_path}.{key}" if _path else key
        in_before = key in before
        in_after = key in after

        if in_before and not in_after:
            changes.append(
                {
                    "field_path": cur,
                    "change_type": "removed",
                    "before": before[key],
                    "after": None,
                }
            )
        elif not in_before and in_after:
            changes.append(
                {
                    "field_path": cur,
                    "change_type": "added",
                    "before": None,
                    "after": after[key],
                }
            )
        else:
            bv = before[key]
            av = after[key]
            if isinstance(bv, dict) and isinstance(av, dict):
                changes.extend(diff_revisions(bv, av, cur))
            elif bv != av:
                change: dict[str, Any] = {
                    "field_path": cur,
                    "change_type": "modified",
                    "before": bv,
                    "after": av,
                }
                # Detect unit changes
                unit_key = f"{key}_unit" if not key.endswith("_unit") else key
                if unit_key in before and unit_key in after and before[unit_key] != after[unit_key]:
                    change["unit_changed"] = True
                    change["before_unit"] = before[unit_key]
                    change["after_unit"] = after[unit_key]
                changes.append(change)

    return changes

"""Finite event-based room proposals from the CURRENT scene and its blockers.

These are search choices, never additional room Authority or historical seeds.
The original attachment search supplies the current initial twelve rooms.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from decimal import Decimal
from typing import Any

from cold_storage.modules.layout.domain.dimensioning import canonical_hash
from cold_storage.modules.layout.domain.site_geometry import PlacedRectangleV1

DOWNSTREAM = ("coating_room", "finished_goods_room", "shipping_channel", "office")


def room_state_hash(rooms: Mapping[str, PlacedRectangleV1]) -> str:
    return canonical_hash(
        {k: {"bbox_mm": q.bounds_mm, "rotation": q.rotation_deg} for k, q in sorted(rooms.items())}
    )


def feedback_room_proposals(
    rooms: Mapping[str, PlacedRectangleV1],
    columns: Sequence[Mapping[str, Any]],
    authorities: Mapping[str, Mapping[str, Any]],
    *,
    node_budget: int,
) -> list[dict[str, Any]]:
    if not 1 <= node_budget <= 48:
        raise ValueError("ADAPTIVE_ROOM_NODE_BUDGET_INVALID")
    finished = rooms["finished_goods_room"].bounds_mm
    relevant = [
        q
        for q in columns
        if q["bbox_mm"][0] < finished[2]
        and q["bbox_mm"][2] > finished[0]
        and q["bbox_mm"][1] < finished[3]
        and q["bbox_mm"][3] > finished[1]
    ]
    # Actual column edges, never an archived displacement. Margins are explicitly
    # unapproved positioning choices; none changes a hard feasibility predicate.
    events = sorted(
        {
            (q["bbox_mm"][3] + margin - finished[1], q["id"], margin)
            for q in relevant
            for margin in (100, 300, 600)
            if 0 < q["bbox_mm"][3] + margin - finished[1] <= 5000
        }
    )
    found: dict[str, dict[str, Any]] = {}

    def add(kind: str, state: dict[str, PlacedRectangleV1], **evidence: Any) -> None:
        h = room_state_hash(state)
        if h not in found and len(found) < node_budget:
            found[h] = {"kind": kind, "rooms": state, "room_geometry_hash": h, **evidence}

    add("CURRENT_INPUT_SEED", dict(rooms))
    # Try a different legal fixed-room orientation, with an explicit new
    # attachment of shipping/office. Exact Authority and collisions decide it.
    a = authorities["finished_goods_room"]
    for rotation in a["rotation_allowed"]:
        if rotation == rooms["finished_goods_room"].rotation_deg:
            continue
        w, h = (int(Decimal(str(a["geometry"][k])) * 1000) for k in ("width_m", "depth_m"))
        ww = w if rotation == 0 else h
        coat = rooms["coating_room"].bounds_mm
        for x in (coat[0], coat[2] - ww):
            state = dict(rooms)
            state["finished_goods_room"] = replace(
                rooms["finished_goods_room"], x=Decimal(x) / 1000, rotation_deg=rotation
            )
            ship = rooms["shipping_channel"]
            sw = ship.bounds_mm[2] - ship.bounds_mm[0]
            state["shipping_channel"] = replace(ship, x=Decimal(x - sw) / 1000)
            office = rooms["office"]
            state["office"] = replace(
                office,
                x=Decimal(x - sw) / 1000,
                y=Decimal(state["shipping_channel"].bounds_mm[3]) / 1000,
            )
            add("ALTERNATE_FIXED_ROTATION", state, rotation_deg=rotation)
    for dy, blocker, margin in events:
        translated = {
            k: replace(q, y=Decimal(q.y) + Decimal(dy) / 1000) if k in DOWNSTREAM else q
            for k, q in rooms.items()
        }
        add(
            "BLOCKER_EDGE_COUPLED_TRANSLATION",
            translated,
            delta_mm=[0, dy],
            blocker=blocker,
            positioning_margin_mm=margin,
        )
        # A different space solution: keep the upstream junction and extend
        # only an Authority-flexible connector before relocating downstream.
        if authorities["coating_room"]["dimension_mode"] == "FLEXIBLE_RECTANGLE":
            state = dict(translated)
            state["coating_room"] = replace(
                rooms["coating_room"],
                depth_m=Decimal(rooms["coating_room"].depth_m) + Decimal(dy) / 1000,
            )
            add(
                "FLEXIBLE_CONNECTOR_EXTENSION",
                state,
                delta_mm=[0, dy],
                blocker=blocker,
                positioning_margin_mm=margin,
            )
    # Translate the production group as another bounded family. The personnel
    # room stays independently attached by its original Access requirements.
    # Displacements derive from real column widths, not an archived layout.
    shifts = sorted(
        {q["bbox_mm"][2] - q["bbox_mm"][0] + m for q in relevant for m in (100, 300, 600)}
    )
    base_states = list(found.values())
    for base in base_states:
        if base["kind"] not in ("BLOCKER_EDGE_COUPLED_TRANSLATION", "CURRENT_INPUT_SEED"):
            continue
        for distance in shifts[:3]:
            for dx, dy in ((-distance, 0), (0, distance)):
                state = {
                    k: replace(
                        q, x=Decimal(q.x) + Decimal(dx) / 1000, y=Decimal(q.y) + Decimal(dy) / 1000
                    )
                    if k != "changing_room"
                    else q
                    for k, q in base["rooms"].items()
                }
                add(
                    "PRODUCTION_GROUP_RELOCATION",
                    state,
                    parent_room_hash=base["room_geometry_hash"],
                    delta_mm=[dx, dy],
                )
    return list(found.values())

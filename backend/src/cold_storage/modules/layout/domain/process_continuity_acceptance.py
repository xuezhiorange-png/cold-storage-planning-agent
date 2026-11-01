"""All required process functions, not a nonzero count of successful chains.

Only selected supply paths are admission requirements. Exploratory alternatives
are retained but cannot either earn a pass or invalidate a connected selection.
Machine operation remains conditional even when its projection is clear.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from cold_storage.modules.layout.domain.dimensioning import canonical_hash
from cold_storage.modules.layout.domain.process_transfer_interfaces import (
    ASSUMED,
    GEOMETRY,
    connect_transfer,
    endpoint_fingerprint,
    geometry_fingerprint,
    route_anchor,
    route_is_conditionally_usable,
    route_states,
)


def coverage_identity(row: Mapping[str, Any], kind: str) -> str:
    fields = (
        ("room", "from_access", "to_access")
        if kind == "interior"
        else ("room", "requirement_identity")
    )
    return kind + ":" + canonical_hash({k: row[k] for k in fields})


def assess_process_continuity(
    c: Mapping[str, Any], parameters: Mapping[str, Any], engineering_checks: Mapping[str, bool]
) -> dict[str, Any]:
    f = c["process_continuity"]
    routes = {q["id"]: q for q in f["routes"]}
    endpoints = {q["id"]: q for q in f["endpoints"]}
    transfers = {q["id"]: q for q in f["transfers"]}
    current = geometry_fingerprint(c, parameters)
    failures: list[dict[str, Any]] = []
    selected: set[str] = set()
    used_transfers: set[str] = set()
    replayed: dict[str, bool] = {}

    def fail(code: str, identity: str) -> None:
        failures.append({"code": code, "id": identity})

    def route_ok(identity: str) -> bool:
        selected.add(identity)
        r = routes.get(identity)
        if not r or not route_is_conditionally_usable(r):
            fail("REQUIRED_ROUTE_NOT_VERIFIED", identity)
            return False
        required_level = (
            ASSUMED
            if r["purpose"]
            in ("PACKING_MACHINE_INTERNAL", "CARTON_MACHINE_INTERNAL", "CARTON_SHORT_HANDOFF")
            else GEOMETRY
        )
        if r["status"] != required_level or (
            required_level == ASSUMED and r.get("actual_operation_status") != "INPUT_REQUIRED"
        ):
            fail("REQUIRED_VERIFICATION_LEVEL_MISMATCH", identity)
            return False
        if r.get("geometry_context_hash") != current or any(
            r.get("endpoint_binding_hashes", {}).get(side)
            != endpoint_fingerprint(endpoints.get(r[side + "_endpoint"], {}))
            for side in ("source", "target")
        ):
            fail("STALE_GEOMETRY_EVIDENCE", identity)
            return False
        if r.get("witness_hash") != canonical_hash(
            {k: v for k, v in r.items() if k != "witness_hash"}
        ):
            fail("ROUTE_WITNESS_CHANGED_WITHOUT_REVALIDATION", identity)
            return False
        if not r.get("centerline_mm"):
            fail("MISSING_REAL_ROUTE", identity)
            return False
        return True

    def transfer_ok(identity: str, left: str | None = None, right: str | None = None) -> bool:
        used_transfers.add(identity)
        t = transfers.get(identity)
        if (
            not t
            or t.get("geometry_status") != GEOMETRY
            or t.get("validation_status") not in (GEOMETRY, ASSUMED)
        ):
            fail("REQUIRED_TRANSFER_NOT_VERIFIED", identity)
            return False
        a, b = t["upstream_route"], t["downstream_route"]
        if a not in routes or b not in routes or (left is not None and (a, b) != (left, right)):
            fail("TRANSFER_ROUTE_BINDING_MISMATCH", identity)
            return False
        if t.get("geometry_context_hash") != current:
            fail("STALE_GEOMETRY_EVIDENCE", identity)
            return False
        if identity in replayed:
            return replayed[identity]
        # Recompute contact/load anchors and the declared operation-space proof;
        # an edited status label or a shared object ID cannot bridge a gap.
        actual = connect_transfer(c, parameters, routes[a], routes[b], endpoints, identity=identity)
        if canonical_hash(t) != canonical_hash(actual):
            fail("TRANSFER_WITNESS_MISMATCH", identity)
            return False
        if t["from"] != route_anchor(routes[a], "target", endpoints, parameters) or t[
            "to"
        ] != route_anchor(routes[b], "source", endpoints, parameters):
            fail("TRANSFER_ANCHOR_MISMATCH", identity)
            return False
        if (
            t["before_state"] != route_states(routes[a])[1]
            or t["after_state"] != route_states(routes[b])[0]
        ):
            fail("PAYLOAD_CARRIER_TRANSITION_MISMATCH", identity)
            return False
        replayed[identity] = True
        return True

    lines = []
    chains = f["product_chains"]
    if sorted(q["line"] for q in chains) != [f"PACK-{i:02}" for i in range(1, 7)]:
        fail("SIX_DISTINCT_MAIN_LINES_REQUIRED", "main")
    for chain in chains:
        legs = [q["route_id"] for q in chain["stages"]]
        number = int(chain["line"].split("-")[1])
        group = "N" if number <= 3 else "S"
        buffer = f"BUF-{group}-{(number - 1) % 3 + 1:02}"
        expected_legs = [
            "PRODUCT-RAW-PRI",
            "PRODUCT-PRI-PACKING",
            f"RAW-LINE-{number}",
            "PROCESS-" + chain["line"],
            f"PACK-PALLET-{number}",
            f"LINE-BUFFER-{number}",
            "BUFFER-SEC-" + buffer,
            "PRODUCT-SEC-DEPAL",
            "FILM-DEPAL-INFEED",
        ]
        film = sorted(
            (q for q in c["equipment"]["items"] if q["kind"] == "case_film_component"),
            key=lambda q: q["bbox_mm"][0],
        )
        for j, q in enumerate(film):
            expected_legs.append("INTERNAL-" + q["id"])
            if j + 1 < len(film):
                expected_legs.append("LINK-" + q["id"])
        expected_legs.extend(
            ["FILM-OUT-REPAL", "PRODUCT-REPAL-FINISHED", "PRODUCT-FINISHED-DISPATCH"]
        )
        ok = all([route_ok(i) for i in legs]) and legs == expected_legs
        if legs != expected_legs:
            fail("MAIN_PROCESS_SEQUENCE_INCOMPLETE", chain["id"])
        tids = chain["transfer_ids"]
        if len(tids) != len(legs) - 1:
            fail("EVERY_MAIN_JUNCTION_REQUIRES_A_TRANSFER", chain["id"])
            ok = False
        else:
            ok = (
                all([transfer_ok(t, a, b) for t, a, b in zip(tids, legs, legs[1:], strict=False)])
                and ok
            )
        lines.append(
            {
                "line": chain["line"],
                "status": "CONTINUOUS_CONDITIONAL_CHAIN" if ok else "INTERRUPTED_BOUNDED_SEARCH",
            }
        )

    auxiliary = []
    for kind, target in (("SECONDARY", "secondary_fruit_buffer"), ("FROZEN", "frozen_fruit_room")):
        bb = [b for b in f["auxiliary_branches"] if b["flow_kind"] == kind]
        ok = len(bb) == 1
        if ok:
            b = bb[0]
            ok = b["from_ref"] == "sorting_packaging_room" and b["to_ref"] == target
            ok = all([route_ok(i) for i in b["route_ids"]]) and ok
            ok = (
                len(b["route_ids"]) == 2
                and len(b["transfer_ids"]) == 2
                and b["route_ids"] == [kind + "-SORT-WORK", kind + "-WORK-STORE"]
                and transfer_ok(
                    b["transfer_ids"][0],
                    "RAW-LINE-" + ("1" if kind == "SECONDARY" else "2"),
                    b["route_ids"][0],
                )
                and transfer_ok(b["transfer_ids"][1], b["route_ids"][0], b["route_ids"][1])
                and ok
            )
            last = routes.get(b["route_ids"][-1], {})
            ok = (
                last.get("target_object") == b["stock_handoff_object"]
                and any(
                    q["id"] == b["stock_handoff_object"] and q["room"] == target
                    for q in c["equipment"]["items"]
                )
                and ok
            )
        if not ok:
            fail("AUXILIARY_BRANCH_INCOMPLETE", kind)
        auxiliary.append(
            {"flow_kind": kind, "status": "CONDITIONAL_CONNECTED" if ok else "INCOMPLETE"}
        )

    supply = f["case_supply"]
    assignments = supply["line_assignments"]
    supplied = (
        sorted(q["line"] for q in assignments) == [f"PACK-{i:02}" for i in range(1, 7)]
        and len({q["erector"] for q in assignments}) == 5
    )
    supplied = all([route_ok(q["route_id"]) for q in assignments]) and supplied
    supplied = (
        sorted(supply["blank_supply_routes"]) == [f"BLANK-ERECT-{i:02}" for i in range(1, 6)]
        and all([route_ok(i) for i in supply["blank_supply_routes"]])
        and supplied
    )
    supplied = (
        all(
            [
                transfer_ok("FORMING:" + q["id"])
                for q in c["equipment"]["items"]
                if q["kind"] == "case_erector"
            ]
        )
        and supplied
    )
    for assignment in assignments:
        r = routes.get(assignment["route_id"], {})
        if (r.get("source_object"), r.get("target_object")) != (
            assignment["erector"],
            assignment["line"],
        ):
            supplied = False
    if not supplied:
        fail("SELECTED_FIVE_TO_SIX_CASE_SUPPLY_INCOMPLETE", "PACKAGING")
    auxiliary.append(
        {"flow_kind": "PACKAGING", "status": "CONDITIONAL_CONNECTED" if supplied else "INCOMPLETE"}
    )
    if sorted(f["buffer_routes"]) != sorted(
        f"BUFFER-SEC-BUF-{g}-{i:02}" for g in ("N", "S") for i in range(1, 8)
    ) or not all([route_ok(i) for i in f["buffer_routes"]]):
        fail("ALL_FOURTEEN_BUFFER_CONNECTIONS_REQUIRED", "buffers")

    coverage = []
    for field, kind, count, expected_status in (
        ("equipment_aware_interior_paths", "interior", 10, "INTERIOR_FULL_WIDTH_PATH_VERIFIED"),
        ("storage_portal_interfaces", "storage", 6, "STORAGE_AISLE_TO_REAL_PORTAL_VERIFIED"),
    ):
        rows = c[field]
        expected = f["v11_required_coverage"][kind]
        ids = [coverage_identity(q, kind) for q in rows]
        ok = len(rows) == count and sorted(ids) == sorted(expected) and len(set(ids)) == count
        ok = (
            all(
                q["status"] == expected_status
                and q.get("geometry_context_hash") == current
                and bool(q["centerline_mm"])
                for q in rows
            )
            and ok
        )
        if not ok:
            fail("V11_REQUIRED_FUNCTION_NOT_RECOVERED_OR_STALE", kind)
        coverage.append(
            {
                "kind": kind,
                "required": count,
                "verified": sum(
                    q["status"] == expected_status and q.get("geometry_context_hash") == current
                    for q in rows
                ),
                "complete": ok,
            }
        )
    for key, passed in engineering_checks.items():
        if not passed:
            fail("ORIGINAL_ENGINEERING_CONSTRAINT_REJECTED", key)
    return {
        "accepted": not failures,
        "status": "CONDITIONAL_PROCESS_CANDIDATE"
        if not failures
        else "INTERRUPTED_PROCESS_CANDIDATE",
        "main_lines": lines,
        "main_line_count": sum(q["status"] == "CONTINUOUS_CONDITIONAL_CHAIN" for q in lines),
        "auxiliary_flows": auxiliary,
        "v11_coverage": coverage,
        "engineering_checks": dict(engineering_checks),
        "failures": failures,
        "selected_route_ids": sorted(selected),
        "alternative_route_ids": sorted(set(routes) - selected),
        "selected_transfer_ids": sorted(used_transfers),
        "counts": {
            "all_routes": len(routes),
            "selected_routes": len(selected),
            "exploratory_alternatives": len(set(routes) - selected),
            "conditional_machine_internal_routes": sum(
                q["purpose"] in ("PACKING_MACHINE_INTERNAL", "CARTON_MACHINE_INTERNAL")
                for q in routes.values()
            ),
            "conditional_short_handoffs": sum(
                q["purpose"] == "CARTON_SHORT_HANDOFF" for q in routes.values()
            ),
            "explicit_transfers": len(transfers),
        },
        "engineering_approval": "NOT_EVALUATED",
        "factory_applicability": "NOT_EVALUATED",
    }

"""Bounded CP-SAT geometry backend ported from hash-verified B0 model.

Continuous integer-mm rooms and portals; five-segment orthogonal corridor
search template, with separate corridor envelopes. INFEASIBLE refers only to
this restricted model, never the original engineering problem. No file input,
legacy candidate, selector hook, historical hint, or engineering budget mapping.
"""

from __future__ import annotations

import itertools
from decimal import Decimal as D
from typing import Any

from ortools.sat.python import cp_model

from cold_storage.modules.layout.domain.access_authority import COLD_ROOM, resolve_access_profile
from cold_storage.modules.layout.domain.composition_placement import _domain_faces
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError
from cold_storage.modules.layout.domain.site_geometry import PlacedRectangleV1

Limit = LayoutAuthorityError


def bounds(r: PlacedRectangleV1) -> tuple[int, int, int, int]:
    points = r.polygon_mm
    return (
        min(p[0] for p in points),
        min(p[1] for p in points),
        max(p[0] for p in points),
        max(p[1] for p in points),
    )


def envelopes(path: list[tuple[int, int]], width: int) -> list[tuple[int, int, int, int]]:
    half = width // 2
    result = []
    for a, b in zip(path, path[1:], strict=False):
        if a == b:
            continue
        if a[0] == b[0]:
            result.append((a[0] - half, min(a[1], b[1]), a[0] + width - half, max(a[1], b[1])))
        elif a[1] == b[1]:
            result.append((min(a[0], b[0]), a[1] - half, max(a[0], b[0]), a[1] + width - half))
        else:
            raise LayoutAuthorityError("NON_ORTHOGONAL_GLOBAL_ROUTE")
    result.extend((x - half, y - half, x + width - half, y + width - half) for x, y in path[1:-1])
    return result


def bind_native_portal_positions(
    model: Any,
    position: Any,
    low: Any,
    high: Any,
    width: int,
    active: Any,
    bound: int,
    name: str,
    *,
    center_only: bool = False,
) -> tuple[Any, ...]:
    """Original _portal_candidates offsets: centered, lower and upper.

    A validator-domain mapping, not a new engineering clearance or a claim
    that continuous portals outside this domain are physically impossible.
    For an active face high-low>=width, so integer division agrees exactly
    with the native nonnegative available-length // 2 computation.
    """
    half_available = model.new_int_var(-2 * bound, 2 * bound, name + "_half_available")
    model.add(high - low >= width).only_enforce_if(active)
    model.add_division_equality(half_available, high - low - width, 2)
    values = (
        (low + half_available + width // 2,)
        if center_only
        else (low + half_available + width // 2, low + width // 2, high - width + width // 2)
    )
    choices = [model.new_bool_var(name + "_offset" + str(i)) for i in range(len(values))]
    for flag, value in zip(choices, values, strict=True):
        model.add_implication(flag, active)
        model.add(position == value).only_enforce_if(flag)
    model.add(sum(choices) == active)
    return tuple(choices)


def bind_native_shared_portal(
    model: Any,
    position: Any,
    first: Any,
    second: Any,
    vertical: bool,
    width: int,
    active: Any,
    bound: int,
    name: str,
) -> tuple[Any, ...]:
    low = model.new_int_var(-2 * bound, 2 * bound, name + "_low")
    high = model.new_int_var(-2 * bound, 2 * bound, name + "_high")
    model.add_max_equality(low, [first["y" if vertical else "x"], second["y" if vertical else "x"]])
    model.add_min_equality(
        high, [first["Y" if vertical else "X"], second["Y" if vertical else "X"]]
    )
    return bind_native_portal_positions(
        model, position, low, high, width, active, bound, name, center_only=True
    )


def disjoint(m: Any, A: Any, B: Any, prefix: str, when: Any = None, closed: bool = False) -> None:
    flags = [m.new_bool_var(prefix + str(i)) for i in range(4)]
    gap = 1 if closed else 0
    for b, constraint in zip(
        flags,
        [
            A["X"] + gap <= B["x"],
            B["X"] + gap <= A["x"],
            A["Y"] + gap <= B["y"],
            B["Y"] + gap <= A["y"],
        ],
        strict=False,
    ):
        m.add(constraint).only_enforce_if([b] + ([] if when is None else [when]))
    m.add_bool_or(flags).only_enforce_if([] if when is None else [when])


def touch(m: Any, A: Any, B: Any, prefix: str, min_overlap: int = 1) -> list[Any]:
    flags = [m.new_bool_var(prefix + str(i)) for i in range(4)]
    for i, b in enumerate(flags):
        if i < 2:
            m.add(A["X"] == B["x"] if i == 0 else B["X"] == A["x"]).only_enforce_if(b)
            m.add(A["y"] + min_overlap <= B["Y"]).only_enforce_if(b)
            m.add(B["y"] + min_overlap <= A["Y"]).only_enforce_if(b)
        else:
            m.add(A["Y"] == B["y"] if i == 2 else B["Y"] == A["y"]).only_enforce_if(b)
            m.add(A["x"] + min_overlap <= B["X"]).only_enforce_if(b)
            m.add(B["x"] + min_overlap <= A["X"]).only_enforce_if(b)
    m.add_bool_or(flags)
    return flags


class GlobalModel:
    def _new_cp_model(self) -> Any:
        return cp_model.CpModel()

    def __init__(self, c: Any, handoff: Any, bank: int = 1) -> None:
        self.c = c
        self.handoff = handoff
        self.bank = bank
        self.m = self._new_cp_model()
        m = self.m
        self.rooms: dict[str, dict[str, Any]] = {}
        self.interfaces: list[dict[str, Any]] = []
        sx, sy, sr, st = c.sitebox
        W = sr - sx
        H = st - sy
        ix = []
        iy = []
        nw: Any
        nd: Any
        for role, auth in c.binding.dimension_authorities.items():
            c.ledger.charge("MODEL_ROLE_VARIABLES", 12)
            x = m.new_int_var(sx, sr, role + "_x")
            y = m.new_int_var(sy, st, role + "_y")
            rot = m.new_bool_var(role + "_rot90")
            if 90 not in auth["rotation_allowed"]:
                m.add(rot == 0)
            if 0 not in auth["rotation_allowed"]:
                m.add(rot == 1)
            if auth["dimension_mode"] == "FLEXIBLE_RECTANGLE":
                # Full bounded width/depth space induced by the actual site; no S4 shape lock.
                nw = m.new_int_var(1, max(W, H), role + "_nominal_w")
                nd = m.new_int_var(1, max(W, H), role + "_nominal_d")
                area = m.new_int_var(1, max(W, H) ** 2, role + "_area")
                m.add_multiplication_equality(area, [nw, nd])
                required = int(
                    (D(str(auth["required_area_m2"])) * 1000000).to_integral_value(
                        rounding="ROUND_CEILING"
                    )
                )
                m.add(area >= required)
                if any(
                    auth.get(k) is not None
                    for k in (
                        "aspect_ratio_bounds",
                        "min_width_m",
                        "min_depth_m",
                        "max_width_m",
                        "max_depth_m",
                    )
                ):
                    raise Limit("UNMODELED_FLEXIBLE_DIMENSION_RULE")
            else:
                nw = int(D(str(auth["geometry"]["width_m"])) * 1000)
                nd = int(D(str(auth["geometry"]["depth_m"])) * 1000)
            w = m.new_int_var(1, W, role + "_physical_w")
            d = m.new_int_var(1, H, role + "_physical_d")
            m.add(w == nw).only_enforce_if(rot.Not())
            m.add(d == nd).only_enforce_if(rot.Not())
            m.add(w == nd).only_enforce_if(rot)
            m.add(d == nw).only_enforce_if(rot)
            X = m.new_int_var(sx + 1, sr, role + "_right")
            Y = m.new_int_var(sy + 1, st, role + "_top")
            m.add(x + w == X)
            m.add(y + d == Y)
            R = dict(x=x, y=y, X=X, Y=Y, w=w, d=d, rot=rot, nw=nw, nd=nd)
            self.rooms[role] = R
            ix.append(m.new_interval_var(x, w, X, role + "_ix"))
            iy.append(m.new_interval_var(y, d, Y, role + "_iy"))
            for i, (ox, oy, or_, ot) in enumerate(c.obsboxes):
                disjoint(
                    m, R, dict(x=ox, y=oy, X=or_, Y=ot), role + "_obstacle" + str(i), closed=True
                )
                c.ledger.charge("MODEL_OBSTACLE_SEPARATION", 4)
        m.add_no_overlap_2d(ix, iy)
        self.geometry_constraint_count = len(m.proto.constraints)
        self.must_choices: dict[tuple[str, str], tuple[Any, ...]] = {}
        for a, b in c.must:
            self.must_choices[a, b] = tuple(touch(m, self.rooms[a], self.rooms[b], a + "_" + b))
            c.ledger.charge("MODEL_MUST_DISJUNCTION", 12)
        self.must_constraint_count = len(m.proto.constraints)
        A = self.rooms[c.pack_req["from_ref"]]
        B = self.rooms[c.pack_req["to_ref"]]
        portal = int(c.profile.portal_clear_width_m * 1000)
        cw = int(c.profile.corridor_clear_width_m * 1000)
        for corridor in (False, True):
            for side in ("EAST", "WEST", "NORTH", "SOUTH"):
                active = m.new_bool_var(f"interface_{corridor}_{side}")
                vertical = side in ("EAST", "WEST")
                span = cw if corridor else portal
                center = m.new_int_var(
                    sy if vertical else sx, st if vertical else sr, "portal_center"
                )
                lower = center - span // 2
                upper = lower + span
                portal_choices = []
                for R in (A, B):
                    m.add(lower >= R["y"] if vertical else lower >= R["x"]).only_enforce_if(active)
                    m.add(upper <= R["Y"] if vertical else upper <= R["X"]).only_enforce_if(active)
                    if corridor:
                        portal_choices.append(
                            bind_native_portal_positions(
                                m,
                                center,
                                R["y" if vertical else "x"],
                                R["Y" if vertical else "X"],
                                portal,
                                active,
                                max(sr, st),
                                "packaging_native",
                            )
                        )
                if not corridor:
                    portal_choices.append(
                        bind_native_shared_portal(
                            m,
                            center,
                            A,
                            B,
                            vertical,
                            portal,
                            active,
                            max(sr, st),
                            "packaging_shared",
                        )
                    )
                # Existing access authority resolves role-relative LONG / SHORT faces.
                m.add(A["d"] >= A["w"] if vertical else A["w"] >= A["d"]).only_enforce_if(active)
                m.add(B["d"] <= B["w"] if vertical else B["w"] <= B["d"]).only_enforce_if(active)
                fa = (
                    A["x"]
                    if side == "EAST"
                    else A["X"]
                    if side == "WEST"
                    else A["y"]
                    if side == "NORTH"
                    else A["Y"]
                )
                fb = (
                    B["X"]
                    if side == "EAST"
                    else B["x"]
                    if side == "WEST"
                    else B["Y"]
                    if side == "NORTH"
                    else B["y"]
                )
                if not corridor:
                    m.add(fa == fb).only_enforce_if(active)
                else:
                    low = fb if side in ("EAST", "NORTH") else fa
                    high = fa if side in ("EAST", "NORTH") else fb
                    gap = m.new_int_var(0, max(W, H), "corridor_gap")
                    m.add(gap == high - low).only_enforce_if(active)
                    m.add(gap >= 1).only_enforce_if(active)
                    E = dict(
                        x=low if vertical else lower,
                        y=lower if vertical else low,
                        X=high if vertical else upper,
                        Y=upper if vertical else high,
                    )
                    for term, bound in ((E["x"], sx), (E["y"], sy)):
                        m.add(term >= bound).only_enforce_if(active)
                    m.add(E["X"] <= sr).only_enforce_if(active)
                    m.add(E["Y"] <= st).only_enforce_if(active)
                    for R in self.rooms.values():
                        disjoint(m, E, R, "corr_room", when=active)
                    for ox, oy, or_, ot in c.obsboxes:
                        disjoint(
                            m,
                            E,
                            dict(x=ox, y=oy, X=or_, Y=ot),
                            "corr_obs",
                            when=active,
                            closed=True,
                        )
                self.interfaces.append(
                    dict(
                        active=active,
                        corridor=corridor,
                        side=side,
                        center=center,
                        fa=fa,
                        fb=fb,
                        vertical=vertical,
                        portal_choices=tuple(portal_choices),
                    )
                )
                c.ledger.charge("MODEL_INTERFACE_CASE", 50)
        m.add_exactly_one(i["active"] for i in self.interfaces)
        self.faces = _domain_faces(handoff, bank)
        axis = handoff.process_axis.value
        sign = 1 if handoff.process_direction.value == "POSITIVE" else -1
        centers = {}
        for k, R in self.rooms.items():
            for ax in ("X", "Y"):
                center = m.new_int_var(0, max(sr, st), k + "_center" + ax)
                m.add_division_equality(
                    center, (R["x"] + R["X"]) if ax == "X" else (R["y"] + R["Y"]), 2
                )
                centers[k, ax] = center
        S = centers["sorting_packaging_room", axis]
        for k in self.faces:
            ax, sgn = self.faces[k]
            m.add(sgn * (centers[k, ax] - centers["sorting_packaging_room", ax]) >= 1)

        def mean(roles: tuple[str, ...]) -> Any:
            v = m.new_int_var(0, max(sr, st), "group_center")
            m.add_division_equality(v, sum(centers[k, axis] for k in roles), len(roles))
            return v

        raw = mean(("raw_fruit_buffer", "primary_precooling_room"))
        core = mean(("sorting_packaging_room", "secondary_precooling_room", "coating_room"))
        finish = mean(("finished_goods_room", "shipping_channel"))
        family = handoff.family.value
        if family == "LINEAR_BANDED":
            m.add(sign * (core - raw) >= 1)
            m.add(sign * (finish - core) >= 1)
        elif family == "CENTRAL_PROCESS_CORE":
            m.add(sign * (S - raw) >= 1)
            m.add(sign * (finish - S) >= 1)
        else:
            flow = (
                "raw_fruit_buffer",
                "primary_precooling_room",
                "sorting_packaging_room",
                "secondary_precooling_room",
                "coating_room",
                "finished_goods_room",
                "shipping_channel",
            )
            for a, b in zip(flow, flow[1:], strict=False):
                m.add(sign * (centers[b, axis] - centers[a, axis]) >= 0)

    def export(self, solver: Any) -> tuple[dict[str, PlacedRectangleV1], dict[str, Any]]:
        state = {}
        for k, R in self.rooms.items():
            self.c.ledger.charge("EXPORT_GEOMETRY", 6)
            nw = R["nw"] if isinstance(R["nw"], int) else solver.value(R["nw"])
            nd = R["nd"] if isinstance(R["nd"], int) else solver.value(R["nd"])
            state[k] = PlacedRectangleV1(
                k,
                D(solver.value(R["x"])) / 1000,
                D(solver.value(R["y"])) / 1000,
                D(nw) / 1000,
                D(nd) / 1000,
                solver.value(R["rot"]) * 90,
            )
        i = next(i for i in self.interfaces if solver.boolean_value(i["active"]))
        center = solver.value(i["center"])
        fa = solver.value(i["fa"])
        fb = solver.value(i["fb"])
        pw = int(self.c.profile.portal_clear_width_m * 1000)
        cw = int(self.c.profile.corridor_clear_width_m * 1000)
        pa = (
            [(fa, center - pw // 2), (fa, center + pw - pw // 2)]
            if i["vertical"]
            else [(center - pw // 2, fa), (center + pw - pw // 2, fa)]
        )
        pb = (
            [(fb, center - pw // 2), (fb, center + pw - pw // 2)]
            if i["vertical"]
            else [(center - pw // 2, fb), (center + pw - pw // 2, fb)]
        )
        E = (
            None
            if not i["corridor"]
            else (min(fa, fb), center - cw // 2, max(fa, fb), center + cw - cw // 2)
            if i["vertical"]
            else (center - cw // 2, min(fa, fb), center + cw - cw // 2, max(fa, fb))
        )
        return state, dict(
            mode="CORRIDOR_MEDIATED" if i["corridor"] else "DIRECT_SHARED_EDGE",
            side=i["side"],
            portal_packaging_mm=pa,
            portal_sorting_mm=pb,
            corridor_envelope_mm=E,
            centerline_mm=[]
            if not i["corridor"]
            else [(fa, center), (fb, center)]
            if i["vertical"]
            else [(center, fa), (center, fb)],
            route_shape="STRAIGHT_ONLY",
            turn_count=0,
        )


class AccessModel(GlobalModel):
    def __init__(self, c: Any, h: Any, separate: bool = True) -> None:
        super().__init__(c, h)
        E: Any
        b: Any
        m = self.m
        self.routes: list[dict[str, Any]] = []
        allenv = []
        sx, sy, sr, st = c.sitebox

        def var(name: str) -> Any:
            return m.new_int_var(-max(sr, st), 2 * max(sr, st), name)

        def endpoint(
            role: str, pw: int, cw: int, active: Any, tag: str, edge: str | None = None
        ) -> Any:
            px, py, qx, qy = [var(tag + k) for k in ("px", "py", "qx", "qy")]
            options = []
            offsets = []
            if role in c.entrances:
                a, b = c.entrances[role]
                vertical = a[0] == b[0]
                fixed = a[0] if vertical else a[1]
                lo = min(a[1], b[1]) if vertical else min(a[0], b[0])
                hi = max(a[1], b[1]) if vertical else max(a[0], b[0])
                if vertical:
                    if fixed == sx:
                        normal = (1, 0)
                    elif fixed == sr:
                        normal = (-1, 0)
                    else:
                        raise Limit("ENTRANCE_BOUNDARY_REFERENCE_INVALID")
                elif fixed == sy:
                    normal = (0, 1)
                elif fixed == st:
                    normal = (0, -1)
                else:
                    raise Limit("ENTRANCE_BOUNDARY_REFERENCE_INVALID")
                faces = [(vertical, fixed, lo, hi, normal)]
            else:
                R = self.rooms[role]
                faces = [
                    (True, R["x"], R["y"], R["Y"], (-1, 0)),
                    (True, R["X"], R["y"], R["Y"], (1, 0)),
                    (False, R["y"], R["x"], R["X"], (0, -1)),
                    (False, R["Y"], R["x"], R["X"], (0, 1)),
                ]
            for n, (vertical, fixed, lo, hi, normal) in enumerate(faces):
                b = m.new_bool_var(tag + "face" + str(n))
                options.append(b)
                m.add_implication(b, active)
                pos = py if vertical else px
                m.add(px == fixed if vertical else py == fixed).only_enforce_if(b)
                m.add(2 * pos >= 2 * lo + pw).only_enforce_if(b)
                m.add(2 * pos <= 2 * hi - pw).only_enforce_if(b)
                offsets.append(
                    bind_native_portal_positions(
                        m, pos, lo, hi, pw, b, max(sr, st), tag + "_native" + str(n)
                    )
                )
                m.add(qx == px + normal[0] * (cw // 2)).only_enforce_if(b)
                m.add(qy == py + normal[1] * (cw // 2)).only_enforce_if(b)
                if edge and role in self.rooms:
                    R = self.rooms[role]
                    length = R["d"] if vertical else R["w"]
                    other = R["w"] if vertical else R["d"]
                    m.add(
                        length >= other if edge == "LONG_EDGE" else length <= other
                    ).only_enforce_if(b)
            m.add(sum(options) == active)
            return (px, py), (qx, qy), options, offsets

        def env(
            A: Any, B: Any, cw: int, act: Any, tag: str, corner: bool = False
        ) -> dict[str, Any]:
            x, y, X, Y = [var(tag + k) for k in ("x", "y", "X", "Y")]
            half = cw // 2
            if corner:
                m.add(x == A[0] - half)
                m.add(A[0] + cw - half == X)
                m.add(y == A[1] - half)
                m.add(A[1] + cw - half == Y)
            else:
                vertical = m.new_bool_var(tag + "vertical")
                m.add(A[0] == B[0]).only_enforce_if([act, vertical])
                m.add(A[1] == B[1]).only_enforce_if([act, vertical.Not()])
                lowx, highx, lowy, highy = [
                    var(tag + k) for k in ("lowx", "highx", "lowy", "highy")
                ]
                m.add_min_equality(lowx, [A[0], B[0]])
                m.add_max_equality(highx, [A[0], B[0]])
                m.add_min_equality(lowy, [A[1], B[1]])
                m.add_max_equality(highy, [A[1], B[1]])
                for cond, vals in (
                    (vertical, (A[0] - half, lowy, A[0] + cw - half, highy)),
                    (vertical.Not(), (lowx, A[1] - half, highx, A[1] + cw - half)),
                ):
                    for t, v in zip((x, y, X, Y), vals, strict=False):
                        m.add(t == v).only_enforce_if(cond)
            E = dict(x=x, y=y, X=X, Y=Y, active=act)
            for term, limit, lower in (
                (x, sx, True),
                (y, sy, True),
                (X, sr, False),
                (Y, st, False),
            ):
                m.add(term >= limit if lower else term <= limit).only_enforce_if(act)
            for k, R in self.rooms.items():
                disjoint(m, E, R, tag + k, when=act)
                c.ledger.charge("MODEL_ROUTE_ROOM_SEPARATION", 4)
            for i, obstacle in enumerate(c.obsboxes):
                disjoint(
                    m,
                    E,
                    dict(zip(("x", "y", "X", "Y"), obstacle, strict=True)),
                    tag + "obs" + str(i),
                    when=act,
                    closed=True,
                )
                c.ledger.charge("MODEL_ROUTE_OBSTACLE", 4)
            return E

        for ri, req in enumerate(c.binding.access_requirements):
            if req["flow_kind"] == "TRUCK" or req["identity"] == c.pack_req["identity"]:
                continue
            p = resolve_access_profile(req["profile_identity"])
            pw = int(p.portal_clear_width_m * 1000)
            cw = int(p.corridor_clear_width_m * 1000)
            if req.get("cold_room_refs"):
                pw = max(pw, int(resolve_access_profile(COLD_ROOM).portal_clear_width_m * 1000))
            corridor = m.new_bool_var("route" + str(ri) + "corridor")
            direct = []
            A = self.rooms.get(req["from_ref"])
            B = self.rooms[req["to_ref"]]
            # Direct door is a continuous shared segment with original portal width.
            if req["direct_allowed"] and A:
                for side in range(4):
                    b = m.new_bool_var("direct" + str(ri) + "_" + str(side))
                    t = var("direct_center")
                    direct.append(dict(active=b, side=side, center=t))
                    m.add_implication(b, corridor.Not())
                    if side < 2:
                        m.add(A["X"] == B["x"] if side == 0 else A["x"] == B["X"]).only_enforce_if(
                            b
                        )
                        for R in (A, B):
                            m.add(2 * t >= 2 * R["y"] + pw).only_enforce_if(b)
                            m.add(2 * t <= 2 * R["Y"] - pw).only_enforce_if(b)
                    else:
                        m.add(A["Y"] == B["y"] if side == 2 else A["y"] == B["Y"]).only_enforce_if(
                            b
                        )
                        for R in (A, B):
                            m.add(2 * t >= 2 * R["x"] + pw).only_enforce_if(b)
                            m.add(2 * t <= 2 * R["X"] - pw).only_enforce_if(b)
                    choices = bind_native_shared_portal(
                        m, t, A, B, side < 2, pw, b, max(sr, st), "direct_native"
                    )
                    direct[-1]["portal_choices"] = choices
            m.add(sum(d["active"] for d in direct) + corridor == 1)
            if not req["corridor_allowed"]:
                m.add(corridor == 0)
            P, Q, ff, fo = endpoint(req["from_ref"], pw, cw, corridor, "from" + str(ri))
            T, U, ft, to = endpoint(req["to_ref"], pw, cw, corridor, "to" + str(ri))
            horizontal = m.new_bool_var("middle_HVH" + str(ri))
            b1 = (var("bendx1"), var("bendy1"))
            b2 = (var("bendx2"), var("bendy2"))
            bend = var("middle_coordinate")
            for cond, vals in (
                (horizontal, (bend, Q[1], bend, U[1])),
                (horizontal.Not(), (Q[0], bend, U[0], bend)),
            ):
                for t, v in zip((*b1, *b2), vals, strict=False):
                    m.add(t == v).only_enforce_if(cond)
            points = [P, Q, b1, b2, U, T]
            E = []
            for j, (a, b) in enumerate(zip(points, points[1:], strict=False)):
                E.append(env(a, b, cw, corridor, f"r{ri}s{j}"))
            for j, a in enumerate(points[1:-1]):
                E.append(env(a, a, cw, corridor, f"r{ri}c{j}", True))
            self.routes.append(
                dict(
                    req=req,
                    cw=cw,
                    pw=pw,
                    corridor=corridor,
                    direct=direct,
                    points=points,
                    envelopes=E,
                    from_faces=ff,
                    to_faces=ft,
                    from_offsets=fo,
                    to_offsets=to,
                )
            )
            allenv.append((req["identity"], E))
        # Packaging envelope remains selected by inherited original authority model.
        for i in self.interfaces:
            if i["corridor"]:
                half = int(c.profile.corridor_clear_width_m * 1000) // 2
                low = i["fb"] if i["side"] in ("EAST", "NORTH") else i["fa"]
                high = i["fa"] if i["side"] in ("EAST", "NORTH") else i["fb"]
                center = i["center"]
                E = dict(
                    x=low if i["vertical"] else center - half,
                    y=center - half if i["vertical"] else low,
                    X=high if i["vertical"] else center + half,
                    Y=center + half if i["vertical"] else high,
                    active=i["active"],
                )
                allenv.append((c.pack_req["identity"], [E]))
        if separate:
            # Stronger, explicitly restricted template avoids unapproved shared corridors.
            for (ka, EA), (kb, EB) in itertools.combinations(allenv, 2):
                if ka == kb:
                    continue
                for a in EA:
                    for b in EB:
                        both = m.new_bool_var("two_corridors")
                        m.add_bool_and([a["active"], b["active"]]).only_enforce_if(both)
                        m.add_bool_or([a["active"].Not(), b["active"].Not(), both])
                        disjoint(m, a, b, "coexist", when=both)
                        c.ledger.charge("MODEL_ROUTE_COEXISTENCE", 4)
        self.separate = separate

    def export_routes(
        self, s: Any, state: dict[str, PlacedRectangleV1], interface: dict[str, Any]
    ) -> list[dict[str, Any]]:
        result = []
        for r in self.routes:
            req = r["req"]
            path: list[tuple[int, int]] = []
            if s.boolean_value(r["corridor"]):
                for P in r["points"]:
                    a = tuple(s.value(t) for t in P)
                    if path and a == path[-1]:
                        continue
                    if len(path) > 1 and (
                        (path[-2][0] == path[-1][0] == a[0]) or (path[-2][1] == path[-1][1] == a[1])
                    ):
                        path[-1] = a
                    else:
                        path.append(a)
                E = envelopes(path, r["cw"])
                mode = "CORRIDOR_MEDIATED"
                pa = path[0]
                pb = path[-1]
            else:
                d = next(d for d in r["direct"] if s.boolean_value(d["active"]))
                A = bounds(state[req["from_ref"]])
                t = s.value(d["center"])
                side = d["side"]
                pa = pb = (
                    (A[2] if side == 0 else A[0], t)
                    if side < 2
                    else (t, A[3] if side == 2 else A[1])
                )
                E = []
                mode = "DIRECT_SHARED_EDGE"
            result.append(
                dict(
                    requirement_identity=req["identity"],
                    from_ref=req["from_ref"],
                    to_ref=req["to_ref"],
                    topology=mode,
                    portal_from_center_mm=pa,
                    portal_to_center_mm=pb,
                    portal_width_mm=r["pw"],
                    width_mm=r["cw"],
                    path_mm=path,
                    envelopes_mm=E,
                    turn_count=max(0, len(path) - 2),
                    length_mm=sum(
                        abs(b[0] - a[0]) + abs(b[1] - a[1])
                        for a, b in zip(path, path[1:], strict=False)
                    ),
                )
            )
        pa = interface["portal_packaging_mm"]
        pb = interface["portal_sorting_mm"]

        def center(p: Any) -> tuple[int, ...]:
            return tuple((a + b) // 2 for a, b in zip(*p, strict=False))

        path = interface["centerline_mm"]
        result.append(
            dict(
                requirement_identity=self.c.pack_req["identity"],
                from_ref=self.c.pack_req["from_ref"],
                to_ref=self.c.pack_req["to_ref"],
                topology=interface["mode"],
                portal_from_center_mm=center(pa),
                portal_to_center_mm=center(pb),
                portal_width_mm=int(self.c.profile.portal_clear_width_m * 1000),
                width_mm=int(self.c.profile.corridor_clear_width_m * 1000),
                path_mm=path,
                envelopes_mm=[]
                if not path
                else envelopes(path, int(self.c.profile.corridor_clear_width_m * 1000)),
                turn_count=0,
                length_mm=sum(
                    abs(b[0] - a[0]) + abs(b[1] - a[1])
                    for a, b in zip(path, path[1:], strict=False)
                ),
            )
        )
        return result

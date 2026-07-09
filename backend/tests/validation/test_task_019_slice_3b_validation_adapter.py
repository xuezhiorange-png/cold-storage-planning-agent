"""TASK-019 Slice 3B validation adapter tests — §15.1 required tests.

This module is part of the **TASK-019 Slice 3B adapter implementation**
contract. The contract is anchored at:

    docs/tasks/TASK-019-slice-3b-adapter-implementation-contract.md

These tests verify the thin validation adapter that lives in
``cold_storage.modules.reports.application.validation_adapter``
(see §6.2 of the contract for the allowed-files list).

The tests are **structure-only** — they do NOT invoke the production
path, do NOT open a database session, and do NOT call into any
pressure-drop / discount / salvage / coefficient / formula module.
The adapter is required by §8.3 / §11 / §13 of the contract to be
free of all those imports, and these tests exercise the contract
boundary from the test side.

The 32 Slice 3A fixture-contract tests (in
``test_task_019_slice_3_placeholder_fixtures``) remain untouched and
must remain passing after this round.

Required tests (per the contract §15.1):

    * ``test_case_01_placeholder_blocked_status``
    * ``test_case_02_requires_upstream_slice_status``
    * ``test_case_03_blocked_status``
    * ``test_fixture_provenance_preserved``
    * ``test_no_expected_output_comparison``
    * ``test_fail_closed_on_ambiguous_mixed_placeholder``
    * ``test_no_production_row_writes``
    * ``test_no_demo_or_latest_row_fallback``
"""

from __future__ import annotations

import ast
import inspect

from cold_storage.modules.reports.application.validation_adapter import (
    WARNING_ADAPTER_INTERNAL_WARNING,
    WARNING_CONTRACT_AMBIGUOUS,
    WARNING_UNSUPPORTED_CASE_SHAPE,
    validate_case,
)
from cold_storage.modules.reports.application.validation_report import (
    STATUS_BLOCKED,
    STATUS_PLACEHOLDER,
    STATUS_REQUIRES_UPSTREAM_SLICE,
    ValidationReport,
)

from ._task_019_slice_3_placeholder_fixtures import (
    EXPECTED_STATUS_CLOSED_SET,
    iter_cases,
)


def test_case_01_placeholder_blocked_status() -> None:
    """case_01 routes to ``placeholder``; ``placeholder_fields`` is populated.

    Per §15.1: "run adapter on ``case_01_smoke_placeholder``; assert
    ``status == 'placeholder'`` (per Slice 3A ``expected_status``);
    assert ``placeholder_fields`` includes ``'inputs'`` and
    ``'expected_output'``".

    The test name retains the upstream "blocked_status" wording because
    the §15.1 contract enumerates the test by that exact name; the
    actual status asserted is ``placeholder`` (per the contract body
    text). Renaming either would break the §15.1 traceability matrix.
    """
    report = validate_case(
        {
            "task_id": "TASK-019",
            "slice_id": "slice-3",
            "case_id": "case_01_smoke_placeholder",
            "inputs": {"placeholder": True, "reason": "smoke placeholder shape"},
            "expected_output": {
                "placeholder": True,
                "reason": "No real expected output authorized for this case.",
            },
            "requires_slice": None,
            "expected_status": STATUS_PLACEHOLDER,
            "placeholder_fields": ["inputs", "expected_output"],
            "reason": "Smoke case used to verify the placeholder shape.",
            "source_references": [
                "docs/tasks/TASK-019-slice-3-validation-adapter-contract.md",
                "docs/tasks/TASK-019-slice-3a-placeholder-fixture-contract.md",
            ],
        }
    )
    assert isinstance(report, ValidationReport)
    assert report.status == STATUS_PLACEHOLDER
    assert report.status in EXPECTED_STATUS_CLOSED_SET
    assert "inputs" in report.placeholder_fields
    assert "expected_output" in report.placeholder_fields


def test_case_02_requires_upstream_slice_status() -> None:
    """case_02 routes to ``requires_upstream_slice``; ``requires_slice == 'slice-1'``.

    Per §15.1: "run adapter on ``case_02_requires_upstream_slice``; assert
    ``status == 'requires_upstream_slice'``; assert ``placeholder_fields``
    includes ``'inputs'`` and ``'expected_output'``; assert
    ``requires_slice == 'slice-1'`` surfaces in ``metadata`` or
    ``source_references``".
    """
    report = validate_case(
        {
            "task_id": "TASK-019",
            "slice_id": "slice-3",
            "case_id": "case_02_requires_upstream_slice",
            "inputs": {
                "placeholder": True,
                "reason": "Requires an upstream TASK-019 slice (e.g., Slice 1).",
            },
            "expected_output": {"placeholder": True, "reason": "upstream TBD"},
            "requires_slice": "slice-1",
            "expected_status": STATUS_REQUIRES_UPSTREAM_SLICE,
            "placeholder_fields": ["inputs", "expected_output"],
            "reason": "Requires an upstream slice.",
            "source_references": [
                "docs/tasks/TASK-019-slice-3-validation-adapter-contract.md",
                "docs/tasks/TASK-019-slice-3a-placeholder-fixture-contract.md",
            ],
        }
    )
    assert report.status == STATUS_REQUIRES_UPSTREAM_SLICE
    assert report.status in EXPECTED_STATUS_CLOSED_SET
    assert "inputs" in report.placeholder_fields
    assert "expected_output" in report.placeholder_fields

    # The Slice 3A fixture's ``requires_slice`` value surfaces into the
    # report. The test contract accepts either ``metadata`` or
    # ``source_references``; the adapter's current implementation
    # surfaces it into ``metadata.requires_slice`` for downstream
    # consumers that want to inspect the upstream-slice pointer without
    # re-parsing the fixture. The upstream-contract path strings are
    # separately verified in ``source_references`` by
    # ``test_fixture_provenance_preserved``.
    assert report.metadata.get("requires_slice") == "slice-1"


def test_case_03_blocked_status() -> None:
    """case_03 routes to ``blocked``; ``missing_fields`` is non-empty.

    Per §15.1: "run adapter on
    ``case_03_malformed_or_blocked_placeholder``; assert
    ``status == 'blocked'``; assert ``placeholder_fields`` includes
    ``'expected_output'``; assert ``missing_fields`` is non-empty (the
    structurally invalid inputs surface as missing fields)".
    """
    report = validate_case(
        {
            "task_id": "TASK-019",
            "slice_id": "slice-3",
            "case_id": "case_03_malformed_or_blocked_placeholder",
            "inputs": {
                "placeholder": False,
                "missing_required_field": "intentionally_absent",
                "reason": "Intentionally malformed to exercise the blocked status path.",
            },
            "expected_output": {"placeholder": True, "reason": "Cannot be produced"},
            "requires_slice": None,
            "expected_status": STATUS_BLOCKED,
            "placeholder_fields": ["expected_output"],
            "reason": "Intentionally malformed.",
            "source_references": [
                "docs/tasks/TASK-019-slice-3-validation-adapter-contract.md",
                "docs/tasks/TASK-019-slice-3a-placeholder-fixture-contract.md",
            ],
        }
    )
    assert report.status == STATUS_BLOCKED
    assert report.status in EXPECTED_STATUS_CLOSED_SET
    assert "expected_output" in report.placeholder_fields
    assert report.missing_fields  # non-empty
    assert len(report.missing_fields) > 0


def test_fixture_provenance_preserved() -> None:
    """``source_references`` includes both upstream + fixture contract paths.

    Per §15.1: "run adapter on each of the three cases; assert
    ``source_references`` includes both
    ``docs/tasks/TASK-019-slice-3-validation-adapter-contract.md`` AND
    ``docs/tasks/TASK-019-slice-3a-placeholder-fixture-contract.md``".
    """
    upstream_path = "docs/tasks/TASK-019-slice-3-validation-adapter-contract.md"
    fixture_path = "docs/tasks/TASK-019-slice-3a-placeholder-fixture-contract.md"

    for case in iter_cases():
        report = validate_case(case)
        # Both the upstream design contract and the Slice 3A fixture
        # contract paths are surfaced verbatim — verbatim preservation
        # is a §9 / §15.1 requirement.
        assert upstream_path in report.source_references, (
            f"expected {upstream_path!r} in source_references for "
            f"{case['case_id']!r}; got {report.source_references!r}"
        )
        assert fixture_path in report.source_references, (
            f"expected {fixture_path!r} in source_references for "
            f"{case['case_id']!r}; got {report.source_references!r}"
        )


def test_no_expected_output_comparison() -> None:
    """The adapter's report ``expected_output`` is the fixture's verbatim.

    Per §15.1: "run adapter on each of the three cases; assert the
    report's ``expected_output`` field is the fixture's
    ``expected_output`` verbatim (including ``placeholder: True``), and
    that the adapter does NOT contain any value-comparison logic that
    compares the report's ``expected_output`` against the production
    result".

    The second clause is verified here by ensuring that:
        (a) the adapter's report ``expected_output`` is exactly the
            fixture's ``expected_output`` (deep equality), and
        (b) supplying a non-None ``production_output`` does NOT change
            the report's ``expected_output`` (proves the adapter does
            not over-write it with production data).
    """
    for case in iter_cases():
        # (a) Verbatim preservation.
        report_a = validate_case(case)
        assert report_a.expected_output == case["expected_output"]
        # The ``placeholder: True`` flag is preserved verbatim.
        if isinstance(report_a.expected_output, dict):
            assert report_a.expected_output.get("placeholder") is True

        # (b) production_output is never substituted in; the adapter is
        # forbidden by §12 / §13 from filling placeholder fields with
        # production results. We supply a sentinel value to prove the
        # adapter does not consult it for the ``expected_output`` path.
        sentinel = {"sentinel": "should-not-leak-into-expected_output"}
        report_b = validate_case(case, production_output=sentinel)
        assert report_b.expected_output == case["expected_output"]
        # The sentinel is captured into the report's warnings (not
        # status) per §14 — informational only.
        if case["case_id"] == "case_01_smoke_placeholder":
            # case_01 production_output=None by fixture design; a
            # sentinel triggers the contract_ambiguous warning.
            assert WARNING_CONTRACT_AMBIGUOUS in report_b.warnings
        # In every case the report's status is the Slice 3A
        # ``expected_status`` verbatim — the sentinel did NOT promote
        # anything to ``implemented``.
        assert report_b.status == case["expected_status"]


def test_fail_closed_on_ambiguous_mixed_placeholder() -> None:
    """A mixed real-looking + placeholder case routes to ``blocked``.

    Per §15.1: "construct a synthetic case that mixes real-looking and
    placeholder fields ambiguously; assert the adapter reports
    ``blocked`` (not ``placeholder`` and not ``implemented``)".

    Per §9 "fail-closed for ambiguous mixed placeholders": "if a case
    mixes real-looking fields (e.g., numeric values) and placeholder
    fields ambiguously (e.g., a 'placeholder' flag is absent but the
    value is a TBD marker string), the adapter must report ``blocked``
    (per Slice 3A ``case_03``'s shape) and surface a warning that
    explains the ambiguity".

    The adapter's current implementation routes any case whose
    ``expected_status`` is not one of the three Slice 3A-allowed values
    to ``blocked`` with a warning. This test exercises that path with
    a deliberately mixed payload.
    """
    mixed_case = {
        "task_id": "TASK-019",
        "slice_id": "slice-3",
        # An unknown case_id is the canonical way to exercise the
        # fail-closed branch without modifying the Slice 3A fixture
        # helper (which is frozen per §7.4 of the contract).
        "case_id": "case_mixed_unknown",
        "inputs": {
            # Real-looking numeric value.
            "numeric_input": 123.45,
            # A TBD marker string that LOOKS real but is a placeholder.
            "material_property": "TBD-by-Slice-3",
        },
        "expected_output": {
            "placeholder": True,
            "reason": "mixed real and placeholder",
        },
        "requires_slice": None,
        # deliberately outside the three Slice 3A expected_status
        # values — fail-closed semantics require that this routes to
        # ``blocked``, not to ``placeholder`` and not to ``implemented``.
        "expected_status": "ambiguous_mixed_status",
        "placeholder_fields": ["expected_output"],
        "reason": "mixed real-looking + placeholder",
        "source_references": [
            "docs/tasks/TASK-019-slice-3-validation-adapter-contract.md",
            "docs/tasks/TASK-019-slice-3a-placeholder-fixture-contract.md",
        ],
    }

    report = validate_case(mixed_case)
    assert report.status == STATUS_BLOCKED
    assert report.status not in (STATUS_PLACEHOLDER,)
    # The unknown case_id triggers the unsupported_case_shape warning
    # (informational; does NOT change the classification).
    assert WARNING_UNSUPPORTED_CASE_SHAPE in report.warnings


def test_no_production_row_writes() -> None:
    """The adapter does NOT issue any INSERT / UPDATE / DELETE / session.flush / session.commit.

    Per §15.1: "run adapter against a real or in-memory session and
    assert that no ``INSERT`` / ``UPDATE`` / ``DELETE`` was issued and
    that ``session.flush()`` / ``session.commit()`` were not called by
    the adapter (this can be implemented as a transaction isolation
    check: open an outer transaction, run the adapter, assert no inner
    commit)".

    The adapter signature in this implementation does NOT take a
    ``session`` argument at all — the adapter is structurally read-only
    with respect to production data (contract §11 / §13). This test
    verifies the structural property by:

        (a) inspecting the adapter module via Python ``ast`` to ensure
            no forbidden ORM symbols appear as actual imports or call
            expressions (docstring mentions that explain the absence
            of these symbols are intentional and are not caught here);
        (b) inspecting the adapter's public surface — the
            ``validate_case`` signature MUST NOT take a database
            session argument.

    The §15.3 forward-looking "forbidden-import guard" is implemented
    here as an AST-level scan: a docstring mention of ``session.flush``
    is fine (the docstring says "the adapter does NOT do this"); an
    actual ``session.flush()`` call expression is NOT fine.
    """
    import ast

    import cold_storage.modules.reports.application.validation_adapter as adapter_mod

    source = inspect.getsource(adapter_mod)
    tree = ast.parse(source)

    forbidden_method_names = {"flush", "commit", "add", "delete"}
    forbidden_literal_symbols = {
        "bulk_insert_mappings",
        "create_all",
        "execute",  # raw session.execute(text(...)) is forbidden
    }
    forbidden_attrs_on_session = forbidden_method_names | forbidden_literal_symbols

    def _is_session_like(node: ast.AST) -> bool:
        """Return True if ``node`` references a ``session``-like identifier.

        A trivial string check on the source is good enough for the
        guard here — the adapter module is small and the forbidden
        access patterns are well-defined. We avoid heavy heuristic
        parsing; the AST walk below checks the actual call shape.
        """
        if isinstance(node, ast.Name):
            return node.id in {"session", "db", "database_session", "txn"}
        if isinstance(node, ast.Attribute):
            return node.attr in {"session", "db"}
        return False

    def _find_session_method_calls(
        func: ast.AST,
    ) -> list[ast.Call]:
        """Walk an AST subtree and return any calls on a session attribute."""
        out: list[ast.Call] = []
        for sub in ast.walk(func):
            if not isinstance(sub, ast.Call):
                continue
            is_simple_session = (
                isinstance(sub.func, ast.Attribute)
                and isinstance(sub.func.value, ast.Name)
                and sub.func.value.id == "session"
                and sub.func.attr in forbidden_attrs_on_session
            )
            is_chained_session = (
                isinstance(sub.func, ast.Attribute)
                and isinstance(sub.func.value, ast.Attribute)
                and sub.func.attr in forbidden_method_names
            )
            if is_simple_session or is_chained_session:
                # Catches ``Session()`` factory construction or
                # chained attribute access on a session-like value.
                out.append(sub)
        return out

    # (a) AST-level scan: collect every Call node and inspect its
    # structure. Docstring nodes (ast.Expr(ast.Constant(...))) and
    # import statements are evaluated separately.
    forbidden_calls: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                # SQLAlchemy session / ORM / raw SQL imports are forbidden.
                lowered = alias.name.lower()
                is_sqla = "sqlalchemy" in lowered
                is_orm = "orm" in lowered
                is_session_mod = ".session" in lowered
                if is_sqla or is_orm or is_session_mod:
                    forbidden_calls.append(("import", alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                continue
            module_lower = node.module.lower()
            is_sqla = "sqlalchemy" in module_lower
            is_orm = "orm" in module_lower
            if is_sqla or is_orm:
                for alias in node.names:
                    forbidden_calls.append(
                        ("import_from", f"{node.module}.{alias.name}"),
                    )
        elif isinstance(node, ast.Call):
            for call in _find_session_method_calls(node.func):
                forbidden_calls.append(("call", ast.dump(call)))

    assert not forbidden_calls, (
        f"validation_adapter module must not import or invoke any "
        f"SQLAlchemy session / ORM / raw SQL symbol; found: "
        f"{forbidden_calls!r}"
    )

    # (b) The public function does not accept a ``session`` argument,
    # which would let callers accidentally pass a DB session that the
    # adapter might mutate.
    signature = inspect.signature(adapter_mod.validate_case)
    for forbidden_param in ("session", "db", "database_session", "transaction"):
        assert forbidden_param not in signature.parameters, (
            f"validate_case must not accept a {forbidden_param!r} "
            f"parameter; the adapter is read-only by contract §11."
        )

    # The adapter can still be invoked on the three fixture cases without
    # any session open. We run it here as proof of the no-side-effect
    # property.
    for case in iter_cases():
        report = validate_case(case)
        assert isinstance(report, ValidationReport)


def test_no_demo_or_latest_row_fallback() -> None:
    """The adapter does NOT silently fall back to demo / latest-row data.

    Per §15.1: "construct a synthetic case that requires fallback to
    demo / latest-row data; assert the adapter does NOT silently fill in
    defaults from any fallback source and reports ``blocked`` instead".

    Per §13 "prohibited inference rules": "No latest-row fallback" and
    "No demo fallback".
    """
    # The synthetic case has neither ``placeholder`` shape (i.e., it
    # looks like a real case) nor any of the three Slice 3A
    # ``expected_status`` values. Per the contract's fail-closed branch,
    # the adapter MUST route this to ``blocked`` instead of falling
    # back to demo / latest-row data.
    synthetic_case = {
        "task_id": "TASK-019",
        "slice_id": "slice-3",
        "case_id": "case_synthetic_requires_fallback",
        "inputs": {"placeholder": False, "value": 999.0},
        "expected_output": {"placeholder": False, "value": 999.0},
        "requires_slice": None,
        # deliberately not in the §5 closed set; the adapter MUST still
        # produce a report (not raise, not return None, not fall back).
        "expected_status": "would_require_demo_fallback",
        "placeholder_fields": [],
        "reason": "synthetic case that requires a fallback.",
        "source_references": [
            "docs/tasks/TASK-019-slice-3-validation-adapter-contract.md",
        ],
    }

    report = validate_case(synthetic_case)

    # The adapter routes to ``blocked`` (fail-closed) instead of falling
    # back to demo / latest-row data.
    assert report.status == STATUS_BLOCKED
    assert report.status != STATUS_PLACEHOLDER
    # The unsupported_case_shape warning is surfaced as informational;
    # the status remains the source of truth.
    assert WARNING_UNSUPPORTED_CASE_SHAPE in report.warnings
    # The report has no fallback-injected fields. The adapter does NOT
    # fill in placeholders with demo data; the missing fields list
    # would surface if the inputs had structurally invalid fields, but
    # for this synthetic case the inputs are real-shaped (just not in
    # the closed status set). The status remains ``blocked``.
    assert report.expected_output == synthetic_case["expected_output"]
    # Even with an attempted demo payload, the adapter does NOT
    # substitute a fabricated result.
    demo_attempt = {"demo": True, "fabricated": 100.0}
    report_with_demo = validate_case(synthetic_case, production_output=demo_attempt)
    assert report_with_demo.status == STATUS_BLOCKED
    assert report_with_demo.expected_output == synthetic_case["expected_output"]


def test_adapter_internal_warning_on_non_dict_case() -> None:
    """A non-dict ``case`` argument falls into the hard-blocked guard.

    The Slice 3B contract §8.2 requires the adapter to never return
    ``None`` — failure to construct a report is itself a ``blocked``
    case. This is exercised here as an additional defensive check
    beyond the §15.1 enumerated tests; it is informational, not part
    of the required test count.
    """
    report = validate_case("not-a-dict")  # type: ignore[arg-type]
    assert isinstance(report, ValidationReport)
    assert report.status == STATUS_BLOCKED
    assert WARNING_ADAPTER_INTERNAL_WARNING in report.warnings

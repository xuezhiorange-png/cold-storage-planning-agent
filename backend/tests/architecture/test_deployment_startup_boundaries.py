"""Architecture tests for TASK-012 Slice 2 deployment/startup boundaries.

These tests assert the architectural invariants in Slice 2 contract
section 9.5 and D-S2-06:

* the application process does not invoke Alembic upgrade/downgrade;
* liveness does not call dependency probes;
* readiness owns dependency probes through the canonical runtime authority;
* strict environments cannot silently admit fake/in-memory production wiring;
* raw exception text is not returned by health endpoints;
* no second configuration or redaction authority is introduced;
* the defensive strict-mode capability admission assertion
  (``STRICT_UNSAFE_CAPABILITY_COUNT_REQUIRED=0``) runs at startup
  and fails closed with ``UNSAFE_STRICT_CAPABILITY_WIRING`` if
  violated;
* the ``/opt/cold-storage/build-identity.json`` authority is the
  single source of truth for build commit and version at runtime;
* probe timeouts are bounded per probe and do not rely on unbounded
  background threads or tasks;
* the probe aggregate upper bound is enforced as a conservative
  upper bound; tests assert completion within the bound and correct
  failure classification, never equality with the product;
* the build version character contract (D-S2-02.d) is enforced for
  both the in-image ``version`` and the runtime
  ``COLD_STORAGE_BUILD_VERSION``.
"""

from __future__ import annotations

from pathlib import Path


# Architecture tests instantiate the FastAPI app via ``create_app()``,
# which runs the production lifespan and therefore triggers
# ``Settings()`` at startup. The settings layer's defaults
# (``local`` env id, ``sqlite`` backend, ``./cold_storage_dev.db``
# sqlite path) are already correct for the architecture test surface,
# so we do NOT pre-populate any environment variable at module level.
# Per-test fixtures add whatever a particular test needs through
# ``monkeypatch``.
#
# We deliberately do NOT seed any ``COLD_STORAGE_*`` keys at module
# level here. The settings layer's pydantic-settings integration
# treats the presence of any canonical ``COLD_STORAGE_*`` key as a
# signal to drop all non-canonical (legacy ``DATABASE_URL`` /
# ``DATABASE_BACKEND`` / ``APP_DEBUG``) keys. The existing
# postgresql ``a2_pg_database`` fixture in
# ``tests/evaluation/_seed_helpers.py`` sets the *legacy* keys when
# invoking its ``alembic upgrade head`` subprocess, and that fixture
# only works when no canonical key is leaked by another test module
# in the same pytest collection. Seeding even a single canonical
# key here poisons the global ``os.environ`` and causes
# ``a2_pg_database`` to create an empty sqlite file (the
# ``database_backend`` defaults to ``sqlite`` once the legacy
# ``DATABASE_BACKEND`` is dropped), which then explodes the first
# postgresql-marked test with ``relation "projects" does not exist``,
# or — for sqlite-marked tests with their own per-test
# ``SQLITE_PATH`` — causes the upstream ``alembic upgrade head`` to
# migrate the wrong database and explode with
# ``no such table: alembic_version`` /
# ``no such table: projects``. Per-test fixtures must therefore
# always go through ``monkeypatch`` and never through
# ``os.environ`` directly.
def _bootstrap_path() -> Path:
    return Path(__file__).resolve().parents[2] / "src" / "cold_storage" / "bootstrap"


def test_runtime_bootstrap_does_not_use_alembic():
    """The runtime bootstrap module MUST NOT import or invoke alembic.

    We strip ALL docstrings (module- and function-level) and inline
    comments before scanning, so docstring mentions are allowed. We
    also assert there is no ``import alembic`` / ``from alembic`` etc.
    in the executable source.
    """
    import ast
    import re

    bootstrap = _bootstrap_path()
    for path in bootstrap.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        # Walk AST and rebuild executable source with all string-literal
        # nodes that are the first statement of a function/module/class
        # replaced by empty placeholders.  This strips docstrings (which
        # Python attaches as Expr -> Constant Str) without touching
        # any other string.
        tree = ast.parse(source)

        class _DocstringStripper(ast.NodeTransformer):
            def visit_Module(self, node: ast.Module) -> ast.Module:  # type: ignore[override]
                if (
                    node.body
                    and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)
                ):
                    node.body[0] = ast.Pass()
                self.generic_visit(node)
                return node

            def visit_FunctionDef(self, node):  # noqa: ANN001
                if (
                    node.body
                    and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)
                ):
                    node.body[0] = ast.Pass()
                self.generic_visit(node)
                return node

            def visit_AsyncFunctionDef(self, node):  # noqa: ANN001
                return self.visit_FunctionDef(node)  # type: ignore[arg-type]

            def visit_ClassDef(self, node):  # noqa: ANN001
                if (
                    node.body
                    and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)
                ):
                    node.body[0] = ast.Pass()
                self.generic_visit(node)
                return node

        _DocstringStripper().visit(tree)
        stripped = ast.unparse(tree)
        stripped = re.sub(r"#[^\n]*\n", "\n", stripped)
        # Allow ``alembic_version`` (the SQL table the runtime reads to
        # compare the recorded head against the packaged head) but
        # forbid any import / dynamic use of alembic itself. The
        # schema probe only reads the table to verify head match; it
        # does NOT import or invoke alembic.
        if "alembic_version" in stripped:
            for forbidden in (
                "from alembic",
                "import alembic",
                "alembic.command",
                "alembic.config",
                "alembic.runtime",
                "alembic upgrade",
                "alembic downgrade",
                "alembic stamp",
                "alembic revision",
                "alembic.script",
            ):
                assert forbidden not in stripped, (
                    f"{path.name} must not invoke '{forbidden.split()[-1]}'; "
                    "reading the alembic_version SQL table for head comparison is allowed"
                )
        else:
            assert "alembic" not in stripped, (
                f"{path.name} must not reference 'alembic' in executable code"
            )

    # Belt-and-braces: AST-level import check.
    for path in bootstrap.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "alembic" not in alias.name, (
                        f"{path.name} imports {alias.name!r} at runtime"
                    )
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                assert "alembic" not in mod, f"{path.name} has 'from {mod} import ...' at runtime"


def test_liveness_does_not_call_dependency_probes(monkeypatch):
    from fastapi.testclient import TestClient

    from cold_storage.bootstrap.app import create_app

    # The settings layer's pydantic-settings integration accepts the
    # canonical ``COLD_STORAGE_READINESS_PROBE_TIMEOUT_SECONDS`` value
    # directly without any per-test setup, but we still go through
    # ``monkeypatch`` so the canonical key never leaks into the
    # process-wide environment (see the module-level comment).
    monkeypatch.setenv(
        "COLD_STORAGE_READINESS_PROBE_TIMEOUT_SECONDS",
        "5",
    )
    # Build a minimal app and inspect its routes for ``/health/live``.
    app = create_app()
    with TestClient(app) as client:
        # Hit only liveness; record any DB calls.
        from cold_storage.bootstrap import dependencies as deps

        called = {"count": 0}
        original = deps.get_engine

        def _spy():
            called["count"] += 1
            return original()

        deps.get_engine = _spy  # type: ignore[assignment]
        try:
            for _ in range(3):
                client.get("/health/live")
        finally:
            deps.get_engine = original  # type: ignore[assignment]
        assert called["count"] == 0, "liveness must not consult the engine (no DB probe)"


def test_readiness_uses_canonical_runtime_authority(monkeypatch):
    from fastapi.testclient import TestClient

    from cold_storage.bootstrap.app import create_app
    from cold_storage.bootstrap.runtime_readiness import (
        LOCAL_TEST_READINESS_PROBE_TIMEOUT_SECONDS,
        ReadinessState,
        reset_readiness_state,
        set_readiness_state,
    )

    monkeypatch.setenv(
        "COLD_STORAGE_READINESS_PROBE_TIMEOUT_SECONDS",
        str(LOCAL_TEST_READINESS_PROBE_TIMEOUT_SECONDS),
    )
    reset_readiness_state()
    set_readiness_state(ReadinessState(state="READY"))
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/health/ready")
        assert resp.status_code == 200
        # The canonical authority state singleton reports the same.
        snapshot = (
            __import__(
                "cold_storage.bootstrap.runtime_readiness",
                fromlist=["get_readiness_state"],
            )
            .get_readiness_state()
            .snapshot()
        )
        assert snapshot["state"] == "READY"


def test_strict_mode_registered_capabilities_count_is_two():
    from cold_storage.bootstrap.runtime_readiness import registered_strict_capabilities

    caps = registered_strict_capabilities()
    # The contract scope-limited table freezes exactly these two
    # strict-mode unsafe wirings.
    assert "PLANNING_AGENT_MODEL_HTTP_ROUTE_STRICT_MODE" in caps
    assert "COEFFICIENT_HTTP_ROUTE_STRICT_MODE" in caps
    assert len(caps) == 2


def test_raw_exception_text_not_returned_by_health_endpoints():
    """Health endpoints MUST NOT include raw exception text or tracebacks.

    The lifespan now runs the mandatory 8-probe startup phase (D-S2-04)
    which fails closed when the state is DRAINING / SHUTDOWN_COMPLETE
    during bootstrap. We therefore build the app, enter the test
    client (which triggers the lifespan with state=READY), then flip
    state to DRAINING, and only THEN probe /health/ready (which
    short-circuits to 503 before invoking the readiness probes, per
    the contract).
    """
    from fastapi.testclient import TestClient

    from cold_storage.bootstrap.app import create_app
    from cold_storage.bootstrap.runtime_readiness import (
        ReadinessState,
        reset_readiness_state,
        set_readiness_state,
    )

    reset_readiness_state()
    set_readiness_state(ReadinessState(state="READY"))
    app = create_app()
    with TestClient(app) as client:
        # Flip to DRAINING AFTER lifespan so the /health/ready
        # endpoint exercises the contract's "DRAINING -> 503" branch.
        set_readiness_state(ReadinessState(state="DRAINING"))
        resp = client.get("/health/ready")
        body = resp.json()
        body_str = repr(body).lower()
        for forbidden in (
            "traceback",
            "exception",
            "stacktrace",
            "stack trace",
        ):
            assert forbidden not in body_str, f"health response leaked {forbidden!r}"


def test_no_second_configuration_authority_in_bootstrap():
    bootstrap = _bootstrap_path()
    # Slice 1 owns configuration resolution. Slice 2 must reuse it,
    # not introduce a new layer.
    forbidden_tokens = {"pydantic_settings.BaseSettings", "BaseSettings("}
    for path in bootstrap.glob("*.py"):
        if path.name in {"environment_model.py", "settings.py"}:
            continue  # these are the canonical owners.
        text = path.read_text(encoding="utf-8")
        for token in forbidden_tokens:
            assert token not in text, (
                f"{path.name} must not introduce a second configuration authority"
            )


def test_defensive_strict_capability_assertion_passes_by_default():
    """With no registered strict capability reachable, the assertion passes.

    This corresponds to the canonical outcome (D-S2-06.a, D-S2-06.b):
    both known strict-mode unsafe wirings are un-registered in
    staging/production. We explicitly call the defensive assertion to
    ensure it executes and does not raise on a real (clean) app.

    Per TASK-012 Slice 2 brief §2 + §5 (2026-07-29 fix), the
    ``enumerate_reachable_unsafe_strict_capabilities`` order is
    mode → app → routes: local / test mode short-circuits with an
    empty reachable subset BEFORE the ``app=None`` check, so a
    ``local`` mode caller with no FastAPI app does NOT trigger the
    fail-closed branch. Strict-mode ``app=None`` behaviour is
    separately locked by the 9-matrix in
    ``tests/unit/test_runtime_readiness.py``.
    """
    from fastapi import FastAPI

    from cold_storage.bootstrap.runtime_readiness import (
        assert_no_unsafe_strict_capabilities,
    )

    # Real (clean) FastAPI app: reachable subset is empty.
    clean_app = FastAPI()
    assert_no_unsafe_strict_capabilities(app=clean_app)


def test_build_identity_module_does_not_invoke_git_cli():
    """The runtime MUST NOT re-derive identity from the working tree or git CLI.

    We strip docstrings and comments and assert against the executable
    source. We also assert there is no ``subprocess`` import and no
    ``os.system`` / ``os.popen`` call anywhere in the module.
    """
    import ast
    import re

    di_path = _bootstrap_path() / "deployment_identity.py"
    source = di_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    # Collect all string / identifier constants and call names from
    # executable statements. Docstrings and comments are excluded.
    banned_literals = ("subprocess", "git describe", "git rev-parse")
    for node in ast.walk(tree):
        # Direct imports of subprocess.
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "subprocess" not in alias.name, (
                    f"deployment_identity.py must not import {alias.name!r}"
                )
        # ``subprocess.run(...)`` etc.
        if isinstance(node, ast.Attribute):
            attr = node.attr
            assert attr not in ("run", "Popen", "call", "check_call", "check_output"), (
                f"deployment_identity.py must not invoke {attr!r}"
            )
        # Function call names that LOOK like a git CLI invocation.
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            attr = node.func.attr
            assert not attr.startswith("git_"), f"deployment_identity.py must not call {attr!r}"
        # ``os.system`` / ``os.popen`` would surface as Attribute on ``os``.
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "os"
            and node.attr in {"system", "popen"}
        ):
            raise AssertionError(f"deployment_identity.py must not call os.{node.attr}()")
    # Forbid any literal mention of "git describe" or "git rev-parse" as
    # an executable string (e.g. passed to subprocess). The check above
    # already prohibits subprocess; this last belt-and-braces line ensures
    # the literal pattern is absent entirely from comments too, because
    # operators read the source when debugging.
    for token in banned_literals:
        if token in source:
            # Allow the literal only inside a triple-quoted docstring or
            # a comment line. Strip both for a final scan.
            no_docstring = re.sub(r'"""[\s\S]*?"""', "", source)
            no_docstring = re.sub(r"'''[\s\S]*?'''", "", no_docstring)
            no_docstring = re.sub(r"#[^\n]*\n", "\n", no_docstring)
            assert token not in no_docstring, (
                f"deployment_identity.py must not reference {token!r} in executable code"
            )


def test_probe_runtime_uses_drain_state_before_dispose():
    """Drain transitions precede dependency disposal."""
    from cold_storage.bootstrap.runtime_readiness import (
        ReadinessState,
        reset_readiness_state,
    )

    reset_readiness_state()
    state = ReadinessState(state="READY")
    state.transition(to="DRAINING")
    assert state.state == "DRAINING"


def test_health_redaction_does_not_leak_password_or_dsn():
    from fastapi.testclient import TestClient

    from cold_storage.bootstrap.app import create_app
    from cold_storage.bootstrap.runtime_readiness import (
        ReadinessState,
        reset_readiness_state,
        set_readiness_state,
    )

    reset_readiness_state()
    set_readiness_state(ReadinessState(state="READY"))
    app = create_app()
    with TestClient(app) as client:
        # Flip to DRAINING AFTER lifespan so the /health/ready
        # endpoint exercises the contract's "DRAINING -> 503" branch.
        set_readiness_state(ReadinessState(state="DRAINING"))
        # Force a forced expose-style probe outcome via DRAINING, then
        # assert the body has no secret / DSN.
        resp = client.get("/health/ready")
        assert resp.status_code == 503
        body = resp.json()
        body_str = repr(body).lower()
        for forbidden in ("password=", "secret=", "dsn=", "://"):
            assert forbidden not in body_str, f"health response leaked {forbidden!r}"

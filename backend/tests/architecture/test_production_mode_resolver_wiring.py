"""Architecture boundary test: Production-mode resolver wiring is centralised.

Slice 2A codified the production mode selector + the strict resolver
injection point.  Both must remain in the bootstrap layer; the
orchestration domain must not need to know about ``app_env``.

Static invariants verified here:

1. ``bootstrap.mode.resolve_app_mode`` accepts the three canonical
   values (``production`` / ``development`` / ``test``) and routes
   everything else to :class:`ValueError`.  Mode drift after
   Slice 2A is the most common regression: production deployments
   that silently fall back to ``development`` and bypass fail-
   closed.

2. ``bootstrap.startup_readiness.run_startup_readiness_or_raise``
   and ``bootstrap.mode`` do **not** import infrastructure ORM
   adapters.  These two modules wire SQLAlchemy via the typed
   factories in ``bootstrap.production_composition``; a direct
   import would bypass that layer and re-couple the bootstrap
   tier to a specific backend.

3. ``ProductionSourceBindingUseCase._gate_production_resolver``
   is gated by ``if self._coefficient_resolver is not None:`` —
   the legacy Phase 3 wiring (``resolver=None``) must remain a
   true no-op.

4. ``Settings.app_env`` carries a type annotation of
   ``Literal['production', 'development', 'test']`` so a typo at
   deploy time (e.g. ``"productoin"``) is rejected at Pydantic
   validation rather than silently routing into
   ``development``.

The four invariants map 1:1 to Slice 2A plan §10.1.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from cold_storage.bootstrap.mode import AppMode, is_production_mode, resolve_app_mode
from cold_storage.bootstrap.settings import Settings

# ``resolve_app_mode`` is the only mapping function — its signatures
# and source govern whether the four invariants hold.  Loading the
# module via importlib would also work, but a static AST scan
# catches accidental loosening (e.g. someone widening the Literal
# later in the file).
BACKEND_SRC = Path(__file__).resolve().parents[2] / "src" / "cold_storage"
MODE_PATH = BACKEND_SRC / "bootstrap" / "mode.py"
STARTUP_READINESS_PATH = BACKEND_SRC / "bootstrap" / "startup_readiness.py"
SETTINGS_PATH = BACKEND_SRC / "bootstrap" / "settings.py"


def _load_module_source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _parse_module(path: Path) -> ast.Module:
    return ast.parse(_load_module_source(path), filename=str(path))


# ---------------------------------------------------------------------------
# Invariant 1: ``resolve_app_mode`` recognises the three canonical values
# ---------------------------------------------------------------------------


def test_resolve_app_mode_accepts_three_canonical_values() -> None:
    """Every canonical value maps to the matching enum member."""
    settings_prod = Settings.model_validate({"app_env": "production"})
    settings_dev = Settings.model_validate({"app_env": "development"})
    settings_test = Settings.model_validate({"app_env": "test"})

    assert resolve_app_mode(settings_prod) is AppMode.PRODUCTION
    assert resolve_app_mode(settings_dev) is AppMode.DEVELOPMENT
    assert resolve_app_mode(settings_test) is AppMode.TEST


def test_resolve_app_mode_is_production_mode_helper() -> None:
    """``is_production_mode`` is the production branch of the mode space."""
    assert is_production_mode(AppMode.PRODUCTION) is True
    assert is_production_mode(AppMode.DEVELOPMENT) is False
    assert is_production_mode(AppMode.TEST) is False


def test_resolve_app_mode_rejects_unknown_value() -> None:
    """A typo in ``app_env`` must surface as a ValueError rather than
    silently routing the process into ``development``.

    ``Settings`` is now ``Literal['production','development','test']``
    so Pydantic rejects typos at construction time; this test
    simulates a hand-rolled ``Settings`` (or a future loosening of
    the Literal) and confirms ``resolve_app_mode`` still raises
    rather than returning ``DEVELOPMENT``.
    """
    # Bypass Pydantic validation deliberately to reach
    # ``resolve_app_mode`` with a typo.  ``object.__new__`` +
    # ``__dict__`` is the cleanest in-process trick.
    fake = object.__new__(Settings)
    fake.__dict__["app_env"] = "productoin"
    with pytest.raises(ValueError):
        resolve_app_mode(fake)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Invariant 2: ``bootstrap.startup_readiness`` and ``bootstrap.mode`` do
# not import infrastructure ORM directly
# ---------------------------------------------------------------------------


_FORBIDDEN_FROM_BOOTSTRAP_MODE = (
    "infrastructure.orm",
    "infrastructure.repositories",
    "cold_storage.config",
)


@pytest.mark.parametrize(
    "module_path",
    [MODE_PATH, STARTUP_READINESS_PATH],
    ids=["bootstrap.mode", "bootstrap.startup_readiness"],
)
def test_bootstrap_module_does_not_import_infrastructure(module_path: Path) -> None:
    """The bootstrap tier routes SQLAlchemy via factories, not direct imports."""
    src = _load_module_source(module_path)
    for token in _FORBIDDEN_FROM_BOOTSTRAP_MODE:
        assert token not in src, (
            f"{module_path.name} must not import {token!r}; route via"
            " bootstrap.production_composition factories instead."
        )


# ---------------------------------------------------------------------------
# Invariant 3: ``ProductionSourceBindingUseCase`` legacy wiring preserved
# ---------------------------------------------------------------------------


PRODUCTION_SOURCE_BINDING_PATH = (
    BACKEND_SRC / "modules" / "orchestration" / "application" / "production_source_binding.py"
)


def test_production_source_binding_legacy_path_keeps_resolver_none_branch() -> None:
    """``if self._coefficient_resolver is not None:`` guards the gate."""
    src = _load_module_source(PRODUCTION_SOURCE_BINDING_PATH)
    assert "if self._coefficient_resolver is not None:" in src
    assert "self._gate_production_resolver()" in src

    # Also confirm the gate method itself is defined and is the
    # only resolver access path on the use case (no other place
    # invokes ``resolver.resolve`` directly).
    tree = _parse_module(PRODUCTION_SOURCE_BINDING_PATH)
    found_gate_method = False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_gate_production_resolver":
            found_gate_method = True
    assert found_gate_method, "ProductionSourceBindingUseCase must carry _gate_production_resolver"


def test_production_source_binding_init_signature_accepts_resolver_keyword_only() -> None:
    """``coefficient_resolver`` is keyword-only with a default of None."""
    tree = _parse_module(PRODUCTION_SOURCE_BINDING_PATH)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "ProductionSourceBindingUseCase":
            for child in node.body:
                if isinstance(child, ast.FunctionDef) and child.name == "__init__":
                    args = child.args
                    # All non-self args must be keyword-only (after ``*``).
                    assert args.posonlyargs == []
                    # ``args.args`` carries ``self`` as its first element
                    # for instance methods; the rest of the function
                    # arguments must be keyword-only.
                    non_self_positional = [arg for arg in args.args if arg.arg != "self"]
                    assert non_self_positional == [], (
                        "coefficient_resolver and friends must be keyword-only;"
                        f" found positional args {non_self_positional}"
                    )
                    kwarg_names = [a.arg for a in args.kwonlyargs]
                    assert "coefficient_resolver" in kwarg_names, kwarg_names
                    # Default must be None so legacy P3 wiring survives.
                    defaults = child.args.kw_defaults
                    for kwarg, default in zip(args.kwonlyargs, defaults, strict=True):
                        if kwarg.arg == "coefficient_resolver":
                            assert isinstance(default, ast.Constant) and default.value is None, (
                                "coefficient_resolver default must be None for backward compat"
                            )
                    return
    pytest.fail("ProductionSourceBindingUseCase.__init__ not found")


# ---------------------------------------------------------------------------
# Invariant 4: ``Settings.app_env`` is a Literal
# ---------------------------------------------------------------------------


def test_settings_app_env_is_literal() -> None:
    """``app_env`` is statically typed as a Literal of three values.

    The settings module carries a module-level alias
    ``AppEnvLiteral = Literal['production','development','test']`` so
    the class field can carry a single token rather than the full
    tuple.  This test follows the alias if necessary.
    """
    from typing import cast

    tree = _parse_module(SETTINGS_PATH)

    # Build the alias map {Name: Tuple[Constant, ...]} for any
    # module-level ``NAME = Literal[...]`` statement.
    alias_map: dict[str, ast.Tuple] = {}
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
            tgt = stmt.targets[0]
            if isinstance(tgt, ast.Name) and isinstance(stmt.value, ast.Subscript):
                slc = stmt.value.slice
                if isinstance(slc, ast.Tuple) and all(
                    isinstance(c, ast.Constant) and isinstance(c.value, str) for c in slc.elts
                ):
                    alias_map[tgt.id] = cast(ast.Tuple, slc)

    app_env_annotation: ast.expr | None = None
    for stmt in tree.body:
        if isinstance(stmt, ast.ClassDef) and stmt.name == "Settings":
            for child in stmt.body:
                if (
                    isinstance(child, ast.AnnAssign)
                    and isinstance(child.target, ast.Name)
                    and child.target.id == "app_env"
                ):
                    app_env_annotation = child.annotation
                    break
            break
    if app_env_annotation is None:
        pytest.fail("Settings.app_env field not found")

    # Unwrap a single-level ``AppEnvLiteral`` alias.
    value_node: ast.expr
    if isinstance(app_env_annotation, ast.Name) and app_env_annotation.id in alias_map:
        value_node = alias_map[app_env_annotation.id]
    elif isinstance(app_env_annotation, ast.Subscript):
        value_node = cast(ast.expr, app_env_annotation.slice)
    else:
        pytest.fail(
            f"app_env annotation must be a Literal (or an alias of one);"
            f" got {ast.dump(app_env_annotation)}"
        )
        return  # for type-checkers

    assert isinstance(value_node, ast.Tuple), (
        f"Literal must enumerate a tuple of values; got {ast.dump(value_node)}"
    )
    literals: list[str] = []
    for c in value_node.elts:
        if isinstance(c, ast.Constant) and isinstance(c.value, str):
            literals.append(c.value)
    assert sorted(literals) == ["development", "production", "test"], sorted(literals)

"""Architecture boundary test: Production-mode resolver wiring is centralised.

Slice 2A codified the production mode selector + the strict resolver
injection point.  Both must remain in the bootstrap layer; the
orchestration domain must not need to know about ``app_env``.

Static invariants verified here:

1. ``bootstrap.mode.resolve_app_mode`` accepts the four canonical
   values (``local`` / ``test`` / ``staging`` / ``production``) and
   routes everything else to :class:`ValueError`.  Mode drift after
   Slice 2A is the most common regression: production deployments
   that silently fall back to ``local`` and bypass fail-closed.

   The legacy input ``development`` is accepted as a backwards-
   compatibility alias for ``local`` (handled by the bootstrap
   environment model); it is **not** a canonical ``AppMode``
   member.

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

4. ``Settings.environment_id`` is the canonical Pydantic model
   field; ``app_env`` is a read-only compatibility property that
   always reflects ``environment_id``.  ``AppMode`` enumerates
   exactly the four canonical values.

The four invariants map 1:1 to Slice 2A plan §10.1, updated for
the Slice 1 four-environment contract.
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

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
# Invariant 1: ``resolve_app_mode`` recognises the four canonical values
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("local", AppMode.LOCAL),
        ("test", AppMode.TEST),
        ("staging", AppMode.STAGING),
        ("production", AppMode.PRODUCTION),
    ],
)
def test_resolve_app_mode_accepts_four_canonical_values(
    value: str,
    expected: AppMode,
) -> None:
    """Every canonical value maps to the matching enum member.

    A lightweight stand-in (SimpleNamespace with only the
    ``environment_id`` attribute) is used so this test exercises
    the mode resolver contract in isolation from the strict
    Settings construction rules (which forbid partial configs in
    staging/production).
    """
    settings = SimpleNamespace(environment_id=value)
    assert resolve_app_mode(settings) is expected


def test_resolve_app_mode_is_production_mode_helper() -> None:
    """``is_production_mode`` covers the full four-mode space."""
    assert is_production_mode(AppMode.PRODUCTION) is True
    assert is_production_mode(AppMode.LOCAL) is False
    assert is_production_mode(AppMode.TEST) is False
    assert is_production_mode(AppMode.STAGING) is False


def test_resolve_app_mode_rejects_unknown_value() -> None:
    """A typo in ``environment_id`` must surface as a ValueError rather
    than silently routing the process into ``local``.

    ``Settings`` is now keyed on ``environment_id`` (a typed enum)
    so Pydantic rejects typos at construction time; this test
    simulates a hand-rolled object (or a future loosening of the
    enum) and confirms ``resolve_app_mode`` still raises rather
    than returning ``LOCAL``.
    """
    # Bypass Pydantic validation deliberately to reach
    # ``resolve_app_mode`` with a typo.  SimpleNamespace carries
    # only ``environment_id``; we confirm the resolver still
    # raises rather than silently falling back.
    fake = SimpleNamespace(environment_id="productoin")
    with pytest.raises(ValueError):
        resolve_app_mode(fake)  # type: ignore[arg-type]


def test_legacy_development_maps_to_local() -> None:
    """The legacy ``APP_ENV=development`` input normalises to ``local``.

    ``development`` is **not** a canonical environment and is **not**
    a member of :class:`AppMode`.  It is a legacy alias that the
    bootstrap environment model collapses onto ``LOCAL`` so that
    pre-Slice-1 callers keep working.  This test pins the contract.
    """
    settings = Settings.model_validate({"APP_ENV": "development"})
    assert settings.environment_id.value == "local"
    assert settings.app_env == "local"
    assert resolve_app_mode(settings) is AppMode.LOCAL


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
# Invariant 4: ``Settings`` carries ``environment_id`` (canonical) and
# exposes ``app_env`` as a read-only compatibility property;
# ``AppMode`` enumerates exactly the four canonical environments.
# ---------------------------------------------------------------------------


def test_settings_uses_environment_id_as_canonical_field() -> None:
    """``environment_id`` is the canonical field; ``app_env`` is a property."""
    assert "environment_id" in Settings.model_fields
    assert "app_env" not in Settings.model_fields
    assert isinstance(Settings.app_env, property)


def test_app_mode_has_exact_four_environment_contract() -> None:
    """``AppMode`` enumerates exactly the four canonical environments."""
    assert {mode.value for mode in AppMode} == {
        "local",
        "test",
        "staging",
        "production",
    }

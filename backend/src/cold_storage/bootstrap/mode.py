"""Application mode selector — Phase 4 Issue #35 Slice 2A.

The production-coefficient governance work is gated behind a
deliberate ``Settings.app_env`` value so the same image can be run
in development, test, or production mode without conditional code
sprinkled across the codebase. This module is the single home for
the mode value object and the typed helpers that depend on it.

Why a dedicated module
=======================

* ``bootstrap.settings`` is the *input* layer; it owns the
  ``Settings`` Pydantic model. Mapping a free-form ``app_env``
  string to the canonical mode is a *bootstrap* concern.
* The readiness gateway (``bootstrap.startup_readiness``) and the
  lifetime hook (``bootstrap.dependencies``) both need to ask the
  same question: "is this production mode?". Putting the answer in
  one place lets us type-check the call sites and add architecture
  tests against that single surface.

Why three canonical values (and not free-form strings)
======================================================

* Slice 2A deliberately tightens ``Settings.app_env`` from
  ``str`` to ``Literal["production", "development", "test"]`` so
  Pydantic rejects a typo at startup (e.g. ``"productoin"``)
  rather than silently falling into ``development`` and bypassing
  fail-closed.
* No fourth value is added: changing the catalogue is a separate
  decision and would require updating the Literal in
  ``bootstrap.settings`` plus the runtime check below plus the
  architecture tests. The discipline pays for itself.
"""

from __future__ import annotations

from enum import Enum

from cold_storage.bootstrap.settings import Settings


class AppMode(Enum):
    """Canonical runtime mode for the backend process.

    * ``PRODUCTION`` — fail-closed startup readiness check is on;
      strict resolver is enabled at the use case boundary when one
      is wired.
    * ``DEVELOPMENT`` — start in any state; demo flows work.
    * ``TEST`` — pytest / alembic test runs; the seed
      ``coefficient_revisions`` table typically carries demo rows
      only, so startup-readiness is intentionally skipped.
    """

    PRODUCTION = "production"
    DEVELOPMENT = "development"
    TEST = "test"


def resolve_app_mode(settings: Settings) -> AppMode:
    """Map ``Settings.app_env`` -> ``AppMode``.

    The Literal in ``bootstrap.settings`` already guards against
    typos at model validation, so this function is the
    type-safe single-source-of-truth lookup that the rest of the
    bootstrap layer depends on. The mapping is exhaustive over
    the three known values; defensive fall-through is
    intentionally absent so an unauthorised ``app_env`` value
    surfaces as an exception here instead of silently choosing
    "development".

    :raises ValueError: when ``app_env`` does not correspond to any
        canonical ``AppMode``. With the Literal in place this is
        unreachable on a validated ``Settings`` instance; the
        explicit guard exists for defence-in-depth should future
        work loosen the Literal.
    """
    raw = settings.app_env
    for mode in AppMode:
        if mode.value == raw:
            return mode
    raise ValueError(f"Unknown app_env={raw!r}; expected one of {sorted(m.value for m in AppMode)}")


def is_production_mode(mode: AppMode) -> bool:
    """Return True iff ``mode`` is :attr:`AppMode.PRODUCTION`."""
    return mode is AppMode.PRODUCTION


def is_test_or_development(mode: AppMode) -> bool:
    """Return True iff ``mode`` is development or test (non-production)."""
    return mode in (AppMode.DEVELOPMENT, AppMode.TEST)


__all__ = [
    "AppMode",
    "is_production_mode",
    "is_test_or_development",
    "resolve_app_mode",
]

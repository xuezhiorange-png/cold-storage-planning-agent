"""Canonical render observer — hook for capturing canonical render models.

Allows external observation of the canonical render model after it is built
but before it is localised and rendered.  The primary use case is testing:

- RecordingObserver in tests captures the canonical model for each render call
  so you can verify the canonical snapshot is locale/format-independent.
- NoopCanonicalObserver is the default (does nothing).
"""

from __future__ import annotations

from typing import Any, Protocol

from cold_storage.modules.reports.domain.canonical import golden_dict


class CanonicalRenderObserverPort(Protocol):
    """Port: observe the canonical render model after construction.

    ``record`` is called by ``ReportRenderService.render()`` after the
    canonical model is built but before it is localized and rendered.
    """

    def record(
        self,
        *,
        artifact_id: str,
        locale: str,
        format: str,  # noqa: A002
        canonical: Any,
    ) -> None:
        """Record the canonical render model for an artifact.

        Parameters
        ----------
        artifact_id:
            The artifact that will be produced from this canonical.
        locale:
            Target locale (e.g. "zh-CN", "en-US").
        format:
            Target format (e.g. "docx", "pdf").
        canonical:
            The ``CanonicalReportRenderModel`` dataclass instance.
        """
        ...


class NoopCanonicalObserver:
    """Default observer that does nothing.

    Used in production to avoid the cost of serialising the canonical model
    when no observer is configured.
    """

    def record(
        self,
        *,
        artifact_id: str,
        locale: str,
        format: str,  # noqa: A002
        canonical: Any,
    ) -> None:
        pass


class RecordingObserver:
    """Test observer that captures every canonical model it sees.

    Each call to ``record`` stores a dict (via ``golden_dict``) together with
    the locale, format, and artifact_id so tests can inspect the captured
    snapshots.

    Attributes
    ----------
    records:
        List of dicts with keys: artifact_id, locale, format, golden.
    """

    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def record(
        self,
        *,
        artifact_id: str,
        locale: str,
        format: str,  # noqa: A002
        canonical: Any,
    ) -> None:
        self.records.append(
            {
                "artifact_id": artifact_id,
                "locale": locale,
                "format": format,
                "golden": golden_dict(canonical),
            }
        )

    @property
    def snapshots(self) -> list[dict[str, Any]]:
        """Return the list of recorded golden_dict snapshots."""
        return [r["golden"] for r in self.records]

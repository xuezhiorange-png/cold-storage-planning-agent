"""Localization error types."""

from __future__ import annotations

from cold_storage.modules.reports.domain.errors import ReportError


class MissingTranslationError(ReportError):
    """Raised when a translation key is missing for a given locale."""

    def __init__(self, locale: str, key: str) -> None:
        self.locale = locale
        self.key = key
        super().__init__(f"Missing translation for key '{key}' in locale '{locale}'")

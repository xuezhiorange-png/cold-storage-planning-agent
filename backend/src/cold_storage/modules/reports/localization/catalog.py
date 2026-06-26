"""Translation catalog registry and lookup.

The catalog is the single source of truth for all localized display text.
Every key is a stable contract.  Missing keys raise ``MissingTranslationError``.

Catalog content is immutable at runtime (``MappingProxyType``) and produces a
deterministic ``content_hash`` for provenance tracking.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from cold_storage.modules.reports.domain.enums import ReportLocale

from .en_us import MESSAGES as _EN_US_MESSAGES
from .errors import MissingTranslationError
from .zh_cn import MESSAGES as _ZH_CN_MESSAGES


@dataclass(frozen=True)
class TranslationCatalog:
    """Immutable translation catalog for a single locale."""

    locale: ReportLocale
    version: str
    messages: Mapping[str, str]

    def __init__(
        self,
        locale: ReportLocale,
        version: str,
        messages: Mapping[str, str],
    ) -> None:
        # Bypass frozen __setattr__ to set fields in __init__
        object.__setattr__(self, "locale", locale)
        object.__setattr__(self, "version", version)
        # Wrap in MappingProxyType for true immutability
        object.__setattr__(self, "messages", MappingProxyType(dict(messages)))


_CATALOGS: dict[ReportLocale, TranslationCatalog] = {
    ReportLocale.ZH_CN: TranslationCatalog(
        locale=ReportLocale.ZH_CN,
        version="1.0.0",
        messages=_ZH_CN_MESSAGES,
    ),
    ReportLocale.EN_US: TranslationCatalog(
        locale=ReportLocale.EN_US,
        version="1.0.0",
        messages=_EN_US_MESSAGES,
    ),
}


def get_catalog(locale: ReportLocale) -> TranslationCatalog:
    """Return the translation catalog for *locale*.

    Raises
    ------
    KeyError
        If no catalog is registered for the requested locale.
    """
    catalog = _CATALOGS.get(locale)
    if catalog is None:
        raise KeyError(f"No translation catalog registered for locale '{locale.value}'")
    return catalog


def translate(locale: ReportLocale, key: str) -> str:
    """Translate *key* using the catalog for *locale*.

    Raises
    ------
    MissingTranslationError
        If *key* is not present in the catalog's messages.
    """
    catalog = get_catalog(locale)
    msg = catalog.messages.get(key)
    if msg is None:
        raise MissingTranslationError(locale.value, key)
    return msg


def compute_catalog_content_hash(locale: ReportLocale) -> str:
    """Compute a deterministic SHA-256 content hash for a locale catalog.

    Hashes the sorted key→value pairs as canonical JSON.  This ensures
    that changing the catalog content (even without changing ``version``)
    produces a different hash, which must invalidate idempotency fingerprints.
    """
    catalog = get_catalog(locale)
    # Sort by key for deterministic ordering
    sorted_pairs = dict(sorted(catalog.messages.items()))
    canonical = json.dumps(sorted_pairs, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def translate_format(locale: ReportLocale, key: str, **kwargs: str) -> str:
    """Translate *key* and apply ``str.format_map`` with *kwargs*.

    Raises
    ------
    MissingTranslationError
        If *key* is not present in the catalog's messages.
    KeyError
        If a template placeholder is missing from *kwargs*.
    """
    pattern = translate(locale, key)
    return pattern.format_map(kwargs)

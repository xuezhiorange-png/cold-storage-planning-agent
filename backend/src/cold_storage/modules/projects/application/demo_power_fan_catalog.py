"""Load evaporator/condenser fan demo electrical from the v05 workbench sample.

This module does not run calculators. Fan kW(e) stay ``source_type=demo``,
``validity_status=unverified``, and ``requires_review=true``. Kernel
``InstalledPowerCalcInput`` defaults remain 0 (fail-closed). v05 compressor
``120.0`` is not authority.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

DEMO_POWER_FAN_SAMPLE_ID = "v05-local-workbench"
DEMO_POWER_FAN_SOURCE = f"samples/{DEMO_POWER_FAN_SAMPLE_ID}/manifest.json"
EVAPORATOR_FAN_FIELD = "evaporator_fan_power_kw_e"
CONDENSER_FAN_FIELD = "condenser_fan_power_kw_e"
FAN_FIELD_NAMES: tuple[str, str] = (EVAPORATOR_FAN_FIELD, CONDENSER_FAN_FIELD)

POWER_FAN_DEMO_CATALOG_DISCLAIMER_ZH = (
    "蒸发/冷凝风机电气来自 v05 演示目录（10 / 8 kW(e)），不是设备结果，需复核"
)


@dataclass(frozen=True, slots=True)
class DemoPowerFanCatalog:
    """v05 fan electrical catalog with honesty markers."""

    evaporator_fan_power_kw_e: str
    condenser_fan_power_kw_e: str
    source: str = DEMO_POWER_FAN_SOURCE
    source_type: str = "demo"
    validity_status: str = "unverified"
    requires_review: bool = True

    def as_field_map(self) -> dict[str, str]:
        return {
            EVAPORATOR_FAN_FIELD: self.evaporator_fan_power_kw_e,
            CONDENSER_FAN_FIELD: self.condenser_fan_power_kw_e,
        }


def demo_power_fan_manifest_path(*, start: Path | None = None) -> Path:
    here = (start or Path(__file__)).resolve()
    roots = [here, *here.parents] if here.is_dir() else list(here.parents)
    for parent in roots:
        candidate = parent / "samples" / DEMO_POWER_FAN_SAMPLE_ID / "manifest.json"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(DEMO_POWER_FAN_SOURCE)


def fan_power_values_from_manifest(manifest: Mapping[str, Any]) -> dict[str, str]:
    """Extract the two fan leaves. Fail closed if missing, zero, or non-numeric."""
    bundle = manifest.get("engineering_input_bundle")
    if not isinstance(bundle, Mapping):
        raise ValueError("v05 manifest is missing engineering_input_bundle")
    section = bundle.get("installed_power_inputs")
    if not isinstance(section, Mapping):
        raise ValueError("v05 manifest is missing installed_power_inputs")
    values: dict[str, str] = {}
    for field_name in FAN_FIELD_NAMES:
        values[field_name] = _positive_kw_e_text(section, field_name)
    return values


def load_demo_power_fan_catalog(*, start: Path | None = None) -> DemoPowerFanCatalog:
    """Return the frozen v05 fan demo catalog with honesty markers."""
    manifest = json.loads(demo_power_fan_manifest_path(start=start).read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("v05 manifest is not an object")
    values = fan_power_values_from_manifest(manifest)
    return DemoPowerFanCatalog(
        evaporator_fan_power_kw_e=values[EVAPORATOR_FAN_FIELD],
        condenser_fan_power_kw_e=values[CONDENSER_FAN_FIELD],
    )


def load_demo_power_fan_catalog_payload(*, start: Path | None = None) -> dict[str, Any]:
    """JSON payload for the read-only demo fan catalog GET."""
    catalog = load_demo_power_fan_catalog(start=start)
    return {
        "source": catalog.source,
        "source_type": catalog.source_type,
        "validity_status": catalog.validity_status,
        "requires_review": catalog.requires_review,
        "disclaimer_zh": POWER_FAN_DEMO_CATALOG_DISCLAIMER_ZH,
        EVAPORATOR_FAN_FIELD: _catalog_leaf(catalog.evaporator_fan_power_kw_e),
        CONDENSER_FAN_FIELD: _catalog_leaf(catalog.condenser_fan_power_kw_e),
    }


def _catalog_leaf(value: str) -> dict[str, Any]:
    return {
        "value": value,
        "unit": "kW(e)",
        "state": "provided",
        "source_type": "demo",
        "validity_status": "unverified",
        "requires_review": True,
        "source_path": DEMO_POWER_FAN_SOURCE,
    }


def _positive_kw_e_text(section: Mapping[str, Any], field_name: str) -> str:
    raw = section.get(field_name)
    if not isinstance(raw, Mapping):
        raise ValueError(f"v05 manifest is missing installed_power_inputs.{field_name}")
    value = raw.get("value")
    text = str(value).strip() if value is not None else ""
    if not text:
        raise ValueError(f"v05 manifest has empty installed_power_inputs.{field_name}")
    try:
        number = Decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(
            f"v05 manifest has non-numeric installed_power_inputs.{field_name}"
        ) from exc
    if number <= 0:
        raise ValueError(f"v05 fan catalog {field_name} must be a positive kW(e), got {text!r}")
    return text

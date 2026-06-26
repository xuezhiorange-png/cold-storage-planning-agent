"""Locale-aware formatting utilities.

All functions accept an explicit ``locale`` parameter and never call
``locale.setlocale()``.

Section V contract:
- ``format_decimal`` accepts ``Decimal | int`` — never converts through float.
- Identical value + locale + precision → byte-identical output.
- No system locale dependency.
"""

from __future__ import annotations

from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any

from cold_storage.modules.reports.domain.enums import ReportLocale

from .catalog import translate

# ---------------------------------------------------------------------------
# Decimal formatting
# ---------------------------------------------------------------------------


def format_decimal(
    value: Decimal | int,
    locale: ReportLocale,
    *,
    decimal_places: int | None = None,
) -> str:
    """Format a ``Decimal`` or ``int`` with locale-aware separators.

    Contract:
    - Never converts through ``float``.
    - ``Decimal`` preserves its existing precision when ``decimal_places`` is
      ``None``; otherwise pads/truncates to the requested count.
    - ``int`` always renders with ``decimal_places=0`` when not specified.
    - zh-CN: no thousands separator, period decimal.
    - en-US: comma thousands separator, period decimal.

    Parameters
    ----------
    value:
        The number to format.  Must be ``Decimal`` or ``int``.
    locale:
        Target locale.
    decimal_places:
        Decimal places.  ``None`` auto-detects from the value's precision.

    Raises
    ------
    TypeError
        If *value* is not ``Decimal`` or ``int`` (e.g. ``float``).
    """
    if not isinstance(value, (Decimal, int)):
        raise TypeError(
            f"format_decimal requires Decimal or int, got {type(value).__name__}. "
            "Float conversion is not permitted."
        )

    if decimal_places is None:
        if isinstance(value, int):
            decimal_places = 0
        else:
            # Use the number of decimal digits in the Decimal
            tup = value.as_tuple()
            exp = tup.exponent
            decimal_places = max(0, -exp) if isinstance(exp, int) and exp < 0 else 0

    # Format using the Decimal itself — never float
    d = Decimal(value) if isinstance(value, int) else value

    # Quantize to the requested decimal places
    if decimal_places > 0:
        quantizer = Decimal(10) ** (-decimal_places)
        d = d.quantize(quantizer, rounding=ROUND_HALF_EVEN)
    elif decimal_places == 0 and isinstance(d, Decimal):
        d = d.quantize(Decimal("1"), rounding=ROUND_HALF_EVEN)

    # Format the integer and fractional parts
    # d is finite after quantize, so as_tuple() yields int digits
    d_tup = d.as_tuple()
    assert isinstance(d_tup.sign, int)
    assert isinstance(d_tup.exponent, int)
    int_digits_raw: list[int] = [int(x) for x in d_tup.digits]
    sign = d_tup.sign
    exp = d_tup.exponent

    # Build the integer part from digits
    if exp < 0:
        int_digits = int_digits_raw[: len(int_digits_raw) + exp]
        frac_digits = list(int_digits_raw[len(int_digits_raw) + exp :])
    else:
        int_digits = int_digits_raw
        frac_digits = []

    # Pad fractional part with leading zeros (not trailing)
    frac_digits = [0] * (decimal_places - len(frac_digits)) + frac_digits
    frac_digits = frac_digits[:decimal_places] if decimal_places > 0 else []

    # Join integer digits with thousands separator
    int_str = "".join(str(digit) for digit in int_digits)
    if not int_str:
        int_str = "0"

    if locale == ReportLocale.EN_US:
        # Add comma thousands separator
        groups: list[str] = []
        for i, ch in enumerate(reversed(int_str)):
            if i and i % 3 == 0:
                groups.append(",")
            groups.append(ch)
        int_str = "".join(reversed(groups))

    # Add sign (suppress negative zero)
    if sign and int_str != "0":
        int_str = "-" + int_str

    if frac_digits:
        return f"{int_str}.{''.join(str(d) for d in frac_digits)}"
    return int_str


# ---------------------------------------------------------------------------
# DateTime formatting
# ---------------------------------------------------------------------------


def format_datetime(
    value: datetime,
    locale: ReportLocale,
    timezone: Any | None = None,
) -> str:
    """Format a datetime with locale-aware pattern.

    Contract:
    - Naive datetime is explicitly rejected.
    - Aware datetime is converted to the target timezone.
    - Never calls ``locale.setlocale()``.
    - Same input + locale + timezone → byte-identical output.

    Parameters
    ----------
    value:
        The datetime to format.
    locale:
        Target locale.
    timezone:
        A ``zoneinfo.ZoneInfo`` or compatible tzinfo object.  Required.

    Raises
    ------
    ValueError
        If *value* is ``None``.
    TypeError
        If *value* is a naive datetime (no tzinfo).
    """
    if value is None:
        raise ValueError("Cannot format None datetime value")

    if value.tzinfo is None:
        raise TypeError("Naive datetime is not supported. Pass an aware datetime with tzinfo set.")

    if timezone is None:
        raise TypeError(
            "timezone parameter is required. Pass a zoneinfo.ZoneInfo or compatible tzinfo."
        )

    # Convert to target timezone
    converted = value.astimezone(timezone)

    if locale == ReportLocale.ZH_CN:
        return converted.strftime("%Y年%m月%d日 %H:%M")
    return converted.strftime("%m/%d/%Y %H:%M")


# ---------------------------------------------------------------------------
# Unit label formatting
# ---------------------------------------------------------------------------


_UNIT_CODE_TO_CATALOG_KEY: dict[str, str] = {
    "kW(r)": "kw_r",
    "kW(e)": "kw_e",
    "kW(th)": "kw_th",
    "kWh": "kwh",
    "m²": "m2",
    "m2": "m2",
    "CNY": "cny",
    "kg": "kg",
    "count": "count",
    "pallet": "pallet",
    "个": "count",
    "托盘": "pallet",
    "元": "cny",
}


def format_unit_label(unit_code: str, locale: ReportLocale) -> str:
    """Return the localized display label for *unit_code*.

    Looks up ``unit.<normalized_key>`` in the translation catalog.
    Raw unit codes (e.g. ``kW(r)``) are normalized to catalog key form
    (e.g. ``kw_r``) before lookup.

    Raises
    ------
    MissingTranslationError
        If the key is not found in the catalog.
    """
    catalog_key = _UNIT_CODE_TO_CATALOG_KEY.get(unit_code, unit_code)
    key = f"unit.{catalog_key}"
    return translate(locale, key)


# ---------------------------------------------------------------------------
# Enum formatting
# ---------------------------------------------------------------------------


def format_enum(
    enum_value: Any,
    locale: ReportLocale,
    prefix: str = "",
) -> str:
    """Format an enum value using its translated label.

    Looks up ``<prefix><enum_value.value>`` (or ``<prefix><enum_value>`` if
    the value is a plain string) in the translation catalog.

    Raises
    ------
    MissingTranslationError
        If the key is not found in the catalog.
    """
    # Resolve the enum's value string
    val_str = str(enum_value.value) if hasattr(enum_value, "value") else str(enum_value)

    key = f"{prefix}{val_str}" if prefix else val_str
    return translate(locale, key)

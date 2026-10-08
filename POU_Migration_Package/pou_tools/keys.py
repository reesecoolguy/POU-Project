"""Key normalisation shared by migration, tests, flows documentation and the app spec.

These rules MUST match the Power Fx / Power Automate expressions generated for the app and flows
(see app/spec and flows/): UPPER(TRIM(x)) with scanner '*' start/stop characters removed.
"""
from __future__ import annotations

import re

KEY_SEP = "|"
SEQ_SEP = "#"


class KeyError_(ValueError):
    pass


def to_text(v) -> str:
    """Render a workbook cell as text WITHOUT altering digits.

    Numeric cells (e.g. Item ID 100416 stored as a number) become '100416'. Whole floats lose '.0'.
    Leading zeros cannot be recovered from a numeric cell - callers record that as an exception.
    """
    if v is None:
        return ""
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if v == int(v):
            return str(int(v))
        return repr(v)
    return str(v)


def normalize_id(v) -> str:
    """UPPER(TRIM(x)) with scanner asterisks removed. Used for ItemID, LocationCode comparisons."""
    s = to_text(v).replace("*", "").strip()
    return s.upper()


def clean_display(v) -> str:
    """Trim outer whitespace only; keeps case, inner spacing and newlines (descriptions)."""
    return to_text(v).strip()


def stock_key(item_id, location) -> str:
    i = normalize_id(item_id)
    l = normalize_id(location)
    if not i or not l:
        raise KeyError_("StockKey needs both ItemID and LocationCode")
    if KEY_SEP in i or KEY_SEP in l:
        raise KeyError_(f"'{KEY_SEP}' is not allowed inside ItemID or LocationCode: {i!r} {l!r}")
    return f"{i}{KEY_SEP}{l}"


def ledger_key(skey: str, seq: int) -> str:
    return f"{skey}{SEQ_SEP}{int(seq)}"


def split_stock_key(skey: str):
    i, _, l = skey.partition(KEY_SEP)
    return i, l


_NUMERIC_ID = re.compile(r"^\d+$")


def looks_numeric(s: str) -> bool:
    return bool(_NUMERIC_ID.match(s))

"""Parsing-copy normalization for typed format matching.

Never apply this to names, addresses, OCR words or stored raw evidence.
Dash normalization preserves source spans. Date parsers retain their own
separator grammar. Numeric normalization requires an already bounded money cell.
"""
from __future__ import annotations

import re

DASH_CHARACTERS = "\u2010\u2011\u2012\u2013\u2014\u2015\u2212\ufe58\ufe63\uff0d"
_DASH_TABLE = str.maketrans({char: "-" for char in DASH_CHARACTERS})
_NUMERIC_LOOKALIKES = str.maketrans({"O": "0", "o": "0", "I": "1", "l": "1"})
_INTEGER_CELL = re.compile(r"(?:[0-9]+|[0-9]{1,3}(?:[,.][0-9]{3})+)")


def normalize_format_text(text: str) -> str:
    """Return a parsing copy with only explicitly allowed dashes translated."""
    return text.translate(_DASH_TABLE)


def normalize_numeric_text(text: str) -> tuple[str | None, tuple[str, ...]]:
    """Normalize a bounded integer-money cell and describe allowed corrections.

    Callers must establish the numeric column before using this parsing copy.
    An empty cell remains empty. Unknown glyphs and malformed grouping return
    None. Every corrected amount still requires the caller's arithmetic checks.
    """
    compact = re.sub(r"\s+", "", text)
    if not compact:
        return "", ()
    digits = compact.translate(_NUMERIC_LOOKALIKES)
    if _INTEGER_CELL.fullmatch(digits) is None:
        return None, ()
    corrections = []
    if digits != compact:
        corrections.append("digit_lookalike")
    if "." in digits:
        corrections.append("group_separator")
    return digits.replace(".", ","), tuple(corrections)

"""Length-preserving normalization for typed format matching only.

Never apply this to names, addresses, OCR words or stored raw evidence.
Date parsers retain their own separator grammar (no slash/dot expansion).
"""
from __future__ import annotations

DASH_CHARACTERS = "\u2010\u2011\u2012\u2013\u2014\u2015\u2212\ufe58\ufe63\uff0d"
_DASH_TABLE = str.maketrans({char: "-" for char in DASH_CHARACTERS})


def normalize_format_text(text: str) -> str:
    """Return a parsing copy with only explicitly allowed dashes translated."""
    return text.translate(_DASH_TABLE)

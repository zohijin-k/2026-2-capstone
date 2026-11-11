"""Normalize and validate the simple ASCII email format used by application forms."""

import re
import unicodedata

_EMAIL = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
)


def normalize_email(value: str) -> str:
    """Convert full-width ASCII to ASCII and trim surrounding whitespace."""
    return unicodedata.normalize("NFKC", value).strip()


def is_valid_email(value: str) -> bool:
    """Accept a nonempty ASCII local part and a dotted domain with a suffix."""
    return bool(value and value.isascii() and _EMAIL.fullmatch(value))

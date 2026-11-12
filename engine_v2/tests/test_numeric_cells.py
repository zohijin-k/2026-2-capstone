"""Numeric-only cell parsing uses fictitious values and explicit grammars."""
import pytest

from engine_v2.extractors.format_text import normalize_numeric_text


@pytest.mark.parametrize("text, expected, corrections", [
    ("", "", ()),
    (" \t", "", ()),
    ("0", "0", ()),
    ("12345", "12345", ()),
    ("12,345", "12,345", ()),
    ("1 2, 345", "12,345", ()),
    ("O", "0", ("digit_lookalike",)),
    ("o", "0", ("digit_lookalike",)),
    ("I2,3lO", "12,310", ("digit_lookalike",)),
    ("12.345", "12,345", ("group_separator",)),
    ("1.234,567", "1,234,567", ("group_separator",)),
    ("I2.3lO", "12,310", ("digit_lookalike", "group_separator")),
])
def test_normalize_integer_amount_cell(text, expected, corrections):
    assert normalize_numeric_text(text) == (expected, corrections)


@pytest.mark.parametrize("text", [
    "A", "12.34", "1234.567", "1,,234", "1,234,", ".123", "-1,234",
    "+123", "1e3", "12원", "2026.03.03", "가짜이름", "O가", "1/234",
])
def test_unknown_characters_and_ambiguous_grouping_stay_unreadable(text):
    assert normalize_numeric_text(text) == (None, ())

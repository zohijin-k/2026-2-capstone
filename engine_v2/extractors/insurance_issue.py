"""Issue-date evidence local to the insurance certificate's header table.

The upper-left authenticity stamp is never a source. Unknown layouts and
ambiguous/malformed cells fail closed; NHIS header selection is independent.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
import re

from ..pipeline.layout import Word, squash
from . import nhis_common as common
from .format_text import normalize_format_text

# The existing insurance_4 form's header table precedes the identity row.
HEADER_TOP, HEADER_BOTTOM = 18.0, 28.0
LABEL_MIN_X = 50.0
_LABEL = "발급일시"  # Whitespace/colon variants are accepted, no fuzzy spelling.
_NEXT_LABELS = ("발급번호", "성명", "주민", "조회기간", "문서확인번호", "발급일")
_CELL_DATE = re.compile(common.DATE_RE.pattern + r"\s*")
# Own may merge the printed space between day and HH:MM. An anchored,
# complete timestamp establishes that boundary; arbitrary digit tails do not.
_TIMESTAMP_DATE = re.compile(
    common.DATE_RE.pattern.removesuffix(r"(?!\d)") +
    r"\s*(?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d)?\s*"
)


@dataclass
class IssueSelection:
    label_found: bool = False
    cell_words: list[Word] = field(default_factory=list)
    cell_text: str = ""  # Internal only; never serialize this object.
    value: date | None = None
    source_words: list[Word] = field(default_factory=list)


def _same_row(anchor: Word, word: Word) -> bool:
    # A large stamp/background box must not expand row membership.
    height = min(anchor.y1 - anchor.y0, word.y1 - word.y0)
    return abs(anchor.cy - word.cy) <= min(0.8, max(0.3, height * 0.6))


def date_shape_spans(text: str) -> list[tuple[int, int]]:
    """Internal diagnostic shape locations, including merged timestamps.

    Spans index the original string because dash translation preserves length.
    They are never part of the diagnostic output schema.
    """
    parsed = normalize_format_text(text)
    spans: list[tuple[int, int]] = []
    for pattern in (_TIMESTAMP_DATE, common.DATE_RE):
        for match in pattern.finditer(parsed):
            if not any(start < match.end() and end > match.start() for start, end in spans):
                spans.append(match.span())
    return spans


def select_issue_date(words: list[Word], *, scoped: bool = False) -> IssueSelection:
    selections = []
    header = words if scoped else [w for w in words if HEADER_TOP <= w.cy <= HEADER_BOTTOM and w.x0 >= LABEL_MIN_X]
    for anchor in header:
        row = sorted((w for w in header if w.x0 >= anchor.x0 and _same_row(anchor, w)), key=lambda w: w.x0)
        flat = "".join(squash(w.text) for w in row)
        if not flat.startswith(_LABEL):
            continue
        remaining = len(_LABEL)
        cell_parts, cell_words = [], []
        label_end = anchor.x1
        for word in row:
            compact = squash(word.text)
            if remaining:
                used = min(remaining, len(compact))
                remaining -= used
                label_end = word.x1
                suffix = compact[used:].lstrip(":：")
                if suffix:
                    # Label and value merged into one OCR region: lexical suffix
                    # is the only admissible value, never a preceding substring.
                    # Preserve spaces in timestamps in the parsing copy.
                    raw_index = 0
                    count = 0
                    for raw_index, char in enumerate(word.text):
                        if not char.isspace():
                            count += 1
                        if count == used:
                            break
                    cell_parts.append(word.text[raw_index + 1:].lstrip(" :："))
                    cell_words.append(word)
                continue
            if any(label in compact for label in _NEXT_LABELS):
                break
            if word.x0 < label_end or word.x1 > 100:
                continue
            if word.text.strip(" :："):
                cell_parts.append(word.text.strip(" :："))
                cell_words.append(word)
        text = " ".join(cell_parts)
        parsed = normalize_format_text(text)
        match = _CELL_DATE.fullmatch(parsed) or _TIMESTAMP_DATE.fullmatch(parsed)
        value = None
        if match:
            try:
                value = date(*(int(part) for part in match.groups()))
            except ValueError:
                pass
        selections.append(IssueSelection(True, cell_words, text, value, cell_words if value else []))
    if len(selections) == 1:
        return selections[0]
    # Multiple label locations cannot establish one unambiguous source cell.
    return IssueSelection(label_found=bool(selections))

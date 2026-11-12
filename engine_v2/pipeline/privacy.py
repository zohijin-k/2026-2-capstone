"""Redact resident-number suffixes before text leaves an ingestion boundary."""
from __future__ import annotations

from datetime import date
from html import unescape
import re
from typing import Any


_RRN = re.compile(
    r"(?<![\dA-Za-z])(\d{6})([ \t\r\n]*(?:[-‐‑‒–—―−﹘﹣－~][ \t\r\n]*)?)([1-8])"
    r"((?:[ \t]*\d){6})(?!\d)"
)


def _suffix_spans(text: str):
    for match in _RRN.finditer(text):
        birth, sex = match.group(1), int(match.group(3))
        century = 2000 if sex in {3, 4, 7, 8} else 1900
        try:
            date(century + int(birth[:2]), int(birth[2:4]), int(birth[4:]))
        except ValueError:
            continue
        yield match.span(4)


def mask_rrn(text: str) -> str:
    """Keep birth and sex digit, replacing only the remaining six digits."""
    characters = list(text)
    for start, end in _suffix_spans(text):
        for index in range(start, end):
            if characters[index].isdigit():
                characters[index] = "*"
    return "".join(characters)


def mask_data(value: Any) -> Any:
    """Redact nested OCR fields, evidence and diagnostic output."""
    if isinstance(value, str):
        return mask_rrn(value)
    if isinstance(value, dict):
        return {mask_data(key): mask_data(item) for key, item in value.items()}
    if isinstance(value, list):
        return [mask_data(item) for item in value]
    if isinstance(value, tuple):
        return tuple(mask_data(item) for item in value)
    return value


def mask_markup_rrn(text: str) -> str:
    """Redact numbers split by HTML tags/entities while retaining markup."""
    visible, positions = [], []
    for token in re.finditer(r"<[^>]*>|&(?:#\d+|#x[\da-fA-F]+|\w+);|[^<&]+|[<&]", text):
        raw = token.group()
        if raw.startswith("<") and raw.endswith(">"):
            tag = re.match(r"</?\s*([\w]+)", raw)
            name = tag.group(1).lower() if tag else ""
            if name in {"td", "th", "tr", "p", "div", "li", "table", "fcel", "ecel", "nl"}:
                visible.append("\0")
                positions.append(token.span())
            elif name == "br":
                visible.append(" ")
                positions.append(token.span())
            continue
        decoded = unescape(raw)
        for index, character in enumerate(decoded):
            visible.append(character)
            positions.append(token.span() if decoded != raw else (token.start() + index, token.start() + index + 1))
    redactions = set()
    value = "".join(visible)
    for start, end in _suffix_spans(value):
        redactions.update(positions[index] for index in range(start, end) if value[index].isdigit())
    for start, end in sorted(redactions, reverse=True):
        text = text[:start] + "*" + text[end:]
    return mask_rrn(text)


def mask_words(words):
    """Redact complete and split numbers while keeping word boxes and order.

    Only adjacent words on the same geometric line can form a split number.
    Text edits have equal length, allowing suffix positions to map back to the
    original words without changing extraction coordinates or tokenization.
    """
    lines = []
    for word in sorted(words, key=lambda item: (item.bbox_px[1] + item.bbox_px[3]) / 2):
        word.text = mask_rrn(word.text)
        x0, y0, x1, y1 = word.bbox_px
        center = (y0 + y1) / 2
        height = max(y1 - y0, 1)
        if lines:
            previous = lines[-1]
            previous_center = sum((item.bbox_px[1] + item.bbox_px[3]) / 2 for item in previous) / len(previous)
            previous_height = max(item.bbox_px[3] - item.bbox_px[1] for item in previous)
            if abs(center - previous_center) <= .6 * max(height, previous_height):
                previous.append(word)
                continue
        lines.append([word])
    for line in lines:
        ordered = sorted(line, key=lambda item: item.bbox_px[0])
        fragments, offsets = [], []
        offset = 0
        previous = None
        for word in ordered:
            if previous is not None:
                gap = word.bbox_px[0] - previous.bbox_px[2]
                height = max(word.bbox_px[3] - word.bbox_px[1], previous.bbox_px[3] - previous.bbox_px[1], 1)
                separator = " " if gap <= 2 * height else "\0"
                fragments.append(separator)
                offset += 1
            offsets.append((offset, offset + len(word.text), word))
            fragments.append(word.text)
            offset += len(word.text)
            previous = word
        sanitized = mask_rrn("".join(fragments))
        for start, end, word in offsets:
            word.text = sanitized[start:end]
    return words

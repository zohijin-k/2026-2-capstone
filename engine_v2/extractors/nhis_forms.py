"""Small coordinate helpers for authored single-page NHIS portal forms."""
from __future__ import annotations

import re
from datetime import date

from . import nhis_common as common
from ..pipeline.layout import line_text, squash


def single_page(pages) -> bool:
    if len(pages) != 1:
        return False
    page, result = pages[0]
    markers = []
    for line in common.page_lines(page, result):
        # NHIS page counters occupy the top margin, separate from body dates.
        if line[0].cy > 8:
            continue
        markers.extend(re.findall(r"(?<!\d)(\d+)\s*[/／]\s*(\d+)(?!\d)", line_text(line)))
    return markers == [("1", "1")]


def confirmation_issue_date(page, result) -> tuple[date | None, list[common.Word], bool]:
    """Select a unique date-only line strictly between confirmation and issuer."""
    lines = common.page_lines(page, result)
    confirmations = [i for i, row in enumerate(lines) if "확인합니다" in squash(line_text(row))]
    if len(confirmations) != 1:
        return None, [], False
    # A seal can obscure the officer's role. The observed organization below
    # confirmation supplies the closing anchor without completing missing text.
    issuers = [i for i, row in enumerate(lines)
               if i > confirmations[0] and "국민건강보험공단" in squash(line_text(row))]
    if len(issuers) != 1:
        return None, [], False
    candidates = []
    for row in lines[confirmations[0] + 1:issuers[0]]:
        dates = common.dates_in_line(row)
        text = common.normalize_format_text(line_text(row))
        # A malformed second date is still a competing candidate, not blank
        # space to ignore after finding one valid date.
        if dates or re.search(r"\d", text):
            residue = re.sub(r"[\d\s년월일年月日./:\-‐‑‒–—―−﹘﹣－]", "", text)
            raw_dates = list(common.DATE_RE.finditer(text))
            if not raw_dates:
                raw_dates = list(common.COMPACT_DATE_RE.finditer(squash(text)))
            if len(dates) != 1 or len(raw_dates) != 1 or residue:
                return None, [], False
            candidates.append(dates[0])
    if len(candidates) != 1:
        return None, [], False
    value, words = candidates[0]
    return value, words, True


def person_table_header(page, result, anchor: str) -> common.PageHeader:
    """Read only the labeled identity table beside its form-specific anchor."""
    lines = common.page_lines(page, result)
    anchors = label_hits(lines, (anchor,))
    if len(anchors) != 1:
        return common.PageHeader(page.page)
    anchor_words = anchors[0][1]
    anchor_y = sum(w.cy for w in anchor_words) / len(anchor_words)
    headings = [row for row in lines if label_hits([row], ("성명",)) and
                label_hits([row], ("주민등록번호",))]
    headings = [row for row in headings if abs(row[0].cy - anchor_y) <=
                4 * max(w.y1 - w.y0 for w in row)]
    if len(headings) != 1:
        return common.PageHeader(page.page)
    heading = headings[0]
    names_label = label_hits([heading], ("성명",))[0][1]
    rrn_label = label_hits([heading], ("주민등록번호",))[0][1]
    top = max(w.y1 for w in heading)
    height = max(w.y1 - w.y0 for w in heading)
    # The side label can sit between the header and value baselines. Use only
    # words horizontally overlapping the actual name label, below its baseline.
    name_left, name_right = min(w.x0 for w in names_label), max(w.x1 for w in names_label)
    rrn_left, rrn_right = min(w.x0 for w in rrn_label), max(w.x1 for w in rrn_label)
    section_hits = label_hits(lines, ("자격득실확인내역", "자격확인내역"))
    bottom = min([top + 6 * height] + [min(w.y0 for w in hit) for _, hit in section_hits
                                                  if min(w.cy for w in hit) > top])
    selected = [w for row in lines for w in row
                if top < w.cy < bottom and
                (min(w.x1, name_right) > max(w.x0, name_left) or
                 min(w.x1, rrn_right) > max(w.x0, rrn_left))]
    header = common.PageHeader(page.page)
    names, rrns = [], []
    for row in common.group_lines(selected):
        name_words = [w for w in row if min(w.x1, name_right) > max(w.x0, name_left)]
        if name_words:
            value = re.sub(r"[()（）]", "", squash(line_text(name_words)))
            valid = common.NAME_RE.fullmatch(value) and not common.is_header_only_value(value)
            # A label is never a name, including a spaced header-only row.
            names.append((value if valid else None, name_words))
        rrn_words = [w for w in row if min(w.x1, rrn_right) > max(w.x0, rrn_left)]
        if rrn_words:
            value = squash(common.normalize_format_text(line_text(rrn_words)))
            match = common.MASKED_RRN_RE.fullmatch(value) or common.RRN_RE.fullmatch(value)
            rrns.append((common.birth_from_rrn(value) if match else None, rrn_words))
    # Preserve the existing merged label/value contract without scanning body rows.
    for label_words, values, label in ((names_label, names, "성명"),
                                        (rrn_label, rrns, "주민등록번호")):
        text = squash(common.normalize_format_text(line_text(label_words)))
        suffix = text.partition(label)[2].lstrip(":：")
        if suffix:
            if label == "성명":
                suffix = suffix.strip("()（）")
                value = suffix if common.NAME_RE.fullmatch(suffix) and not common.is_header_only_value(suffix) else None
            else:
                match = common.MASKED_RRN_RE.fullmatch(suffix) or common.RRN_RE.fullmatch(suffix)
                value = common.birth_from_rrn(suffix) if match else None
            values.append((value, label_words))
    if len(names) == 1 and names[0][0]:
        header.name, header.name_words = names[0]
    if len(rrns) == 1 and rrns[0][0]:
        header.birth, header.birth_words = rrns[0]
    return header


def label_hits(lines, aliases, *, x_bounds=None):
    """Compare spaced labels without joining or changing source value tokens.

    Separate one-character glyphs must share a line and reasonably regular
    spacing. Larger word fragments may form a label, but not across a cell gap.
    An explicitly observed label-cell interval permits justified glyph spacing.
    Values outside that interval never participate in the comparison.
    """
    from statistics import median

    found = []
    for row in lines:
        if x_bounds is not None:
            left, right = x_bounds
            row = [word for word in row if left <= word.x0 and word.x1 <= right]
        for alias, words in common.label_hits([row], aliases):
            if x_bounds is not None:
                found.append((alias, words))
                continue
            widths = [(w.x1 - w.x0) / max(len(squash(w.text)), 1) for w in words]
            scale = median(widths)
            gaps = [b.x0 - a.x1 for a, b in zip(words, words[1:])]
            if any(gap > 2.5 * scale for gap in gaps):
                continue
            glyphs = all(len(squash(w.text)) == 1 for w in words)
            if glyphs and len(gaps) > 1 and max(gaps) - min(gaps) > scale:
                continue
            found.append((alias, words))
    return found


def table_columns(headers, body, *, optional_columns=(), minimum_gap_ratio=1.0):
    """Map ordered headers to persistent empty vertical corridors in body words.

    Header centers only establish column order and which pair a corridor can
    separate; body interval edges supply every actual boundary. Multiple equally
    plausible corridors, overlaps without a gap, or missing evidence return None.
    Marker cells can supply evidence for otherwise empty optional columns.
    Explicit optional columns may additionally use observed header gaps within
    empty body space. Missing headers and ambiguous occupied corridors fail.
    """
    from statistics import median

    if not headers or any(not words for words in headers):
        return None
    centers = [(min(w.x0 for w in words) + max(w.x1 for w in words)) / 2 for words in headers]
    if any(a >= b for a, b in zip(centers, centers[1:])):
        return None
    words = [w for row in body for w in row if w.text.strip()]
    if not words:
        return None
    scale = median((w.x1 - w.x0) / max(len(squash(w.text)), 1) for w in words)
    minimum_gap = scale * minimum_gap_ratio
    intervals = []
    for left, right in sorted((w.x0, w.x1) for w in words):
        if intervals and left <= intervals[-1][1]:
            intervals[-1][1] = max(intervals[-1][1], right)
        else:
            intervals.append([left, right])
    gaps = [(a[1], b[0]) for a, b in zip(intervals, intervals[1:])]
    boundaries = [float('-inf')]
    for index, (left, right) in enumerate(zip(centers, centers[1:])):
        candidates = sorted(((b - a, a, b) for a, b in gaps
                             if left < (a + b) / 2 < right and b - a >= minimum_gap), reverse=True)
        if not candidates:
            if index not in optional_columns and index + 1 not in optional_columns:
                return None
            header_left = max(word.x1 for word in headers[index])
            header_right = min(word.x0 for word in headers[index + 1])
            empty = [(float('-inf'), intervals[0][0]), *gaps,
                     (intervals[-1][1], float('inf'))]
            candidates = sorted((min(b, header_right) - max(a, header_left),
                                 max(a, header_left), min(b, header_right))
                                for a, b in empty
                                if min(b, header_right) - max(a, header_left) >= minimum_gap)
            candidates.reverse()
            if not candidates:
                return None
        width, a, b = candidates[0]
        if len(candidates) > 1 and width - candidates[1][0] <= scale:
            return None
        boundaries.append((a + b) / 2)
    boundaries.append(float('inf'))
    return boundaries if all(a < b for a, b in zip(boundaries, boundaries[1:])) else None


def table_noise(word, reference_height: float) -> bool:
    """Identify OCR geometry anomalies for a caller's explicitly scoped region.

    Callers must retain ordinary cells and use this only on OCR pages in an
    observed blank/header-gap region. A low confidence by itself is insufficient.
    """
    if reference_height <= 0:
        return False
    height = word.y1 - word.y0
    width = word.x1 - word.x0
    tall = word.conf < .75 and height > 2.5 * reference_height
    tiny = word.conf < .3 and height < .6 * reference_height and width < .8 * reference_height
    return tall or tiny


def column_cells(words, boundaries):
    """Use full word intervals; an overlapping boundary is incomplete evidence."""
    cells = [[] for _ in range(len(boundaries) - 1)]
    for word in words:
        matches = [i for i, (a, b) in enumerate(zip(boundaries, boundaries[1:]))
                   if a <= word.x0 and word.x1 <= b]
        if len(matches) != 1:
            return None
        cells[matches[0]].append(word)
    return cells

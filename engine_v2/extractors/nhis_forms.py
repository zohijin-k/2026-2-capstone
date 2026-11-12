"""Small coordinate helpers for authored single-page NHIS portal forms."""
from __future__ import annotations

import re
from datetime import date

from . import nhis_common as common
from ..pipeline.layout import line_text, squash
from ..pipeline.ocr import OcrResult, OcrWord


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
    issuers = [i for i, row in enumerate(lines)
               if "국민건강보험공단" in squash(line_text(row)) and "이사장" in squash(line_text(row))]
    if len(confirmations) != 1 or len(issuers) != 1 or confirmations[0] >= issuers[0]:
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
    hits = common.label_hits(lines, (anchor,))
    anchors = hits[0][1] if hits else []
    if not anchors:
        return common.PageHeader(page.page)
    anchor_y = anchors[0].cy
    headings = [row for row in lines if abs(row[0].cy - anchor_y) <= 3 and
                common.label_hits([row], ("성명",)) and
                common.label_hits([row], ("주민등록번호",))]
    if len(headings) != 1:
        return common.PageHeader(page.page)
    heading = headings[0]
    name_words = common.label_hits([heading], ("성명",))[0][1]
    left = min(word.x0 for word in name_words)
    top = min(word.y0 for word in heading)
    bottom = max(word.y1 for word in heading) + 6
    selected = [word for row in lines for word in row
                if word.x0 >= left - .5 and top <= word.cy <= bottom]
    scoped = OcrResult(result.engine, [OcrWord(word.text, word.conf, word.px) for word in selected])
    header = common.header_for_page(page, scoped)
    rrn_words = common.label_hits([heading], ("주민등록번호",))[0][1]
    rrn_left = min(word.x0 for word in rrn_words)
    heading_bottom = max(word.cy for word in heading)
    names = []
    for row in common.group_lines(selected):
        if row[0].cy <= heading_bottom:
            continue
        words = [word for word in row if left - .5 <= word.x0 < rrn_left]
        if words:
            value = re.sub(r"[()（）]", "", squash(line_text(words)))
            name = value if common.NAME_RE.fullmatch(value) and not common.is_header_only_value(value) else None
            names.append((name, words))
    # Keep the established merged-label token handling without scanning any
    # household/body rows outside this small identity table.
    if header.name and header.name_words and all(word.cy <= heading_bottom for word in header.name_words):
        names.append((header.name, header.name_words))
    if len(names) == 1 and names[0][0]:
        header.name, header.name_words = names[0]
    else:
        header.name = header.name_words = None

    rrns = []
    for row in common.group_lines(selected):
        words = [word for word in row if word.x0 >= rrn_left - .5]
        text = squash(common.normalize_format_text(line_text(words)))
        # A label may be merged with its value, but unrelated text or an
        # overlong mask cannot be discarded around a plausible number.
        if text.startswith("주민등록번호"):
            text = text[len("주민등록번호"):].lstrip(":：")
        if not text:
            continue
        match = common.MASKED_RRN_RE.fullmatch(text) or common.RRN_RE.fullmatch(text)
        rrns.append((common.birth_from_rrn(match.group()) if match else None, words))
    if len(rrns) == 1 and rrns[0][0] is not None:
        header.birth, header.birth_words = rrns[0]
    else:
        header.birth = header.birth_words = None
    return header


def label_hits(lines, aliases):
    """Compare spaced labels without joining or changing source value tokens.

    Separate one-character glyphs must share a line and reasonably regular
    spacing. Larger word fragments may form a label, but not across a cell gap.
    Legacy readers retain their existing common.label_hits behavior.
    """
    from statistics import median

    found = []
    for row in lines:
        for alias, words in common.label_hits([row], aliases):
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


def table_columns(headers, body):
    """Map ordered headers to persistent empty vertical corridors in body words.

    Header centers only establish column order and which pair a corridor can
    separate; body interval edges supply every actual boundary. Multiple equally
    plausible corridors, overlaps without a gap, or missing evidence return None.
    Marker cells can supply evidence for otherwise empty optional columns.
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
    intervals = []
    for left, right in sorted((w.x0, w.x1) for w in words):
        if intervals and left <= intervals[-1][1]:
            intervals[-1][1] = max(intervals[-1][1], right)
        else:
            intervals.append([left, right])
    gaps = [(a[1], b[0]) for a, b in zip(intervals, intervals[1:])]
    boundaries = [float('-inf')]
    for left, right in zip(centers, centers[1:]):
        candidates = sorted(((b - a, a, b) for a, b in gaps
                             if left < (a + b) / 2 < right and b - a >= scale), reverse=True)
        if not candidates:
            return None
        width, a, b = candidates[0]
        if len(candidates) > 1 and width - candidates[1][0] <= scale:
            return None
        boundaries.append((a + b) / 2)
    boundaries.append(float('inf'))
    return boundaries


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

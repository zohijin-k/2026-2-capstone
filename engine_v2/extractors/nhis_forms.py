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
    anchors = [word for row in lines for word in row if anchor in squash(word.text)]
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
        matches = list(common.MASKED_RRN_RE.finditer(text)) + list(common.RRN_RE.finditer(text))
        rrns.extend((common.birth_from_rrn(match.group()), words) for match in matches)
    if len(rrns) == 1 and rrns[0][0] is not None:
        header.birth, header.birth_words = rrns[0]
    else:
        header.birth = header.birth_words = None
    return header

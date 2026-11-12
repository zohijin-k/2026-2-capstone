"""Independent date-omission evidence; do not use date-dependent parsed history rows."""
import re
from dataclasses import replace
from types import SimpleNamespace
from statistics import median
from . import nhis_common as common, nhis_forms as forms
from ..pipeline.layout import line_text, squash
from .format_text import normalize_format_text


def _positional_page(page, result):
    """Prove blank observed date columns without depending on parsed history.

    Numbered row anchors distinguish address continuations from separate rows.
    All geometry remains in page percentages; header comparison alone removes
    spacing/OCR prefix noise, without changing any source value token.
    """
    lines = common.page_lines(page, result)
    unknown = {"status": "UNDETERMINED", "digits": False}
    numbers = [w for row in lines for w in row if squash(w.text) == "번호"
               and w.x0 < 15 and 16 < w.cy < 65 and w.conf >= .85]
    if len(numbers) != 1:
        return unknown
    number = numbers[0]
    header = [row for row in lines if abs(row[0].cy - number.cy) < 3.5]
    # e.g. a noisy prefix before spaced 신고일 still locates its whole box.
    comparison = [[replace(w, text=re.sub(r"[^가-힣]", "", w.text)) for w in row]
                  for row in header]
    if any(squash(line_text(row)).count(label) > 1
           for row in comparison for label in ("발생일", "신고일")):
        return unknown
    hits = forms.label_hits(comparison, ("발생일", "신고일"))
    columns = []
    for label in ("발생일", "신고일"):
        boxes = {(min(w.x0 for w in ws), max(w.x1 for w in ws),
                  min(w.y0 for w in ws), max(w.y1 for w in ws))
                 for found, ws in hits if found == label}
        if len(boxes) != 1:
            return unknown
        columns.append(next(iter(boxes)))
    first, second = columns
    if not (number.x1 < first[0] and
            (first[0] + first[1]) / 2 < (second[0] + second[1]) / 2):
        return unknown
    top = max(number.y1, *(box[3] for box in columns))
    ends = [min(w.y0 for w in row) for row in lines if row[0].cy > top
            and ("이하여백" in squash(line_text(row)) or
                 ("병역" in squash(line_text(row)) and row[0].x0 < 12) or
                 squash(line_text(row)).startswith(("※", "수수료")))]
    if not ends:
        return unknown  # Without a table end, numbered footer notes are not rows.
    end = min(ends)
    body = [w for row in lines for w in row if top < w.cy < end]
    # Any overlapping digit-bearing word, however faint or malformed, vetoes
    # omission. Never use a center-only test that drops a boundary-crossing date.
    digits = any(re.search(r"\d", normalize_format_text(w.text)) and
                 any(w.x0 < right and w.x1 > left for left, right, _, _ in columns)
                 for w in body)
    if digits:
        return {"status": "UNDETERMINED", "digits": True}
    ordinals = sorted([w for w in body if number.x0 <= (w.x0+w.x1)/2 <= number.x1
                       and re.fullmatch(r"[0-9]{1,3}", w.text) and w.conf >= .9],
                      key=lambda w: w.cy)
    row_count = 0
    for index, ordinal in enumerate(ordinals):
        row_top = (ordinals[index-1].cy + ordinal.cy)/2 if index else top
        row_end = (ordinal.cy + ordinals[index+1].cy)/2 if index+1 < len(ordinals) else end
        address = [w for w in body if row_top < w.cy < row_end
                   and number.x1 < w.x0 and w.x1 < first[0]]
        if any(re.search(r"[가-힣]", w.text) for w in address):
            row_count += 1
    if row_count < 2:
        return unknown
    return {"status": "MISSING", "digits": False, "page": page.page,
            "rows": row_count, "reason": "rows_without_dates",
            "basis": "positional_blank_date_columns"}


def assess(pages, *, type_confidence):
    unknown = {"status": "UNDETERMINED", "confidence": 0.0}
    if type_confidence < .85:
        return unknown
    # A categorical type score is not confidence in the title's source words.
    from ..pipeline.resident_title import classify_resident_title
    reliable_pages = [(page, SimpleNamespace(words=[w for w in result.words if w.confidence >= .85]))
                      for page, result in pages]
    kind, _ = classify_resident_title(reliable_pages)
    title_kinds = {kind} if kind else set()
    for page, result in pages:
        lines = common.page_lines(page, result)
        heights = [w.y1-w.y0 for row in lines for w in row if re.search("[가-힣]", w.text)]
        ordinary = median(heights) if heights else 0
        for row in lines:
            text = re.sub(r"[\s()（）]", "", line_text(row))
            if (row[0].cy < 25 and all(w.conf >= .85 for w in row) and
                    max(w.y1-w.y0 for w in row) >= 1.25*ordinary):
                if text == "주민등록표초본":
                    title_kinds.add("abstract")
                elif text == "주민등록표등본":
                    title_kinds.add("register")
    if title_kinds != {"abstract"}:
        return unknown
    positional = [_positional_page(page, result) for page, result in pages]
    if positional and all(item["status"] == "MISSING" for item in positional):
        return {"status": "MISSING", "confidence": .95,
                "pages": [{key: value for key, value in item.items()
                           if key not in {"status", "digits"}} for item in positional]}
    evidence = []
    any_dates = False
    for page, result in pages:
        lines = common.page_lines(page, result)
        numbers = [w for row in lines for w in row if squash(w.text) == "번호" and w.x0 < 15 and 16 < w.cy < 65]
        if len(numbers) != 1:
            return unknown
        number = numbers[0]
        header = [row for row in lines if abs(row[0].cy - number.cy) < 3.5]
        addr = [(label, words) for label, words in forms.label_hits(header, ("주소",))
                if all(12 < ((w.x0 + w.x1) / 2) < 50 for w in words)]
        if len(addr) != 1 or min(number.conf, *(w.conf for w in addr[0][1])) < .85:
            return unknown
        bottom = max([number.y1] + [w.y1 for _, ws in addr for w in ws])
        end = min([78] + [min(w.y0 for w in row) for row in lines
                           if row[0].cy > bottom and "이하여백" in squash(line_text(row))])
        body = [w for row in lines for w in row if bottom + 1 < w.cy < end]
        ordinals = sorted([w for w in body if w.x1 < 12 and re.fullmatch(r"[0-9]{1,3}", w.text) and w.conf >= .9], key=lambda w:w.cy)
        row_count = 0
        for i, ordinal in enumerate(ordinals):
            top = ordinal.cy - 2.5
            tail = (ordinal.cy + ordinals[i+1].cy) / 2 if i+1 < len(ordinals) else min(end,ordinal.cy+5)
            address = [w for w in body if 12 <= ((w.x0 + w.x1) / 2) < 50 and top < w.cy < tail]
            # An observed administrative-region address plus its ordinal proves a row.
            if any(w.conf >= .9 and re.search(r"(?:특별자치도|특별시|광역시|[가-힣]+도)", w.text) for w in address):
                row_count += 1
        date_labels = {label for label, _ in forms.label_hits(header, ("발생일", "신고일"))}
        if not row_count and date_labels:
            return unknown
        date_words = [w for w in body if 50 <= ((w.x0 + w.x1) / 2) < 77.5]
        from ..pipeline.layout import group_lines
        has_dates = any(common.parse_date(line_text(row)) is not None for row in group_lines(date_words))
        any_dates |= has_dates
        # Digits/unreadable date punctuation are evidence of failed reading, not blank cells.
        ambiguous = any(re.search(r"[0-9?？]|[-–—./]{2,}", normalize_format_text(w.text)) for w in date_words)
        reasons = {"전입", "전출", "등록", "신규등록", "세대주변경", "주소변경", "행정구역변경", "도로명주소변경"}
        ambiguous |= any(w.conf < .8 or (squash(w.text) and squash(w.text) not in reasons)
                         for w in date_words)
        if not has_dates and ambiguous:
            return unknown
        if not has_dates:
            evidence.append({"page": page.page, "rows": row_count,
                             "reason": "rows_without_dates" if date_labels else "date_headers_absent"})
        elif not date_labels:
            return unknown  # Contradictory layout rather than certain option omission.
    if evidence and not any_dates:
        if any(item["digits"] for item in positional):
            return unknown
        return {"status": "MISSING", "confidence": .95, "pages": evidence}
    if evidence:
        return unknown
    return {"status": "PRESENT", "confidence": .95} if any_dates else unknown

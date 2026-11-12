"""Independent date-omission evidence; do not use date-dependent parsed history rows."""
import re
from . import nhis_common as common, nhis_forms as forms
from ..pipeline.layout import line_text, squash
from .format_text import normalize_format_text


def assess(pages, *, type_confidence):
    unknown = {"status": "UNDETERMINED", "confidence": 0.0}
    if type_confidence < .85:
        return unknown
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
        if not row_count:
            return unknown
        date_words = [w for w in body if 50 <= ((w.x0 + w.x1) / 2) < 77.5]
        has_dates = any(common.parse_date(line_text(row)) is not None for row in lines
                        if row[0].cy > bottom + 1 and row[0].cy < end and
                        any(w in date_words for w in row))
        any_dates |= has_dates
        # Digits/unreadable date punctuation are evidence of failed reading, not blank cells.
        ambiguous = any(re.search(r"[0-9?？]|[-–—./]{2,}", normalize_format_text(w.text)) for w in date_words)
        reasons = {"전입", "전출", "등록", "신규등록", "세대주변경", "주소변경", "행정구역변경", "도로명주소변경"}
        ambiguous |= any(w.conf < .8 or (squash(w.text) and squash(w.text) not in reasons)
                         for w in date_words)
        if not has_dates and ambiguous:
            return unknown
        date_labels = {label for label, _ in forms.label_hits(header, ("발생일", "신고일"))}
        if not has_dates:
            evidence.append({"page": page.page, "rows": row_count,
                             "reason": "rows_without_dates" if date_labels else "date_headers_absent"})
        elif not date_labels:
            return unknown  # Contradictory layout rather than certain option omission.
    if evidence and not any_dates:
        return {"status": "MISSING", "confidence": .95, "pages": evidence}
    if evidence:
        return unknown
    return {"status": "PRESENT", "confidence": .95} if any_dates else unknown

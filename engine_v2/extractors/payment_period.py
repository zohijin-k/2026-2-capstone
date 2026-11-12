"""Independent, bounded payment-period evidence; never infer a period from a slot."""
from __future__ import annotations

import json
import re

from . import nhis_common as common
from .format_text import normalize_format_text
from ..pipeline.layout import line_text, squash


FIELD = "고지월검증자료"
_MONTH = r"(20\d{2})(?:년|[./-])(1[0-2]|0?[1-9])(?:월|\.?)(?!\d)"
_PERIOD = re.compile(_MONTH + r"[~～\-]" + _MONTH)
_ROW_MONTH = re.compile(r"(?:(20\d{2})[./-])?(0?[1-9]|1[0-2])월?\.?$")
_MONEY = re.compile(r"[0-9]+(?:,[0-9]{3})*")
MIN_CONFIDENCE = .85


def _period(text):
    text = normalize_format_text(squash(text))
    matches = list(_PERIOD.finditer(text))
    if len(matches) != 1:
        return None
    residue = _PERIOD.sub("", text)
    for label in ("조회기간", "납부내역", "단위", "원"):
        residue = residue.replace(label, "")
    if re.search(r"[^\s:：()（）\[\]]", residue):
        return None
    match = matches[0]
    start = f"{int(match[1]):04}-{int(match[2]):02}"
    end = f"{int(match[3]):04}-{int(match[4]):02}"
    return [start, end] if start <= end else None


def collect(pages, extraction) -> dict[str, object]:
    """Keep confidence of printed dates separate from incomplete money/identity.

    A twelve-row calendar contains zero placeholders outside the query range.
    Only positive observed amounts or explicit year-month rows contradict it.
    Ambiguous or low-confidence competing evidence requires review.
    """
    periods = []
    uncertain = False
    row_months = []
    for page, result in pages:
        lines = common.page_lines(page, result)
        table_top = min((word.y0 for row in lines for word in row
                         if squash(word.text) in {"고지금액", "고지보험료", "납부금액", "월별", "년월"}),
                        default=100)
        page_periods = []
        for index, row in enumerate(lines):
            if min(word.y0 for word in row) >= table_top:
                continue
            text = squash(line_text(row))
            if not any(label in text for label in ("조회기간", "납부내역")):
                continue
            selected = row
            parsed = _period(line_text(selected))
            if parsed is None and "조회기간" in text and index + 1 < len(lines):
                following = lines[index + 1]
                height = max(word.y1 - word.y0 for word in row + following)
                if min(word.y0 for word in following) - max(word.y1 for word in row) <= height * 2:
                    selected = row + following
                    parsed = _period(line_text(selected))
            if parsed is None or any(word.conf < MIN_CONFIDENCE for word in selected):
                uncertain = True
            else:
                periods.append(parsed)
                page_periods.append(parsed)

        # Reconcile actual row evidence even if the amount extractor could not
        # find all component columns. A missing header is not period evidence.
        unique = {tuple(value) for value in page_periods}
        period = next(iter(unique)) if len(unique) == 1 else None
        for row in lines:
            if not row or min(word.y0 for word in row) <= table_top:
                continue
            first = row[0]
            text = normalize_format_text(squash(first.text))
            match = _ROW_MONTH.fullmatch(text)
            if not match or not ("월" in text or match[1]):
                continue
            # Month labels form the leftmost table column, never amount cells.
            if first.x0 > 25:
                continue
            year = int(match[1]) if match[1] else int(period[0][:4]) if period else None
            month = int(match[2])
            if year is not None and period and period[0][:4] != period[1][:4] and month < int(period[0][5:]):
                year += 1
            amounts = [word for word in row[1:] if _MONEY.fullmatch(squash(word.text))]
            positive = [word for word in amounts if int(squash(word.text).replace(",", "")) > 0]
            if year is not None:
                ym = f"{year:04}-{month:02}"
                row_months.append({"month": ym, "positive": bool(positive), "explicit_year": bool(match[1])})
                if period and not period[0] <= ym <= period[1] and (positive or match[1]):
                    # Uncertain competing values also prevent certain rejection.
                    uncertain = uncertain or any(word.conf < MIN_CONFIDENCE for word in [first, *positive])

    unique = {tuple(value) for value in periods}
    period = list(next(iter(unique))) if len(unique) == 1 else None
    conflict = len(unique) > 1 or bool(period and any(
        not period[0] <= row["month"] <= period[1] and (row["positive"] or row["explicit_year"])
        for row in row_months))
    # The government reader separately proves headers, columns, all arithmetic
    # and blank-cell boundaries. This must not rely on document confidence.
    validations = {check.name: check.passed for check in extraction.validations}
    amounts_certain = (validations.get("payment_billing_absence_certain") is True and
                       validations.get("paid_total_matches") is True)
    rows = None
    try:
        rows = json.loads(extraction.fields["월별납부내역"].value)
    except (KeyError, TypeError, ValueError):
        pass
    absent_amount_months = []
    if amounts_certain and isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                amounts_certain = False
                break
            value = (row.get("고지") or {}).get("건강보험료")
            if value is None or str(value).strip() in {"", "0"}:
                absent_amount_months.append(row.get("월"))
    return {"version": 1, "status": "CONFLICT" if conflict else
            "READABLE" if period and not uncertain else "UNDETERMINED",
            "period": period, "periods": periods, "month_rows": row_months,
            "amounts_certain": bool(amounts_certain and not uncertain and not conflict and period),
            "absent_amount_months": absent_amount_months}

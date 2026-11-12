"""Bounded eight-column government payment form reader."""
from __future__ import annotations

import json
import re

from . import nhis_common as common, nhis_forms as forms
from .format_text import normalize_format_text, normalize_numeric_text
from ..pipeline.layout import line_text, squash
from ..pipeline.preprocess import PageSource
from ..schemas.models import DocType


DOCUMENT_NUMBER = re.compile(r"(?<!\d)\d{4}-\d{4}-\d{4}-\d{4,5}(?!\d)")
MONTH = re.compile(r"(0?[1-9]|1[0-2])월")
PERIOD = re.compile(r"(20\d{2})년(0?[1-9]|1[0-2])월[~～-](20\d{2})년(0?[1-9]|1[0-2])월납부내역")
COMPONENTS = ("건강보험료", "장기요양보험료", "보수외소득월액(건강)", "보수외소득월액(요양)")
HEADERS = ("월별", *COMPONENTS, *COMPONENTS)
OPTIONAL_COLUMNS = (3, 4, 7, 8)


def recognizes(pages) -> bool:
    text = squash(" ".join(result.text for _, result in pages))
    title = "보험료납부확인서" in text
    government_number = "문서확인번호" in text and DOCUMENT_NUMBER.search(normalize_format_text(text))
    information_grid = "납부자번호" in text and "사업장명칭" in text
    words = [word for page, result in pages for row in common.page_lines(page, result) for word in row]
    header_top = min((word.y0 for word in words if "보수외" in squash(word.text)), default=float('inf'))
    first_month = min((word.y0 for word in words if word.y0 > header_top and MONTH.fullmatch(squash(word.text))),
                      default=float('inf'))
    header_text = squash(" ".join(word.text for word in words if word.cy < first_month))
    eight_columns = header_text.count("보수외") >= 3 and header_text.count("소득월액") >= 3
    return bool(title and (government_number or information_grid) and eight_columns)


def _unique_label(lines, label):
    hits = forms.label_hits(lines, (label,))
    return hits[0][1] if len(hits) == 1 else []


def _value_cells(lines, left_label, right_label):
    left = _unique_label(lines, left_label)
    right = _unique_label(lines, right_label)
    if not left or not right:
        return None
    height = max(word.y1 - word.y0 for word in left + right)
    left_y = sum(word.cy for word in left) / len(left)
    right_y = sum(word.cy for word in right) / len(right)
    if abs(left_y - right_y) > height or max(word.x1 for word in left) >= min(word.x0 for word in right):
        return None
    label_ids = {id(word) for word in left + right}
    selected = [word for row in lines for word in row
                if id(word) not in label_ids and abs(word.cy - (left_y + right_y) / 2) <= height * .8]
    left_edge = max(word.x1 for word in left)
    right_start = min(word.x0 for word in right)
    right_edge = max(word.x1 for word in right)
    first = [word for word in selected if left_edge < word.x0 and word.x1 < right_start]
    second = [word for word in selected if word.x0 > right_edge]
    return first, second


def _text(words):
    return line_text(sorted(words, key=lambda word: word.x0))


def _date_cell(words):
    text = normalize_format_text(squash(_text(words)))
    if re.fullmatch(r"\d{4}(?:년\d{1,2}월\d{1,2}일|[./-]\d{1,2}[./-]\d{1,2}\.?)", text) is None:
        return None
    return common.parse_date(text)


def _header_columns(words):
    clusters = []
    for word in sorted(words, key=lambda item: item.x0):
        if clusters and word.x0 <= max(item.x1 for item in clusters[-1]):
            clusters[-1].append(word)
        else:
            clusters.append([word])
    if len(clusters) != len(HEADERS):
        return None
    for index, (cluster, expected) in enumerate(zip(clusters, HEADERS)):
        value = squash("".join(word.text for word in sorted(cluster, key=lambda item: (item.cy, item.x0))))
        if index == 0:
            valid = value in {"월별", "년월", "월"}
        else:
            valid = value == expected
        if not valid:
            return None
    return clusters


def _money_cell(words, *, allow_correction, row, column, corrections):
    text = squash(_text(words))
    if not text:
        return None, True
    normalized, categories = normalize_numeric_text(text)
    if normalized is None or (categories and not allow_correction):
        return None, False
    if categories:
        corrections.append({"row": row, "column": column, "categories": list(categories)})
    return int(normalized.replace(",", "")), True


def _monthly_table(lines, *, allow_correction):
    checks = []
    corrections = []
    groups = [_unique_label(lines, label) for label in ("고지금액", "납부금액")]
    group_ok = all(groups) and max(word.x1 for word in groups[0]) < min(word.x0 for word in groups[1])
    checks.append(common.Validation("payment_group_headers", bool(group_ok)))
    words = [word for row in lines for word in row]
    group_bottom = max((word.y1 for group in groups for word in group), default=float('inf'))
    months = [word for word in words if word.y0 > group_bottom and MONTH.fullmatch(squash(word.text))]
    months.sort(key=lambda word: word.cy)
    sequence = [int(MONTH.fullmatch(squash(word.text))[1]) for word in months]
    months_ok = sequence == list(range(1, 13))
    checks.append(common.Validation("monthly_rows_found", months_ok))
    checks.append(common.Validation("months_continuous", months_ok))
    sums = _unique_label(lines, "합계")
    sum_y = sum(word.cy for word in sums) / len(sums) if sums else float('inf')
    first_y = min((word.y0 for word in months), default=float('-inf'))
    header_words = [word for word in words if word.y0 > group_bottom and word.cy < first_y]
    headers = _header_columns(header_words) if group_ok and months else None
    alignment = headers is not None and all(
        min(word.x0 for word in headers[start]) < sum((word.x0 + word.x1) / 2 for word in group) / len(group)
        < max(word.x1 for word in headers[end])
        for group, start, end in zip(groups, (1, 5), (4, 8)))
    checks.append(common.Validation("payment_component_headers", bool(alignment)))
    sum_height = max((word.y1 - word.y0 for word in sums), default=0)
    body = [word for word in words if first_y <= word.cy <= sum_y + sum_height * .8]
    boundaries = forms.table_columns(headers, [body], optional_columns=OPTIONAL_COLUMNS,
                                     minimum_gap_ratio=.5) if headers and sums else None
    checks.append(common.Validation("payment_columns", boundaries is not None))
    checks.append(common.Validation("payment_sum_row", bool(sums) and bool(months) and sum_y > months[-1].cy))
    if not months_ok or boundaries is None or not sums or sum_y <= months[-1].cy:
        return [], [], corrections, checks

    row_height = min(b.cy - a.cy for a, b in zip(months, months[1:]))
    bands = [[] for _ in months]
    sum_words = []
    rows_ok = True
    for word in body:
        if abs(word.cy - sum_y) <= max(item.y1 - item.y0 for item in sums) * .8:
            sum_words.append(word)
            continue
        nearest = min(range(len(months)), key=lambda index: abs(months[index].cy - word.cy))
        if abs(months[nearest].cy - word.cy) > row_height * .45:
            rows_ok = False
        bands[nearest].append(word)

    values = []
    for month, band in zip(months, bands):
        cells = forms.column_cells(band, boundaries)
        if cells is None or squash(_text(cells[0])) != squash(month.text):
            rows_ok = False
            continue
        row_values = []
        for column, cell in enumerate(cells[1:], 1):
            amount, numeric = _money_cell(cell, allow_correction=allow_correction,
                                          row=squash(month.text), column=column, corrections=corrections)
            required = column not in OPTIONAL_COLUMNS
            rows_ok &= numeric and (amount is not None or not required)
            row_values.append(amount)
        values.append(row_values)
    checks.append(common.Validation("monthly_amounts_numeric", rows_ok and len(values) == 12))
    sum_cells = forms.column_cells(sum_words, boundaries)
    totals = []
    total_numeric = sum_cells is not None and squash(_text(sum_cells[0])) == "합계"
    if sum_cells:
        for column, cell in enumerate(sum_cells[1:], 1):
            amount, numeric = _money_cell(cell, allow_correction=allow_correction,
                                          row="합계", column=column, corrections=corrections)
            total_numeric &= numeric and (amount is not None or column in OPTIONAL_COLUMNS)
            totals.append(amount)
    matches = []
    for column in range(8):
        observed = [row[column] for row in values]
        total = totals[column] if len(totals) == 8 else None
        empty = not any(value is not None for value in observed)
        matches.append(total_numeric and rows_ok and len(values) == 12 and
                       ((empty and total is None) or (total is not None and sum(value or 0 for value in observed) == total)))
    checks.append(common.Validation("monthly_total_matches", all(matches)))
    for column, matched in enumerate(matches, 1):
        checks.append(common.Validation(f"payment_column_{column}_sum", bool(matched)))
    return values, totals, corrections, checks


def extract(pages, today=None):
    from .nhis_payment import PaymentResult, _average

    page_map = {page.page: page for page, _ in pages}
    sources = common.sources_by_page(pages)
    lines = [line for page, result in pages for line in common.page_lines(page, result)]
    checks = [common.Validation("document_type", True), common.Validation("payment_single_page", len(pages) == 1)]
    fields = {}

    def put(label, value, words=None):
        raw = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        fields[label] = common.make_field(raw, raw, words, page_map, .95, sources)

    top = _value_cells(lines, "가입자성명", "생년월일")
    name = squash(_text(top[0])) if top else ""
    name_ok = bool(common.NAME_RE.fullmatch(name)) and not common.is_header_only_value(name)
    checks.append(common.Validation("성명_consistent", name_ok))
    if name_ok:
        put("성명", name, top[0])
    birth = _date_cell(top[1]) if top else None
    checks.append(common.Validation("생년월일_consistent", birth is not None))
    if birth:
        put("생년월일", birth.isoformat(), top[1])

    middle = _value_cells(lines, "사업장명칭", "납부자번호")
    payer = squash(_text(middle[1])) if middle else ""
    checks.append(common.Validation("payment_information_cells", middle is not None and bool(re.fullmatch(r"\d{11}", payer))))
    if middle is not None:
        put("사업장명칭", _text(middle[0]), middle[0])
    if re.fullmatch(r"\d{11}", payer):
        put("납부자번호", payer, middle[1])

    number_rows = [row for row in lines if "문서확인번호" in squash(line_text(row))]
    numbers = [match.group() for row in number_rows
               for match in DOCUMENT_NUMBER.finditer(normalize_format_text(line_text(row)))]
    checks.append(common.Validation("document_number_format", len(numbers) == 1))
    if len(numbers) == 1:
        put("문서확인번호", numbers[0], number_rows[0])

    periods = [(match, row) for row in lines
               if (match := PERIOD.fullmatch(normalize_format_text(squash(line_text(row)))))]
    period_ok = len(periods) == 1 and periods[0][0][1] == periods[0][0][3] and int(periods[0][0][2]) <= int(periods[0][0][4])
    checks.append(common.Validation("payment_query_period", period_ok))
    year = int(periods[0][0][1]) if period_ok else None
    if period_ok:
        match, row = periods[0]
        put("조회기간", [f"{year}-{int(match[2]):02}", f"{year}-{int(match[4]):02}"], row)

    allow_correction = all(page.source != PageSource.TEXT_LAYER and result.engine != "text_layer" for page, result in pages)
    values, totals, corrections, table_checks = _monthly_table(lines, allow_correction=allow_correction)
    checks.extend(table_checks)
    bottom = _value_cells(lines, "납부총액", "용도구분")
    grand_total, total_ok = _money_cell(bottom[0], allow_correction=allow_correction,
                                       row="납부총액", column="total", corrections=corrections) if bottom else (None, False)
    purpose = squash(_text(bottom[1])) if bottom else ""
    checks.append(common.Validation("payment_purpose", bool(purpose)))
    if purpose:
        put("용도구분", purpose, bottom[1])
    if total_ok and grand_total is not None:
        put("납부총액", str(grand_total), bottom[0])
    paid_matches = total_ok and grand_total is not None and len(totals) == 8 and grand_total == sum(value or 0 for value in totals[4:])
    checks.append(common.Validation("paid_total_matches", bool(paid_matches)))

    issue, issue_words, issue_ok = forms.confirmation_issue_date(*pages[0]) if len(pages) == 1 else (None, [], False)
    checks.append(common.Validation("발급일_consistent", issue_ok))
    if issue is not None:
        put("발급일", issue.isoformat(), issue_words)

    arithmetic_ok = all(check.passed for check in checks if check.name in {"monthly_total_matches", "paid_total_matches"})
    checks.append(common.Validation("numeric_cell_corrections", arithmetic_ok if corrections else True,
                                    json.dumps(corrections, ensure_ascii=False, separators=(",", ":"))))
    if corrections:
        put("숫자형식교정", corrections)

    if len(values) == 12 and year is not None:
        rows = []
        for month, amounts in enumerate(values, 1):
            rows.append({"월": f"{year}-{month:02}",
                         "고지": dict(zip(COMPONENTS, (str(value) if value is not None else None for value in amounts[:4]))),
                         "납부": dict(zip(COMPONENTS, (str(value) if value is not None else None for value in amounts[4:])))})
        put("월별납부내역", rows)
        for label, column in (("월별고지금액", 0), ("월별장기요양보험료", 1), ("월별보수외소득월액_건강", 2)):
            observed = {(year, month): (row[column], []) for month, row in enumerate(values, 1) if row[column] is not None}
            if observed:
                put(label, {f"{y}-{month:02}": str(amount) for (y, month), (amount, _) in observed.items()})
            average, _ = _average(observed)
            average_label = {0: "건강보험료", 1: "장기요양보험료", 2: "보수외소득월액_건강"}[column]
            if average is not None:
                put(average_label, str(average))
        put("고지월", ",".join(f"{year}-{month:02}" for month in range(1, 13)))
    if len(totals) == 8:
        put("합계자료", [str(value) if value is not None else None for value in totals])

    complete = all(check.passed for check in checks)
    if not complete:
        for extracted in fields.values():
            extracted.confidence = min(extracted.confidence, .4)
    warnings = [] if complete else ["납부확인서의 필수 정보 또는 월별 금액·합계를 완전히 확인하지 못했습니다."]
    return PaymentResult(DocType.NHIS_PAYMENT, .95, fields, checks, warnings,
                         form_kind="government_payment", structure_complete=complete)

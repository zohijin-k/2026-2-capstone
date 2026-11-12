"""Bounded eight-column government payment form reader."""
from __future__ import annotations

import json
import re
from statistics import median

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
GROUPS = ("고지금액", "납부금액")


def recognizes(pages) -> bool:
    text = squash(" ".join(result.text for _, result in pages))
    title = "보험료납부확인서" in text
    government_number = "문서확인번호" in text and DOCUMENT_NUMBER.search(normalize_format_text(text))
    information_grid = "납부자번호" in text and "사업장명칭" in text
    words = [word for page, result in pages for row in common.page_lines(page, result) for word in row]
    component_top = _component_top(words)
    months = [word for word in words if word.y0 > component_top and MONTH.fullmatch(squash(word.text))]
    first_month = min(months, key=lambda word: word.y0) if months else None
    header_words = [word for word in words if first_month is not None
                    and first_month.y0 - 3 * (first_month.y1 - first_month.y0) <= word.y0
                    and word.cy < first_month.y0]
    component_top = _component_top(header_words)
    header_words = [word for word in header_words if word.y0 >= component_top]
    header_text = " ".join(squash("".join(line_text(row) for row in common.group_lines(cluster, tol=.25)))
                           for cluster in _header_clusters(header_words))
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
    accounted = {id(word) for word in first + second}
    label_start = min(word.x0 for word in left)
    if any(word.x1 > label_start and id(word) not in accounted for word in selected):
        return None
    return first, second


def _text(words):
    return line_text(sorted(words, key=lambda word: word.x0))


def _workplace_evidence(lines, middle, period_rows, complete):
    """Keep optional income evidence separate from the existing form checks."""
    left = _unique_label(lines, "사업장명칭")
    right = _unique_label(lines, "납부자번호")
    above = _unique_label(lines, "가입자성명") + _unique_label(lines, "생년월일")
    labels = left + right
    if not (complete and middle is not None and left and right and above and len(period_rows) == 1):
        return "못 읽음", labels
    if squash(_text(left)) != "사업장명칭" or squash(_text(right)) != "납부자번호":
        return "못 읽음", labels
    top = (max(word.y1 for word in above) + min(word.y0 for word in labels)) / 2
    bottom = (max(word.y1 for word in labels) + min(word.y0 for word in period_rows[0])) / 2
    start, end = max(word.x1 for word in left), min(word.x0 for word in right)
    if top >= min(word.y0 for word in labels) or bottom <= max(word.y1 for word in labels):
        return "못 읽음", labels
    label_ids = {id(word) for word in labels}
    words = [word for row in lines for word in row if id(word) not in label_ids and
             word.x1 > start and word.x0 < end and word.y1 > top and word.y0 < bottom]
    if any(word.x0 <= start or word.x1 >= end or word.y0 < top or word.y1 > bottom or
           word.conf < .85 for word in words) or any(word.conf < .85 for word in labels + above):
        return "못 읽음", labels + words
    if all(not re.search(r"[^\s|:：.·=~\-－—–]", word.text) for word in words):
        return "확실한 공란", left + words
    text = _text(words)
    valid = (bool(re.search(r"[가-힣A-Za-z]", text)) and
             re.fullmatch(r"[가-힣A-Za-z0-9\s()（）&.,·'’\-]+", text) and
             not common.is_header_only_value(text))
    return ("값 있음" if valid else "못 읽음"), left + words


def _date_cell(words):
    text = normalize_format_text(squash(_text(words)))
    if re.fullmatch(r"\d{4}(?:년\d{1,2}월\d{1,2}일|[./-]\d{1,2}[./-]\d{1,2}\.?)", text) is None:
        return None
    return common.parse_date(text)


def _component_top(words):
    return min((word.y0 for word in words
                if any(squash(word.text) in label for label in COMPONENTS)
                and not any(squash(word.text) in label for label in GROUPS)), default=float('inf'))


def _header_clusters(words):
    if not words:
        return []
    glyph_width = median((word.x1 - word.x0) / max(len(squash(word.text)), 1) for word in words)
    clusters = []
    for word in sorted(words, key=lambda item: item.x0):
        if clusters and word.x0 <= max(item.x1 for item in clusters[-1]) + .5 * glyph_width:
            clusters[-1].append(word)
        else:
            clusters.append([word])
    return clusters


def _header_columns(words, expected=HEADERS):
    clusters = _header_clusters(words)
    if len(clusters) != len(expected):
        return None
    for index, (cluster, label) in enumerate(zip(clusters, expected)):
        value = squash("".join(line_text(row) for row in common.group_lines(cluster, tol=.25)))
        if expected == HEADERS and index == 0:
            valid = value in {"월별", "년월", "월"}
        else:
            valid = value == label
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


def _monthly_table(lines, *, allow_correction, metadata_bottom):
    checks = []
    corrections = []
    words = [word for row in lines for word in row]
    months = [word for word in words if word.y0 > metadata_bottom and MONTH.fullmatch(squash(word.text))]
    months.sort(key=lambda word: word.cy)
    first_y = min((word.y0 for word in months), default=float('-inf'))
    # Group labels belong to the table's header band. Notice prose below the
    # table may contain the same words and cannot compete with these labels.
    header_band = [word for word in words if metadata_bottom < word.y0 and word.cy < first_y]
    component_top = _component_top(header_band)
    group_words = [word for word in header_band if word.cy < component_top
                   and any(squash(word.text) in label for label in GROUPS)]
    groups = _header_columns(group_words, expected=GROUPS)
    group_ok = groups is not None
    checks.append(common.Validation("payment_group_headers", group_ok))
    group_bottom = max((word.y1 for group in (groups or []) for word in group), default=float('inf'))
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
    workplace_ok = middle is not None and not common.is_header_only_value(_text(middle[0]))
    checks.append(common.Validation("payment_information_cells", workplace_ok and bool(re.fullmatch(r"\d{11}", payer))))
    if middle is not None:
        put("사업장명칭", _text(middle[0]), middle[0])
    if re.fullmatch(r"\d{11}", payer):
        put("납부자번호", payer, middle[1])

    number_label = _unique_label(lines, "문서확인번호")
    number_words = []
    if number_label:
        label_ids = {id(word) for word in number_label}
        left = min(word.x0 for word in number_label)
        number_words = [word for row in lines if any(id(word) in label_ids for word in row)
                        for word in row if word.x0 >= left]
    number_text = normalize_format_text(squash(_text(number_words))).partition("문서확인번호")[2].lstrip(":：")
    number_ok = bool(number_label and DOCUMENT_NUMBER.fullmatch(number_text))
    checks.append(common.Validation("document_number_format", number_ok))
    if number_ok:
        put("문서확인번호", number_text, number_words)

    group_labels = [word for label in ("고지금액", "납부금액") for word in _unique_label(lines, label)]
    table_top = min((word.y0 for word in group_labels), default=float('inf'))
    period_rows = [row for row in lines if min(word.y0 for word in row) < table_top and
                   ("납부내역" in squash(line_text(row)) or re.search(
                       r"20\d{2}년\d{1,2}월[~～-]", normalize_format_text(squash(line_text(row)))))]
    periods = []
    if len(period_rows) == 1:
        row = period_rows[0]
        text = normalize_format_text(squash(line_text(row)))
        matches = list(PERIOD.finditer(text))
        residue = PERIOD.sub("", text)
        if len(matches) == 1 and re.fullmatch(r"(?:[（(]?단위[:：]?원[)）]?)?", residue):
            periods = [(matches[0], row)]
    period_ok = len(periods) == 1 and periods[0][0][1] == periods[0][0][3] and int(periods[0][0][2]) <= int(periods[0][0][4])
    checks.append(common.Validation("payment_query_period", period_ok))
    year = int(periods[0][0][1]) if period_ok else None
    if period_ok:
        match, row = periods[0]
        put("조회기간", [f"{year}-{int(match[2]):02}", f"{year}-{int(match[4]):02}"], row)

    allow_correction = all(page.source != PageSource.TEXT_LAYER and result.engine != "text_layer" for page, result in pages)
    metadata_bottom = max((word.y1 for row in period_rows for word in row), default=0)
    values, totals, corrections, table_checks = _monthly_table(
        lines, allow_correction=allow_correction, metadata_bottom=metadata_bottom)
    checks.extend(table_checks)
    bottom = _value_cells(lines, "납부총액", "용도구분")
    grand_total, total_ok = _money_cell(bottom[0], allow_correction=allow_correction,
                                       row="납부총액", column="total", corrections=corrections) if bottom else (None, False)
    purpose = squash(_text(bottom[1])) if bottom else ""
    purpose_ok = bool(purpose) and not common.is_header_only_value(purpose)
    checks.append(common.Validation("payment_purpose", purpose_ok))
    if purpose_ok:
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
    workplace_state, workplace_words = _workplace_evidence(lines, middle, period_rows, complete)
    put("사업장명칭_상태", workplace_state, workplace_words)
    if not complete:
        for extracted in fields.values():
            extracted.confidence = min(extracted.confidence, .4)
    warnings = [] if complete else ["납부확인서의 필수 정보 또는 월별 금액·합계를 완전히 확인하지 못했습니다."]
    return PaymentResult(DocType.NHIS_PAYMENT, .95, fields, checks, warnings,
                         form_kind="government_payment", structure_complete=complete)

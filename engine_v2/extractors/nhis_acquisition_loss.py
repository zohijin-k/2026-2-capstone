"""건강보험 자격득실확인서의 가입 이력·조회기간 판독기."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from statistics import median

from ..pipeline.layout import line_text, squash
from ..pipeline.ocr import OcrResult
from ..pipeline.preprocess import PageImage, PageSource
from ..schemas.models import DocType, ExtractedField
from . import nhis_common as common
from . import nhis_forms


@dataclass
class HistoryRow:
    category: str
    acquired: date | None
    lost: date | None
    employer: str
    words: list[common.Word]
    page: int
    number: int | None = None


@dataclass
class AcquisitionLossResult:
    detected_type: DocType
    type_confidence: float
    fields: dict[str, ExtractedField]
    history: list[HistoryRow]
    validations: list[common.Validation]
    warnings: list[str] = field(default_factory=list)
    diagnostics: dict[str, str] = field(default_factory=dict)
    form_kind: str = "government24"
    structure_complete: bool | None = None
    document_number: str | None = None


def _header_positions(pages):
    found: dict[str, list[float]] = {key: [] for key in ("category", "acquired", "lost", "employer")}
    aliases = {
        "category": ("가입자구분", "자격구분"),
        "acquired": ("자격취득일", "취득일"),
        "lost": ("자격상실일", "상실일"),
        "employer": ("사업장명칭", "사업장명", "사업장"),
    }
    for page, result in pages:
        lines = common.page_lines(page, result)
        for index, line in enumerate(lines):
            flat = squash(line_text(line))
            block = [line]
            if index + 1 < len(lines):
                candidate = lines[index : min(index + 3, len(lines))]
                if common.label_hits(candidate, tuple(alias for group in aliases.values() for alias in group)):
                    block = candidate
            if not any(common.label_hits(block, group) for group in aliases.values()):
                continue
            for key, terms in aliases.items():
                for _, words in common.label_hits(block, terms):
                    if words:
                        found[key].append((min(w.x0 for w in words) + max(w.x1 for w in words)) / 2)
    return {key: values[0] for key, values in found.items() if values}


def _query_period(pages):
    periods = []
    words = []
    for page, result in pages:
        for line in common.page_lines(page, result):
            text = line_text(line)
            if "조회" not in squash(text) and "대상기간" not in squash(text):
                continue
            dates = [value for value, _ in common.dates_in_line(line)]
            if len(dates) >= 2:
                periods.append((min(dates), max(dates)))
                words = line
    if not periods:
        return None, []
    return (min(pair[0] for pair in periods), max(pair[1] for pair in periods)), words


def _observed_identity_consensus(headers, key: str):
    """Require identity on page one; compare only values actually read on pages."""
    first = getattr(headers[0], key, None) if headers else None
    available = [getattr(header, key) for header in headers
                 if getattr(header, key, None) is not None]
    if first is None:
        return None, [], False
    words = getattr(headers[0], f"{key}_words") or []
    return first, words, all(value == first for value in available)


def _document_confirmation_numbers(pages):
    """Read document numbers only in the tightly scoped neighborhood of their label."""
    values: list[str] = []
    for page, result in pages:
        for line in common.page_lines(page, result):
            hits = common.label_hits([line], ("문서확인번호",))
            if not hits:
                continue
            label_words = hits[0][1]
            if not label_words:
                continue
            label_right = max(word.x1 for word in label_words)
            candidates = [word.text for word in line if word.x0 >= label_right]
            # Some OCR engines include the label and value in one token.
            for word in label_words:
                suffix = re.sub(r".*?문서확인번호", "", word.text)
                if suffix and suffix != word.text:
                    candidates.insert(0, suffix)
            pieces = []
            for text in candidates:
                if re.fullmatch(r"[\d\s\-‐‑‒–—―−﹘﹣－]+", text):
                    pieces.append(text)
                elif pieces:
                    break
            digits = re.sub(r"\D", "", "".join(pieces))
            if 12 <= len(digits) <= 20:
                values.append(digits)
            break
    return values


def _parse_history(pages):
    rows: list[HistoryRow] = []
    for page, result in pages:
        positions = _header_positions([(page, result)])
        header_y = None
        lines = common.page_lines(page, result)
        closing_index = next((index for index, line in enumerate(lines)
                              if "확인합니다" in squash(line_text(line)) or
                              ("국민건강보험공단" in squash(line_text(line)) and
                               "이사장" in squash(line_text(line)))), len(lines))
        for index, line in enumerate(lines):
            if index >= closing_index:
                continue
            flat = squash(line_text(line))
            header_block = [line]
            if index + 1 < len(lines):
                candidate = lines[index : min(index + 3, len(lines))]
                acquired_aliases = ("자격취득일", "취득일")
                lost_aliases = ("자격상실일", "상실일")
                if ((not common.label_hits([line], acquired_aliases) or
                     not common.label_hits([line], lost_aliases)) and
                    common.label_hits(candidate, acquired_aliases) and
                    common.label_hits(candidate, lost_aliases)):
                    header_block = candidate
            has_acquired = bool(common.label_hits(header_block, ("자격취득일", "취득일")))
            has_lost = bool(common.label_hits(header_block, ("자격상실일", "상실일")))
            if has_acquired and has_lost:
                header_y = max(word.cy for row in header_block for word in row)
                continue
            if header_y is None or line[0].cy <= header_y:
                continue
            dates = [(words, value) for value, words in common.dates_in_line(line)]
            if not dates:
                continue
            date_word_ids = {id(word) for date_words, _ in dates for word in date_words}
            # A date by itself can occur in the confirmation footer. Real table
            # rows carry at least one other cell token (category/workplace/etc.).
            if not any(id(word) not in date_word_ids for word in line):
                continue
            acquired = lost = None
            for date_words, value in dates:
                x = (min(word.x0 for word in date_words) + max(word.x1 for word in date_words)) / 2
                if "acquired" in positions and "lost" in positions:
                    if abs(x - positions["acquired"]) <= abs(x - positions["lost"]):
                        acquired = value
                    else:
                        lost = value
                elif acquired is None:
                    acquired = value
                else:
                    lost = value
            category = ""
            employer = ""
            for word in line:
                flat = squash(word.text)
                if "피부양자" in flat:
                    category = "직장피부양자"
                elif "직장" in flat:
                    category = "직장"
                elif "지역" in flat:
                    category = "지역"
                if positions.get("employer") is not None and word.x0 >= positions["employer"]:
                    # 사업장명은 추출 결과 객체에만 보관하며 결과 필드·경고·로그에 넣지 않는다.
                    employer += word.text
            rows.append(HistoryRow(category, acquired, lost, employer, line, page.page))
    return rows


def _form_kind(pages) -> str:
    text = squash(" ".join(result.text for _, result in pages))
    nhis = "확인청구자" in text or ("발급번호" in text and "자격득실확인내역" in text)
    government = "문서확인번호" in text
    if nhis:
        return "unknown" if government else "nhis"
    # Legacy labeled headers and table columns are an existing government24
    # structural signature, including synthetic/continuation fixtures.
    labels = {"성명", "가입자구분", "자격취득일", "자격상실일"}
    lines = [row for page, result in pages for row in common.page_lines(page, result)]
    positions = _header_positions(pages)
    ordered_dates = (all(key in positions for key in ("category", "acquired", "lost")) and
                     positions["category"] < positions["acquired"] < positions["lost"])
    table_order = ordered_dates and (positions.get("employer", -1) > positions["lost"])
    # Existing compact/wrapped synthetic headers can omit the employer column;
    # their inline labeled identity/date headers still identify that layout.
    inline_identity = any("성명" in squash(line_text(row)) and any(
        common.NAME_RE.fullmatch(squash(word.text)) and
        not common.is_header_only_value(word.text) for word in row) for row in lines)
    labeled_issue = any(any(label in squash(line_text(row)) for label in ("발급일", "발행일"))
                        for row in lines)
    if "employer" not in positions:
        table_order = ordered_dates and inline_identity and labeled_issue
    legacy = table_order and all(common.label_hits(lines, (label,)) for label in labels)
    identity_label = common.label_hits(lines, ("생년월일", "주민등록번호"))
    if government or (legacy and identity_label):
        return "government24"
    return "unknown"


def _nhis_document_number(pages):
    if not pages:
        return None
    page, result = pages[0]
    for line in common.page_lines(page, result):
        hits = common.label_hits([line], ("발급번호",))
        if not hits:
            continue
        label = hits[0][1]
        right = max(word.x1 for word in label)
        suffixes = [squash(word.text).partition("발급번호")[2] for word in label]
        suffixes += [word.text for word in line if word.x0 >= right]
        value = re.sub(r"[\s:：]", "", "".join(suffixes))
        return value if re.fullmatch(r"G\d{18}", value) else None
    return None


def _nhis_history(pages):
    """Split observed body columns; reserve date tokens before employer."""
    rows = []
    checks = []
    markers = []
    row_cells_read = True
    for page, result in pages:
        lines = common.page_lines(page, result)
        headings = [(index, row) for index, row in enumerate(lines)
                    if all(common.label_hits([row], (label,)) for label in
                           ("가입자구분", "사업장명칭", "자격취득일", "자격상실일"))]
        if len(headings) != 1:
            row_cells_read = False
            continue
        header_index, heading = headings[0]
        labels = ("No", "가입자구분", "사업장명칭", "자격취득일", "자격상실일")
        hits = [nhis_forms.label_hits([heading], (label,)) for label in labels]
        end = next((i for i in range(header_index + 1, len(lines))
                    if "확인합니다" in squash(line_text(lines[i])) or
                    "국민건강보험공단" in squash(line_text(lines[i]))), len(lines))
        body = lines[header_index + 1:end]
        ocr_page = page.source != PageSource.TEXT_LAYER
        header_height = median(word.y1 - word.y0 for word in heading)
        if ocr_page and all(len(hit) == 1 for hit in hits):
            # Regional rows may have no employer text. Tall low-confidence
            # overprints in that observed optional region are OCR artifacts.
            optional_left = max(word.x1 for word in hits[1][0][1])
            optional_right = min(word.x0 for word in hits[3][0][1])
            regional = [word for line in body for word in line
                        if squash(word.text) in {"직장가입자", "지역세대주", "지역세대원", "직장피부양자"}]
            only_regional = bool(regional) and all(squash(word.text).startswith("지역") for word in regional)
            body = common.group_lines([word for line in body for word in line
                if not (only_regional and optional_left <= word.x0 and word.x1 <= optional_right
                        and nhis_forms.table_noise(word, header_height)
                        and not re.search(r"[가-힣\d]", word.text))])
        marker_rows = [index for index, line in enumerate(body)
                       if "이하여백" in squash(line_text(line))]
        marker_index = marker_rows[0] if marker_rows else len(body)
        bounded_body = body[:marker_index + 1]
        # Reserve observed date occurrences before measuring whitespace. A long
        # employer token can overprint the beginning of a date cell; that token
        # must not erase a corridor supported by the other rows. Keep it intact
        # for the established employer continuation check below.
        geometry = []
        for row in bounded_body:
            dates = [w for w in row if common.DATE_RE.fullmatch(common.normalize_format_text(w.text))]
            geometry.append([w for w in row if w in dates or not any(
                w.x0 < d.x0 < w.x1 for d in dates)])
        boundaries = nhis_forms.table_columns(
            [hit[0][1] if len(hit) == 1 else [] for hit in hits], geometry, optional_columns=(2, 4),
            minimum_gap_ratio=.5 if ocr_page else 1.0)
        if boundaries is None:
            row_cells_read = False
            continue
        _, category_left, employer_left, date_left, lost_left, _ = boundaries
        categories = {"직장가입자", "지역세대주", "지역세대원", "직장피부양자"}
        anchor_y = [line[0].cy for line in body[:marker_index]
                    if any(squash(word.text) in categories for word in line)]
        pitches = [b - a for a, b in zip(anchor_y, anchor_y[1:]) if b > a]
        row_pitch = median(pitches) if pitches else 2 * header_height
        marker_seen = False
        marker_y = None
        for line in body:
            flat = squash(line_text(line))
            if "확인합니다" in flat or "국민건강보험공단" in flat:
                break
            marker_hits = nhis_forms.label_hits([line], ("이하여백",))
            marker_words = marker_hits[0][1] if len(marker_hits) == 1 else []
            if marker_words:
                marker_valid = (employer_left <= min(word.x0 for word in marker_words) and
                                max(word.x1 for word in marker_words) <= date_left and
                                re.sub(r"[^가-힣A-Za-z\d]", "", flat) == "이하여백")
                markers.append(marker_valid)
                marker_seen = True
                marker_y = max(word.cy for word in marker_words)
                continue
            if not line:
                continue
            if marker_seen:
                # Empty printed rows can contain distant watermark fragments.
                # Numbers/categories/dates and nearby text remain row evidence.
                punctuation = not re.search(r"[가-힣A-Za-z\d]", flat)
                distant_artifact = (ocr_page and marker_y is not None and
                    min(word.cy for word in line) > marker_y + 2.5 * row_pitch and
                    all(word.x0 >= employer_left for word in line) and
                    not any(squash(word.text) in categories for word in line) and
                    not common.dates_in_line(line) and
                    all(re.fullmatch(r"[가-힣]", squash(word.text)) or
                        not re.search(r"[가-힣A-Za-z\d]", word.text) or
                        (nhis_forms.table_noise(word, header_height) and
                         not re.search(r"[가-힣]", word.text)) for word in line))
                if punctuation or distant_artifact:
                    continue
                row_cells_read = False
                continue
            number_words = [word for word in line if word.x0 < category_left]
            number_text = squash(line_text(number_words))
            number = int(number_text) if re.fullmatch(r"\d+", number_text) else None
            category_words = [word for word in line if category_left <= word.x0 < employer_left]
            category = squash(line_text(category_words))
            # Date-only tokens are reserved first, even if the preceding long
            # workplace name crosses the printed date columns.
            date_words = [word for word in line if word.x0 >= date_left and
                          re.fullmatch(r"[\d\s년월일./\-]+", common.normalize_format_text(word.text))]
            acquired_words = [word for word in date_words if word.x0 < lost_left]
            lost_words = [word for word in date_words if word.x0 >= lost_left]

            def cell_date(words):
                text = common.normalize_format_text(line_text(words)).strip(" .")
                return (common.parse_date(text) if common.DATE_RE.fullmatch(text) or
                        common.COMPACT_DATE_RE.fullmatch(squash(text)) else None)

            acquired, lost = cell_date(acquired_words), cell_date(lost_words)
            date_ids = {id(word) for word in date_words}
            employer_words = []
            employer_complete = True
            for word in line:
                if word.x0 < employer_left or id(word) in date_ids:
                    continue
                # A tail outside the workplace column must join an observed
                # workplace token; isolated unreadable date cells stay uncertain.
                if word.x0 >= date_left and (not employer_words or
                        word.x0 - max(old.x1 for old in employer_words) > 2):
                    employer_complete = False
                employer_words.append(word)
            employer = line_text(employer_words)
            row_cells_read &= (number is not None and category in categories and acquired is not None
                               and (not lost_words or lost is not None) and employer_complete)
            rows.append(HistoryRow(category, acquired, lost, employer, line, page.page, number))
    checks.extend([
        common.Validation("nhis_history_cells_read", bool(rows) and row_cells_read),
        common.Validation("nhis_row_numbers_continuous", bool(rows) and
                          [row.number for row in rows] == list(range(1, len(rows) + 1))),
        common.Validation("nhis_current_loss_blank", bool(rows) and rows[0].lost is None),
        common.Validation("nhis_neighbor_dates_continuous", bool(rows) and all(
            lower.lost is not None and upper.acquired is not None and lower.lost <= upper.acquired
            for upper, lower in zip(rows, rows[1:]))),
        common.Validation("nhis_blank_marker", markers == [True]),
    ])
    return rows, checks


def _five_years_before(day: date, years: int = 5) -> date:
    try:
        return day.replace(year=day.year - years)
    except ValueError:
        return day.replace(year=day.year - years, day=28)


def history_covers_recent_years(
    issue_date: date,
    period: tuple[date, date] | None,
    rows: Iterable[tuple[date | None, date | None]],
    years: int = 5,
) -> bool:
    """Apply the NHIS coverage rule to dates from extractor rows or serialized JSON."""
    cutoff = _five_years_before(issue_date, years)
    if period:
        return period[0] <= cutoff and period[1] >= issue_date
    row_dates = tuple(rows)
    if any(acquired and acquired <= cutoff and (lost is None or lost >= issue_date)
           for acquired, lost in row_dates):
        return True
    return any(lost and lost < cutoff for _, lost in row_dates)


def extract(pages: list[tuple[PageImage, OcrResult]], today: date | None = None) -> AcquisitionLossResult:
    del today
    form_kind = _form_kind(pages)
    headers = common.page_headers(pages)
    nhis_checks = []
    document_number = None
    if form_kind == "nhis":
        headers = [nhis_forms.person_table_header(page, result, "확인청구자")
                   for page, result in pages]
        issue, words, valid_issue = nhis_forms.confirmation_issue_date(*pages[0]) if pages else (None, [], False)
        if headers:
            headers[0].issue, headers[0].issue_words = issue, words
        document_number = _nhis_document_number(pages)
        nhis_checks = [common.Validation("nhis_single_page", nhis_forms.single_page(pages)),
                       common.Validation("nhis_issue_location_unique", valid_issue),
                       common.Validation("nhis_document_number", document_number is not None)]
    page_map = {page.page: page for page, _ in pages}
    sources = common.sources_by_page(pages)
    validations: list[common.Validation] = []
    warnings: list[str] = []
    fields: dict[str, ExtractedField] = {}
    diagnostics: dict[str, str] = {}
    title = squash(" ".join(result.text for _, result in pages))
    detected = DocType.NHIS_ACQUISITION_LOSS if "자격득실확인서" in title else DocType.UNKNOWN
    type_confidence = 0.95 if detected == DocType.NHIS_ACQUISITION_LOSS else 0.2
    validations.append(common.Validation("document_type", detected == DocType.NHIS_ACQUISITION_LOSS))

    for key, label in (("name", "성명"), ("birth", "생년월일"), ("issue", "발급일")):
        if key in ("name", "birth"):
            value, words, same = _observed_identity_consensus(headers, key)
        else:
            value, words, same = common.consensus(headers, key)
        if key == "issue":
            same = bool(value) and all(h.issue in (None, value) for h in headers)
        validations.append(common.Validation(f"{label}_consistent", bool(value) and same))
        if value is not None:
            rendered = value.isoformat() if isinstance(value, date) else str(value)
            fields[label] = common.make_field(rendered, rendered, words, page_map,
                                              common.confidence([same], same), sources)
        else:
            warnings.append(f"{label}을 찾지 못해 담당자 확인이 필요합니다.")
            diagnostics[label] = f"라벨 '{label}' 또는 값을 찾지 못함"

    name, _, names_same = _observed_identity_consensus(headers, "name")
    validations.append(common.Validation("page_names_match", bool(name) and names_same))
    if not name or not names_same:
        warnings.append("쪽마다 성명이 같지 않거나 일부 쪽에서 찾지 못했습니다.")

    document_numbers = _document_confirmation_numbers(pages)
    if len(document_numbers) >= 2:
        validations.append(common.Validation("document_confirmation_number_consistent",
                                             len(set(document_numbers)) == 1))

    if form_kind == "nhis":
        rows, row_checks = _nhis_history(pages)
        nhis_checks.extend(row_checks)
        validations.extend(nhis_checks)
    else:
        rows = _parse_history(pages)
    if form_kind == "unknown":
        validations.append(common.Validation("form_recognized", False))
    period, period_words = _query_period(pages)
    history_data = {
        "period": [value.isoformat() for value in period] if period else None,
        "rows": [{"category": row.category, "acquired": row.acquired.isoformat() if row.acquired else None,
                  "lost": row.lost.isoformat() if row.lost else None} for row in rows],
    }
    history_text = json.dumps(history_data, ensure_ascii=False, separators=(",", ":"))
    fields["자격이력자료"] = common.make_field(history_text, history_text,
        [word for row in rows for word in row.words], page_map, 0.9, sources)
    dates_read = bool(rows) and all(row.acquired is not None for row in rows)
    order_ok = all(row.acquired <= row.lost for row in rows if row.acquired and row.lost)
    validations.extend((common.Validation("history_dates_read", dates_read),
                        common.Validation("acquisition_before_loss", order_ok)))
    if not dates_read:
        warnings.append("이력 표의 취득일을 모두 읽지 못했습니다.")
        diagnostics["history"] = "열 제목은 찾았으나 자격취득일이 있는 행을 못 찾음"
    if not order_ok:
        warnings.append("자격 취득일과 상실일의 순서가 맞지 않습니다.")
        diagnostics["취득일"] = "자격취득일이 자격상실일보다 늦음"

    categorized = [row for row in rows if row.category and row.acquired]
    if categorized:
        newest = max(categorized, key=lambda row: row.acquired)
        current_category = {"직장가입자": "직장", "지역세대주": "지역", "지역세대원": "지역"}.get(
            newest.category, newest.category)
        source_words = [word for word in newest.words if newest.category in squash(word.text)]
        fields["가입구분"] = common.make_field(current_category, current_category, source_words,
                                                page_map, common.confidence([dates_read]), sources)
    else:
        diagnostics["가입구분"] = "가입자구분 열 또는 해당 값을 못 찾음"

    issue = fields.get("발급일")
    issue_date = date.fromisoformat(issue.value) if issue else None
    period, period_words = _query_period(pages)
    spans_five_years = bool(issue_date and history_covers_recent_years(
        issue_date, period, ((row.acquired, row.lost) for row in rows)
    ))
    if issue_date:
        status = "최근 5년 포함" if spans_five_years else "최근 5년 미포함"
        fields["변동내역"] = common.make_field(status, status, period_words or
            next((row.words for row in rows if row.acquired), []), page_map,
            common.confidence([issue_date is not None, dates_read]), sources)
    else:
        diagnostics["변동내역"] = "발급일을 찾지 못해 최근 5년 범위를 계산하지 못함"
    validations.append(common.Validation("recent_five_years_covered", spans_five_years))

    active_jobs = [row for row in rows if row.category in {"직장", "직장가입자"} and row.acquired and row.lost is None]
    if active_jobs:
        newest = max(active_jobs, key=lambda row: row.acquired)
        value = newest.acquired.isoformat()
        fields["취득일"] = common.make_field(value, value,
        [word for word in newest.words if newest.acquired.isoformat() in word.text] or newest.words,
            page_map, common.confidence([dates_read, order_ok]), sources)
    else:
        diagnostics["취득일"] = "상실일이 없는 직장가입자 행을 못 찾음"

    structure_complete = None
    if form_kind != "government24":
        structure_complete = form_kind == "nhis" and all(
            check.passed for check in validations if check.name != "recent_five_years_covered")
        if not structure_complete:
            warnings.append("양식 또는 표 구조를 완전히 읽지 못해 담당자 확인이 필요합니다.")
            for extracted in fields.values():
                extracted.confidence = min(extracted.confidence, 0.4)
    return AcquisitionLossResult(detected, type_confidence, fields, rows, validations,
                                 list(dict.fromkeys(warnings)), diagnostics,
                                 form_kind, structure_complete, document_number)

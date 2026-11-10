"""건강보험 자격득실확인서의 가입 이력·조회기간 판독기."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from ..pipeline.layout import line_text, squash
from ..pipeline.ocr import OcrResult
from ..pipeline.preprocess import PageImage
from ..schemas.models import DocType, ExtractedField
from . import nhis_common as common


@dataclass
class HistoryRow:
    category: str
    acquired: date | None
    lost: date | None
    employer: str
    words: list[common.Word]
    page: int


@dataclass
class AcquisitionLossResult:
    detected_type: DocType
    type_confidence: float
    fields: dict[str, ExtractedField]
    history: list[HistoryRow]
    validations: list[common.Validation]
    warnings: list[str] = field(default_factory=list)
    diagnostics: dict[str, str] = field(default_factory=dict)


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


def _parse_history(pages):
    rows: list[HistoryRow] = []
    for page, result in pages:
        positions = _header_positions([(page, result)])
        header_y = None
        lines = common.page_lines(page, result)
        for index, line in enumerate(lines):
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
                if "직장" in flat:
                    category = "직장"
                elif "지역" in flat:
                    category = "지역"
                if positions.get("employer") is not None and word.x0 >= positions["employer"]:
                    # 사업장명은 추출 결과 객체에만 보관하며 결과 필드·경고·로그에 넣지 않는다.
                    employer += word.text
            rows.append(HistoryRow(category, acquired, lost, employer, line, page.page))
    return rows


def _five_years_before(day: date) -> date:
    try:
        return day.replace(year=day.year - 5)
    except ValueError:
        return day.replace(year=day.year - 5, day=28)


def extract(pages: list[tuple[PageImage, OcrResult]], today: date | None = None) -> AcquisitionLossResult:
    del today
    headers = common.page_headers(pages)
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

    name, _, names_same = common.consensus(headers, "name")
    validations.append(common.Validation("page_names_match", bool(name) and names_same))
    if not names_same:
        warnings.append("쪽마다 성명이 같지 않거나 일부 쪽에서 찾지 못했습니다.")

    rows = _parse_history(pages)
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
        current_category = max(categorized, key=lambda row: row.acquired).category
        source_words = [word for word in max(categorized, key=lambda row: row.acquired).words
                        if current_category in squash(word.text)]
        fields["가입구분"] = common.make_field(current_category, current_category, source_words,
                                                page_map, common.confidence([dates_read]), sources)
    else:
        diagnostics["가입구분"] = "가입자구분 열 또는 해당 값을 못 찾음"

    issue = fields.get("발급일")
    issue_date = date.fromisoformat(issue.value) if issue else None
    period, period_words = _query_period(pages)
    spans_five_years = False
    if issue_date:
        cutoff = _five_years_before(issue_date)
        if period:
            spans_five_years = period[0] <= cutoff and period[1] >= issue_date
        if not spans_five_years:
            spans_five_years = any(row.acquired and row.acquired <= cutoff and
                                    (row.lost is None or row.lost >= issue_date) for row in rows)
        status = "최근 5년 포함" if spans_five_years else "최근 5년 미포함"
        fields["변동내역"] = common.make_field(status, status, period_words or
            next((row.words for row in rows if row.acquired), []), page_map,
            common.confidence([issue_date is not None, dates_read]), sources)
    else:
        diagnostics["변동내역"] = "발급일을 찾지 못해 최근 5년 범위를 계산하지 못함"
    validations.append(common.Validation("recent_five_years_covered", spans_five_years))

    active_jobs = [row for row in rows if row.category == "직장" and row.acquired and row.lost is None]
    if active_jobs:
        newest = max(active_jobs, key=lambda row: row.acquired)
        value = newest.acquired.isoformat()
        fields["취득일"] = common.make_field(value, value,
        [word for word in newest.words if newest.acquired.isoformat() in word.text] or newest.words,
            page_map, common.confidence([dates_read, order_ok]), sources)
    else:
        diagnostics["취득일"] = "상실일이 없는 직장가입자 행을 못 찾음"

    return AcquisitionLossResult(detected, type_confidence, fields, rows, validations,
                                 list(dict.fromkeys(warnings)), diagnostics)

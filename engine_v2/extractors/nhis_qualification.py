"""Coordinate reader for single-page NHIS qualification notification forms."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date

from . import nhis_common as common, nhis_forms as forms
from ..pipeline.layout import line_text, squash
from ..pipeline.ocr import OcrResult
from ..pipeline.preprocess import PageImage
from ..schemas.models import DocType, ExtractedField

NOTICE_RE = re.compile(r"(?<!\d)\d-\d{4}-\d{8}-\d{6}(?!\d)")


@dataclass
class MemberRow:
    name: str | None
    birth: date | None
    acquired: date | None
    lost: date | None
    words: list[common.Word]
    complete: bool


@dataclass
class QualificationResult:
    detected_type: DocType
    type_confidence: float
    fields: dict[str, ExtractedField]
    validations: list[common.Validation]
    warnings: list[str] = field(default_factory=list)
    diagnostics: dict[str, str] = field(default_factory=dict)
    form_kind: str = "unknown"
    structure_complete: bool = False
    document_number: str | None = field(default=None, repr=False)
    request_date: date | None = None
    valid_until: date | None = None
    members: list[MemberRow] = field(default_factory=list, repr=False)


def is_notification(text: str) -> bool:
    """A positive notification cue selects this reader even when fields are damaged."""
    flat = squash(text)
    return ("자격확인(통보)서" in flat or
            ("통보번호" in flat and "자격확인내역" in flat))


def _labeled_value(lines, label: str):
    found = []
    for row in lines:
        hits = common.label_hits([row], (label,))
        if not hits:
            continue
        labels = hits[0][1]
        right = max(word.x1 for word in labels)
        words = [word for word in row if word.x0 >= right]
        text = squash(line_text(words)).lstrip(":：")
        # Preserve values merged into their label's token.
        if not text:
            flat = squash(line_text(row))
            text = flat.partition(label)[2].lstrip(":：")
        found.append((text, words or labels))
    return found


def _date_cell(words, *, optional=False):
    if not words:
        return None, optional
    text = common.normalize_format_text(line_text(words))
    raw = list(common.DATE_RE.finditer(text))
    found = common.dates_in_line(words)
    residue = re.sub(r"[\d\s년월일年月日./:\-‐‑‒–—―−﹘﹣－]", "", text)
    if len(raw) == 1 and len(found) == 1 and not residue:
        return found[0][0], True
    # An explicitly empty/dashed loss cell is admissible.
    return None, optional and bool(re.fullmatch(r"[\s\-－—–]+", text))


def _household(lines):
    headers = [i for i, row in enumerate(lines)
               if all(common.label_hits([row], (label,)) for label in
                      ("성명", "주민등록번호", "자격취득일", "자격상실일"))]
    if len(headers) != 1:
        return [], False, False
    index = headers[0]
    header = lines[index]
    labels = ("성명", "주민등록번호", "자격취득일", "자격상실일", "급여정지")
    header_hits = [forms.label_hits([header], (label,)) for label in labels]
    # Confirmation/issuer blocks delimit the table even if its marker is absent.
    end = next((i for i in range(index + 1, len(lines))
                if "확인합니다" in squash(line_text(lines[i]))), len(lines))
    body = lines[index + 1:end]
    bounds = forms.table_columns([hit[0][1] if len(hit) == 1 else [] for hit in header_hits], body)
    if bounds is None:
        return [], False, False
    markers = [i for i, row in enumerate(body) if "이하여백" in squash(line_text(row))]
    marker_ok = len(markers) == 1
    marker_index = markers[0] if markers else len(body)
    if marker_ok:
        marker_row = body[marker_index]
        marker_hits = common.label_hits([marker_row], ("이하여백",))
        marker_words = marker_hits[0][1] if len(marker_hits) == 1 else []
        marker_ok = (bool(marker_words) and squash(line_text(marker_words)) == "이하여백" and
                     bounds[2] <= min(word.x0 for word in marker_words) < bounds[3] and
                     all(any(word is marker for marker in marker_words) or
                         re.fullmatch(r"[\s\-－—–]+", word.text)
                         for word in marker_row) and
                     not any(re.search(r"[가-힣\d]", line_text(row)) for row in body[marker_index + 1:]))
    rows = []
    for row in body[:marker_index]:
        cells = forms.column_cells(row, bounds)
        if cells is None:
            return rows, False, False
        name = squash(line_text(cells[0]))
        name_ok = bool(common.NAME_RE.fullmatch(name) and not common.is_header_only_value(name))
        rrn = squash(common.normalize_format_text(line_text(cells[1])))
        match = common.MASKED_RRN_RE.fullmatch(rrn) or common.RRN_RE.fullmatch(rrn)
        birth = common.birth_from_rrn(match.group()) if match else None
        acquired, acquired_ok = _date_cell(cells[2])
        lost, lost_ok = _date_cell(cells[3], optional=True)
        ordered = acquired is not None and (lost is None or acquired <= lost)
        rows.append(MemberRow(name if name_ok else None, birth, acquired, lost, row,
                              bool(name_ok and birth and acquired_ok and lost_ok and ordered)))
    return rows, marker_ok, bool(rows) and all(row.complete for row in rows)


def extract(pages: list[tuple[PageImage, OcrResult]], today: date | None = None) -> QualificationResult:
    del today
    text = " ".join(result.text for _, result in pages)
    flat = squash(text)
    detected = DocType.NHIS_QUALIFICATION if "건강보험자격확인" in flat else DocType.UNKNOWN
    recognized = (is_notification(text) and "통보번호" in flat and "가입자" in flat and
                  "자격확인내역" in flat and "문서확인번호" not in flat)
    checks = [common.Validation("document_type", detected == DocType.NHIS_QUALIFICATION),
              common.Validation("form_recognized", recognized),
              common.Validation("nhis_single_page", forms.single_page(pages))]
    result = QualificationResult(detected, .95 if detected != DocType.UNKNOWN else .2, {}, checks,
                                 form_kind="nhis" if recognized else "unknown")
    if not pages:
        result.warnings.append("자격확인 통보서의 쪽을 확인하지 못했습니다.")
        return result
    page, ocr = pages[0]
    lines = common.page_lines(page, ocr)
    page_map = {p.page: p for p, _ in pages}
    sources = common.sources_by_page(pages)
    header = forms.person_table_header(page, ocr, "가입자")
    issue, issue_words, issue_ok = forms.confirmation_issue_date(page, ocr)
    checks.append(common.Validation("nhis_issue_location_unique", issue_ok))
    for label, value, words in (("성명", header.name, header.name_words),
                                ("생년월일", header.birth, header.birth_words),
                                ("발급일", issue, issue_words)):
        checks.append(common.Validation(f"{label}_consistent", value is not None))
        if value is not None:
            rendered = value.isoformat() if isinstance(value, date) else str(value)
            result.fields[label] = common.make_field(rendered, rendered, words, page_map, .95, sources)
        else:
            result.diagnostics[label] = f"{label} 값 셀을 읽지 못함"
    notices = _labeled_value(lines, "통보번호")
    numbers = [NOTICE_RE.fullmatch(value) for value, _ in notices]
    if len(numbers) == 1 and numbers[0]:
        result.document_number = numbers[0].group()
    checks.append(common.Validation("notice_number_read", result.document_number is not None))
    requests = _labeled_value(lines, "자격확인요청일")
    if len(requests) == 1 and common.DATE_RE.fullmatch(common.normalize_format_text(requests[0][0])):
        result.request_date = common.parse_date(requests[0][0])
        if result.request_date is not None:
            rendered = result.request_date.isoformat()
            result.fields["자격확인요청일"] = common.make_field(
                rendered, rendered, requests[0][1], page_map, .95, sources)
    # Validity is metadata, deliberately excluded from issue-date selection and rules.
    expiry = [common.parse_date(line_text(row)) for row in lines if "까지유효합니다" in squash(line_text(row))]
    if len(expiry) == 1:
        result.valid_until = expiry[0]
    members, marker_ok, rows_ok = _household(lines)
    result.members = members
    first_matches = bool(members and header.name and header.birth and
                         members[0].name == header.name and members[0].birth == header.birth)
    checks.extend((common.Validation("nhis_blank_marker", marker_ok),
                   common.Validation("household_rows_read", rows_ok),
                   common.Validation("subscriber_matches_first_member", first_matches)))
    result.structure_complete = all(check.passed for check in checks)
    # A partial list must not become an authoritative, reduced household count.
    if result.structure_complete:
        data = [{"성명": row.name, "생년월일": row.birth.isoformat(),
                 "자격취득일": row.acquired.isoformat(),
                 "자격상실일": row.lost.isoformat() if row.lost else ""} for row in members]
        raw = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        words = [word for row in members for word in row.words]
        result.fields["가구원목록"] = common.make_field(raw, raw, words, page_map, .95, sources)
        result.fields["가구원수"] = common.make_field(str(len(data)), str(len(data)), words, page_map, .95, sources)
    else:
        result.warnings.append("자격확인 통보서의 필수 정보 또는 표 구조를 완전히 확인하지 못했습니다.")
        for value in result.fields.values():
            value.confidence = min(value.confidence, .4)
    return result

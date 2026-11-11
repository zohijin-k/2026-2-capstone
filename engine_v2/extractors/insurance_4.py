"""정부24 4대 사회보험 가입자 가입내역 확인서 좌표 기반 판독기.

이 서식은 발급일 현재 내역만 표시한다. 마지막 열은 취득일과 괄호 안
신고접수일이며 상실일 또는 과거 이력으로 해석하지 않는다.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date

from ..pipeline.layout import Word, line_text, normalize, squash
from ..pipeline.ocr import OcrResult
from ..pipeline.preprocess import PageImage
from ..schemas.models import BBox, DocType, ExtractedField
from . import nhis_common as common
from .resident_abstract import kst_today

INSURANCE_NAMES = ("국민연금", "건강보험", "산재보험", "고용보험")
DOC_NO_RE = re.compile(r"(?<!\d)(\d{4}-\d{4}-\d{4}-\d{4,5})(?!\d)")
RRN_RE = re.compile(r"(?<!\d)(\d{6})\s*[-‐‑‒–—―]?\s*([0-8])(?=(?:\s*\d){6}(?!\d))")
ISSUE_NUMBER_RE = re.compile(r"(?<!\d)\d{14}(?!\d)")
NAME_RE = re.compile(r"^[가-힣]{2,6}$")
CATEGORY_NAMES = ("지역가입자", "직장가입자", "직장피부양자", "사업장가입자")


@dataclass
class InsuranceRow:
    insurance_type: str
    subscriber_name: str = ""
    subscriber_category: str = ""
    management_number: str = ""
    workplace_name: str = ""
    acquired: date | None = None
    received: date | None = None
    receipt_date_present: bool = False
    status: str = ""
    words: list[Word] = field(default_factory=list)
    acquired_words: list[Word] = field(default_factory=list)
    received_words: list[Word] = field(default_factory=list)
    bbox: BBox | None = None
    confidence: float = 0.0


@dataclass
class Insurance4Result:
    detected_type: DocType
    type_confidence: float
    fields: dict[str, ExtractedField]
    rows: list[InsuranceRow]
    validations: list[common.Validation]
    warnings: list[str] = field(default_factory=list)
    diagnostics: dict[str, str] = field(default_factory=dict)


def _birth_from_rrn(front: str, gender: str) -> date | None:
    century = {"1": 1900, "2": 1900, "5": 1900, "6": 1900,
               "3": 2000, "4": 2000, "7": 2000, "8": 2000,
               "9": 1800, "0": 1800}.get(gender)
    if century is None:
        return None
    try:
        return date(century + int(front[:2]), int(front[2:4]), int(front[4:6]))
    except ValueError:
        return None


def _erase_rrn(words: list[Word]) -> date | None:
    compact = "".join(word.text for word in words)
    match = RRN_RE.search(compact)
    if not match:
        return None
    birth = _birth_from_rrn(match.group(1), match.group(2))
    for word in words:
        if any(char.isdigit() for char in word.text) or re.fullmatch(r"[-‐‑‒–—―]+", word.text):
            word.text = ""
    return birth


def _dates(words: list[Word]) -> list[tuple[date, list[Word]]]:
    found = []
    for line in common.group_lines(words):
        found.extend(common.dates_in_line(line))
    unique: list[tuple[date, list[Word]]] = []
    for value, source in found:
        if not any(value == old for old, _ in unique):
            unique.append((value, source))
    return unique


def _field(value, words: list[Word], page_map, sources, confidence: float) -> ExtractedField:
    rendered = value.isoformat() if isinstance(value, date) else str(value)
    return common.make_field(value, rendered, words, page_map, confidence, sources)


def _looks_like_insurance4(pages: list[tuple[PageImage, OcrResult]]) -> bool:
    text = squash(" ".join(result.text for _, result in pages))
    title = "4대사회보험" in text and "가입자가입내역확인서" in text
    return title or "4대사회보험정보연계" in text


def _page_marker(lines: list[list[Word]]) -> bool:
    # OCR may return "1/1" as one token, spaced tokens, or three separate tokens.
    # Join each line and short neighboring-line windows after removing whitespace.
    for index, line in enumerate(lines):
        text = "".join(word.text for word in line)
        if re.search(r"(?<!\d)1\s*[/|／]\s*1(?!\d)", text):
            return True
        adjacent = "".join(word.text for row in lines[index:index + 3] for word in row)
        adjacent = re.sub(r"\s+", "", adjacent)
        if re.search(r"(?<!\d)1[/|／]1(?!\d)", adjacent):
            return True
    return False


def _row_starts(lines: list[list[Word]], header_y: float) -> list[tuple[int, str]]:
    starts = []
    for index, line in enumerate(lines):
        if line[0].cy <= header_y or line[0].cy > 51.5:
            continue
        flat = squash(line_text(line))
        for name in INSURANCE_NAMES:
            if name in flat:
                starts.append((index, name))
                break
    return starts


def _table_header_y(lines: list[list[Word]]) -> float | None:
    for i in range(len(lines)):
        block = lines[i:min(i + 3, len(lines))]
        flat = squash("".join(line_text(row) for row in block))
        if "자격취득일" in flat and "신고접수일" in flat and "사업장" in flat:
            return max(word.cy for row in block for word in row)
    return None


def _header_x(lines: list[list[Word]], token: str, default: float, table_y: float) -> float:
    for line in lines:
        if not table_y - 1 <= line[0].cy <= table_y + 4:
            continue
        for word in line:
            if token in squash(word.text):
                return word.x0
    return default


def _normalize_cell(value: str) -> str:
    value = value.strip(" \t:：()（）[]【】")
    return "" if value in {"", "-", "－", "—", "–", "해당없음"} else value


def _parse_row(insurance: str, lines: list[list[Word]], anchors: dict[str, float]) -> InsuranceRow:
    words = [word for line in lines for word in line if word.text]
    row = InsuranceRow(insurance_type=insurance, words=words)
    flat = squash("".join(word.text for word in words))
    if "미가입" in flat:
        row.status = "미가입"
        return row
    row.status = "가입"
    for word in words:
        text = squash(word.text.strip("()（）"))
        if text in CATEGORY_NAMES:
            row.subscriber_category = text
        elif anchors["name"] - 3 <= word.x0 < anchors["category"] and NAME_RE.fullmatch(text):
            row.subscriber_name = text
        elif anchors["management"] <= word.x0 < anchors["workplace"]:
            cell = _normalize_cell(word.text)
            if cell and re.search(r"\d", cell):
                row.management_number += re.sub(r"\D", "", cell)
        elif anchors["workplace"] <= word.x0 < anchors["date"]:
            cell = _normalize_cell(word.text)
            if cell and cell not in CATEGORY_NAMES and not re.search(r"\d{4}[.\-/]", cell):
                row.workplace_name += cell

    row_text = " ".join(line_text([word]) for word in words)
    row.receipt_date_present = bool(re.search(r"\(\s*[^)]*\d", row_text))
    date_hits = _dates(words)
    if date_hits:
        date_hits.sort(key=lambda item: (min(word.cy for word in item[1]), min(word.x0 for word in item[1])))
        row.acquired, row.acquired_words = date_hits[0]
        if len(date_hits) > 1:
            row.received, row.received_words = date_hits[1]
    row.subscriber_name = _normalize_cell(row.subscriber_name)
    row.management_number = _normalize_cell(row.management_number)
    row.workplace_name = _normalize_cell(row.workplace_name)
    return row


def extract(pages: list[tuple[PageImage, OcrResult]], today: date | None = None) -> Insurance4Result:
    today = today or kst_today()
    page_map = {page.page: page for page, _ in pages}
    sources = common.sources_by_page(pages)
    validations: list[common.Validation] = []
    warnings: list[str] = []
    diagnostics: dict[str, str] = {}
    fields: dict[str, ExtractedField] = {}
    headers = []
    page_lines: dict[int, list[list[Word]]] = {}
    all_words: list[Word] = []

    for page, result in pages:
        words = normalize(result.words, page.page, page.pixel_size or (1, 1))
        original_words = list(result.words)
        lines = common.group_lines(words)
        birth = None
        birth_words: list[Word] = []
        for line in lines:
            if RRN_RE.search("".join(word.text for word in line)):
                birth = _erase_rrn(line) or birth
                birth_words.extend(line)
        for source_word, normalized_word in zip(original_words, words):
            if not normalized_word.text and any(char.isdigit() for char in source_word.text):
                source_word.text = ""
        lines = common.group_lines(words)
        doc_no = issue_number = issue = name = None
        doc_words: list[Word] = []
        issue_number_words: list[Word] = []
        issue_words: list[Word] = []
        name_words: list[Word] = []
        for line in lines:
            flat = squash(line_text(line))
            if doc_no is None:
                match = DOC_NO_RE.search("".join(word.text for word in line))
                if match:
                    doc_no, doc_words = match.group(1), line
            if issue_number is None and "발급" in flat:
                candidates = [word for word in line if word.x0 < 55 and any(char.isdigit() for char in word.text)]
                joined_digits = "".join(re.findall(r"\d+", "".join(word.text for word in candidates)))
                match_number = ISSUE_NUMBER_RE.search(joined_digits)
                if match_number:
                    issue_number = match_number.group()
                    issue_number_words = candidates
            if issue is None and "발급일시" in flat:
                hit = _dates(line)
                if hit:
                    issue, issue_words = hit[0]
            if name is None and "성명" in flat:
                label = next((word for word in line if "성명" in squash(word.text)), None)
                if label:
                    candidate = next((word for word in line if word.x0 >= label.x1 and
                                      NAME_RE.fullmatch(word.text.strip("()（）"))), None)
                    if candidate:
                        name, name_words = candidate.text.strip("()（）"), [candidate]
            all_words.extend(word for word in line if word.text)
        headers.append({"doc_no": doc_no, "doc_no_words": doc_words,
                        "issue_number": issue_number, "issue_number_words": issue_number_words,
                        "issue": issue, "issue_words": issue_words, "name": name,
                        "name_words": name_words, "birth": birth, "birth_words": birth_words,
                        "lines": lines, "page": page})
        page_lines[page.page] = lines

    detected = DocType.INSURANCE_4 if _looks_like_insurance4(pages) else DocType.UNKNOWN
    type_confidence = 0.98 if detected == DocType.INSURANCE_4 else 0.2
    validations.append(common.Validation("document_type", detected == DocType.INSURANCE_4))
    validations.append(common.Validation("page_complete", len(pages) == 1 and bool(all_words)))
    validations.append(common.Validation("page_marker_1_of_1", len(headers) == 1 and _page_marker(headers[0]["lines"])))

    for key, label in (("doc_no", "문서확인번호"), ("issue_number", "발급번호"),
                       ("issue", "발급일"), ("name", "성명"), ("birth", "생년월일")):
        values = [(h[key], h[f"{key}_words"]) for h in headers if h[key] is not None]
        value = values[0][0] if values else None
        consistent = bool(values) and len(values) == len(headers) and all(v == value for v, _ in values)
        if value is not None:
            fields[label] = _field(value, values[0][1], page_map, sources,
                                   common.confidence([consistent], consistent))
        else:
            diagnostics[label] = f"라벨 '{label}' 또는 값을 찾지 못함"
            warnings.append(f"{label}을 찾지 못해 담당자 확인이 필요합니다.")
        validations.append(common.Validation(f"{label}_consistent", value is not None and consistent))

    doc_value = fields.get("문서확인번호")
    validations.append(common.Validation("document_number_format", bool(doc_value and DOC_NO_RE.fullmatch(str(doc_value.value)))))
    issue_field = fields.get("발급일")
    issue_date = date.fromisoformat(str(issue_field.value)) if issue_field else None
    validations.append(common.Validation("issue_not_future", issue_date is not None and issue_date <= today))
    names = [h["name"] for h in headers]
    validations.append(common.Validation("name_consistent", bool(names) and len(names) == len(headers) and len(set(names)) == 1))

    all_rows: list[InsuranceRow] = []
    for page, _ in pages:
        lines = page_lines[page.page]
        header_y = _table_header_y(lines)
        starts = _row_starts(lines, header_y if header_y is not None else 33.5)
        anchors = {
            "name": _header_x(lines, "성명", 22.0, header_y or 33.5),
            "category": _header_x(lines, "가입자종별", 33.5, header_y or 33.5),
            "management": _header_x(lines, "관리번호", 47.5, header_y or 33.5),
            "workplace": _header_x(lines, "사업장명칭", 64.0, header_y or 33.5),
            "date": _header_x(lines, "자격취득일", 81.5, header_y or 33.5),
        }
        for i, (start, insurance) in enumerate(starts):
            end = starts[i + 1][0] if i + 1 < len(starts) else len(lines)
            chunk = [line for line in lines[start:end] if line[0].cy <= 51.5]
            all_rows.append(_parse_row(insurance, chunk, anchors))

    expected_order = list(INSURANCE_NAMES)
    actual_order = [row.insurance_type for row in all_rows]
    validations.append(common.Validation("four_rows_in_order", actual_order == expected_order))
    validations.append(common.Validation("insurance_names_recognized", len(set(actual_order)) == 4))
    nonempty = [row for row in all_rows if row.status != "미가입"]
    dates_read = all(row.acquired is not None and
                     (not row.receipt_date_present or row.received is not None)
                     for row in nonempty)
    validations.append(common.Validation("date_formats", dates_read))
    dates_before_issue = issue_date is not None and all(
        value <= issue_date for row in all_rows for value in (row.acquired, row.received) if value
    )
    validations.append(common.Validation("dates_not_after_issue", dates_before_issue))
    names_match = bool(headers and headers[0]["name"]) and all(
        row.status == "미가입" or row.subscriber_name == headers[0]["name"]
        for row in all_rows
    )
    validations.append(common.Validation("row_names_match_header", names_match))
    if not dates_read:
        warnings.append("가입 행의 자격취득일을 모두 읽지 못했습니다.")
    if not dates_before_issue:
        warnings.append("발급일보다 뒤인 자격취득일 또는 신고접수일이 있거나 발급일을 확인하지 못했습니다.")
    if not names_match:
        warnings.append("가입 행의 성명이 머리 표 성명과 일치하지 않습니다.")
    if any(row.acquired and row.received and row.received < row.acquired for row in all_rows):
        warnings.append("신고접수일이 자격취득일보다 빠른 행이 있습니다.")

    table_words = [word for row in all_rows for word in row.words]
    rows_data = []
    for row in all_rows:
        row.bbox = common.bbox(row.words, page_map)
        row.confidence = round(sum(word.conf for word in row.words) / len(row.words), 2) if row.words else 0.0
        rows_data.append({
            "보험": row.insurance_type, "성명": row.subscriber_name,
            "가입자종별": row.subscriber_category, "사업장관리번호": row.management_number,
            "사업장명칭": row.workplace_name,
            "자격취득일": row.acquired.isoformat() if row.acquired else "",
            "신고접수일": row.received.isoformat() if row.received else "",
            "상태": row.status, "bbox": row.bbox.model_dump(mode="json") if row.bbox else None,
            "신뢰도": row.confidence,
        })
    if all_rows:
        rows_json = json.dumps(rows_data, ensure_ascii=False, separators=(",", ":"))
        fields["가입내역"] = _field(rows_json, table_words, page_map, sources,
                                     common.confidence([actual_order == expected_order, dates_read, names_match]))
        insured = {name: any(row.insurance_type == name and row.status == "가입" for row in all_rows)
                   for name in INSURANCE_NAMES}
        categories = {name: next((row.subscriber_category for row in all_rows
                                  if row.insurance_type == name and row.status == "가입"), "")
                      for name in INSURANCE_NAMES}
        work_rows = [row for row in all_rows if row.status == "가입" and (
            (row.insurance_type == "국민연금" and row.subscriber_category == "사업장가입자") or
            (row.insurance_type == "건강보험" and row.subscriber_category == "직장가입자") or
            row.insurance_type in {"고용보험", "산재보험"})]
        work_dates = sorted(row.acquired for row in work_rows if row.acquired)
        summaries = {
            "보험별가입여부": insured,
            "보험별가입자종별": categories,
            "근로관련가입여부": bool(work_rows),
            "근로관련최초취득일": work_dates[0].isoformat() if work_dates else "",
            "근로관련최근취득일": work_dates[-1].isoformat() if work_dates else "",
            "사업장명칭목록": list(dict.fromkeys(
                row.workplace_name for row in all_rows if row.status == "가입" and row.workplace_name)),
        }
        for key, value in summaries.items():
            raw = json.dumps(value, ensure_ascii=False, separators=(",", ":")) if isinstance(value, (dict, list)) else str(value)
            fields[key] = _field(raw, table_words, page_map, sources, common.confidence([bool(all_rows)]))
    else:
        diagnostics["가입내역"] = "표 제목을 찾았으나 보험별 행을 찾지 못함"
        warnings.append("가입 내역 표를 찾지 못해 담당자 확인이 필요합니다.")

    return Insurance4Result(detected, type_confidence, fields, all_rows, validations,
                            list(dict.fromkeys(warnings)), diagnostics)

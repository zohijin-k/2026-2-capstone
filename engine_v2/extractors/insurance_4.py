"""정부24 4대 사회보험 가입내역 확인서의 좌표 기반 판독기.

표의 보험별 한 행은 OCR 줄바꿈을 포함할 수 있어, 보험 종류를 행 시작으로 삼아
다음 보험 행 전까지를 한 묶음으로 읽는다. 주민등록번호는 생년월일 계산 직후
OCR 단어에서 제거하며, 정규화된 결과에는 남기지 않는다.
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


INSURANCE_NAMES = ("국민연금", "건강보험", "고용보험", "산재보험")
DOC_NO_RE = re.compile(r"(?<!\d)(\d{4}-\d{4}-\d{4}-\d{4,5})(?!\d)")
RRN_RE = re.compile(r"(?<!\d)(\d{6})\s*[-‐‑‒–—―]?\s*([0-8])(?=(?:\s*\d){6}(?!\d))")
DATE_TOKEN_RE = re.compile(r"(?<!\d)\d{4}\s*[.\-/년]\s*\d{1,2}\s*[.\-/월]\s*\d{1,2}\s*일?(?!\d)|(?<!\d)\d{8}(?!\d)")
ISSUE_NUMBER_RE = re.compile(r"(?<!\d)\d{14}(?!\d)")
NAME_RE = re.compile(r"^[가-힣]{2,6}$")


@dataclass
class InsuranceRow:
    insurance_type: str
    subscriber_name: str = ""
    workplace_name: str = ""
    management_number: str = ""
    subscriber_category: str = ""
    status: str = ""
    acquired: date | None = None
    lost: date | None = None
    other_columns: dict[str, str] = field(default_factory=dict)
    words: list[Word] = field(default_factory=list)
    acquired_words: list[Word] = field(default_factory=list)
    lost_words: list[Word] = field(default_factory=list)
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
    """Keep only the first six digits and gender digit long enough to derive birth date."""
    compact = "".join(word.text for word in words)
    match = RRN_RE.search(compact)
    if not match:
        return None
    birth = _birth_from_rrn(match.group(1), match.group(2))
    # Erase every number fragment from this identity line before retaining any field.
    for word in words:
        if any(char.isdigit() for char in word.text) or re.fullmatch(r"[-‐‑‒–—―]+", word.text):
            word.text = ""
    return birth


def _date_matches(words: list[Word]) -> list[tuple[date, list[Word]]]:
    values: list[tuple[date, list[Word]]] = []
    for line in common.group_lines(words):
        values.extend(common.dates_in_line(line))
    result: list[tuple[date, list[Word]]] = []
    for value, source_words in values:
        if not any(existing == value for existing, _ in result):
            result.append((value, source_words))
    return result


def _field(value, raw: str, words: list[Word], page_map, sources, confidence: float) -> ExtractedField:
    return common.make_field(value, raw, words, page_map, confidence, sources)


def _row_starts(lines: list[list[Word]], header_y: float) -> list[tuple[int, str]]:
    starts = []
    for index, line in enumerate(lines):
        if not header_y < line[0].cy < 51.5:
            continue
        flat = squash(line_text(line))
        for name in INSURANCE_NAMES:
            if squash(name) in flat:
                starts.append((index, name))
                break
    return starts


def _table_header_y(lines: list[list[Word]]) -> float | None:
    for index in range(len(lines)):
        candidate = lines[index:min(index + 3, len(lines))]
        flat = squash("".join(line_text(item) for item in candidate))
        if "취득일" in flat and ("사업장" in flat or "가입자" in flat or "구분" in flat):
            return max(word.cy for row in candidate for word in row)
    return None


def _parse_row(insurance_type: str, lines: list[list[Word]]) -> InsuranceRow:
    words = [word for line in lines for word in line if word.text]
    row = InsuranceRow(insurance_type=insurance_type, words=words)
    row_text = squash("".join(word.text for word in words))
    if "미가입" in row_text or "해당없음" in row_text:
        row.status = "미가입" if "미가입" in row_text else "해당없음"
    for word in words:
        text = squash(word.text)
        if "직장가입자" in text:
            row.subscriber_category = "직장"
        elif "지역가입자" in text:
            row.subscriber_category = "지역"
        elif 20 <= word.x0 < 32 and NAME_RE.fullmatch(word.text.strip("()（）")):
            row.subscriber_name = word.text.strip("()（）")

    dates = _date_matches(words)
    if dates:
        ordered = sorted(dates, key=lambda item: min(word.x0 for word in item[1]))
        row.acquired, row.acquired_words = ordered[0]
        if len(ordered) > 1:
            row.lost, row.lost_words = ordered[1]

    # Second-level table headings put workplace number/name before the rightmost date column.
    for word in words:
        if 42 <= word.x0 < 58 and re.search(r"\d{5,}", word.text):
            row.management_number += word.text
        if 58 <= word.x0 < 80 and not DATE_TOKEN_RE.search(word.text):
            text = word.text.strip("()（）:：")
            if text and text not in INSURANCE_NAMES and not any(k in text for k in (
                "직장가입", "지역가입", "미가입", "해당없음", "사업장", "명칭", "관리번호", "구분",
            )):
                row.workplace_name += text
    if row.workplace_name:
        row.other_columns["사업장명칭"] = row.workplace_name
    if row.management_number:
        row.other_columns["사업장관리번호"] = row.management_number
    if row.subscriber_category:
        row.other_columns["가입자구분"] = row.subscriber_category
    if row.status:
        row.other_columns["가입상태"] = row.status
    return row


def _looks_like_insurance4(pages: list[tuple[PageImage, OcrResult]]) -> bool:
    text = squash(" ".join(result.text for _, result in pages))
    title = ("4대사회보험" in text or "4대보험" in text or "사대보험" in text or
             ("가입자가입내역확인서" in text and "사회보험" in text))
    return title or sum(name in text for name in INSURANCE_NAMES) >= 3


def extract(pages: list[tuple[PageImage, OcrResult]], today: date | None = None) -> Insurance4Result:
    today = today or kst_today()
    page_map = {page.page: page for page, _ in pages}
    sources = common.sources_by_page(pages)
    validations: list[common.Validation] = []
    warnings: list[str] = []
    diagnostics: dict[str, str] = {}
    fields: dict[str, ExtractedField] = {}

    headers: list[dict] = []
    all_words: list[Word] = []
    lines_by_page: dict[int, list[list[Word]]] = {}
    for page, result in pages:
        words = normalize(result.words, page.page, page.pixel_size or (1, 1))
        source_words = list(result.words)
        lines = common.group_lines(words)
        birth = None
        rrn_words = []
        for line in lines:
            if RRN_RE.search("".join(word.text for word in line)):
                birth = _erase_rrn(line) or birth
                rrn_words.extend(line)
        # Mirror the privacy erasure onto the source OCR object when a single OCR word held it.
        for source_word, normalized_word in zip(source_words, words):
            if not normalized_word.text and any(char.isdigit() for char in source_word.text):
                source_word.text = ""
        lines = common.group_lines(words)

        name = None
        name_words: list[Word] = []
        issue = None
        issue_words: list[Word] = []
        doc_no = None
        doc_no_words: list[Word] = []
        issue_number = None
        issue_number_words: list[Word] = []
        for line in lines:
            text = line_text(line)
            flat = squash(text)
            if doc_no is None:
                match = DOC_NO_RE.search("".join(word.text for word in line))
                if match:
                    doc_no, doc_no_words = match.group(1), line
            if issue_number is None and line[0].cy < 27 and ("발급" in flat or "발급번호" in flat):
                found = next((word for word in line
                              if word.x0 < 55 and ISSUE_NUMBER_RE.search(word.text)), None)
                if found:
                    issue_number = ISSUE_NUMBER_RE.search(found.text).group()
                    issue_number_words = [found]
            if issue is None and "발급일시" in flat:
                found = _date_matches(line)
                if found:
                    issue, issue_words = found[0]
            if name is None and "성명" in flat:
                label = next((word for word in line if "성명" in squash(word.text)), None)
                if label:
                    candidate = next((word for word in line if word.x0 >= label.x1 and
                                      NAME_RE.fullmatch(word.text.strip("()（）"))), None)
                    if candidate:
                        name, name_words = candidate.text.strip("()（）"), [candidate]
            all_words.extend(word for word in line if word.text)
        headers.append({"name": name, "name_words": name_words, "birth": birth,
                        "birth_words": rrn_words, "issue": issue, "issue_words": issue_words,
                        "doc_no": doc_no, "doc_no_words": doc_no_words,
                        "issue_number": issue_number, "issue_number_words": issue_number_words,
                        "lines": lines, "page": page})
        lines_by_page[page.page] = lines

    detected = DocType.INSURANCE_4 if _looks_like_insurance4(pages) else DocType.UNKNOWN
    type_confidence = 0.97 if detected == DocType.INSURANCE_4 else 0.2
    validations.append(common.Validation("document_type", detected == DocType.INSURANCE_4))
    validations.append(common.Validation("page_complete", len(pages) == 1 and bool(all_words)))

    for key, label in (("doc_no", "문서확인번호"), ("issue_number", "발급번호"),
                       ("issue", "발급일"), ("name", "성명"), ("birth", "생년월일")):
        values = [(header[key], header[f"{key}_words"]) for header in headers if header[key] is not None]
        value = values[0][0] if values else None
        consistent = bool(values) and len(values) == len(headers) and all(v == value for v, _ in values)
        if value is not None:
            rendered = value.isoformat() if isinstance(value, date) else str(value)
            fields[label] = _field(rendered, rendered, values[0][1], page_map, sources,
                                   common.confidence([consistent], consistent))
        else:
            diagnostics[label] = f"라벨 '{label}' 또는 값을 찾지 못함"
            warnings.append(f"{label}을 찾지 못해 담당자 확인이 필요합니다.")
        validations.append(common.Validation(f"{label}_consistent", value is not None and consistent))

    doc_number = fields.get("문서확인번호")
    validations.append(common.Validation("document_number_format",
        bool(doc_number and DOC_NO_RE.fullmatch(str(doc_number.value)))))
    issue_field = fields.get("발급일")
    issue_date = date.fromisoformat(str(issue_field.value)) if issue_field else None
    validations.append(common.Validation("issue_not_future", issue_date is not None and issue_date <= today))
    names = [header["name"] for header in headers]
    validations.append(common.Validation("name_consistent", bool(names) and len(names) == len(headers)
                                          and len(set(names)) == 1))

    all_rows: list[InsuranceRow] = []
    for page, _ in pages:
        lines = lines_by_page[page.page]
        header_y = _table_header_y(lines)
        starts = _row_starts(lines, header_y if header_y is not None else 30.0)
        for index, (line_index, name) in enumerate(starts):
            end = starts[index + 1][0] if index + 1 < len(starts) else len(lines)
            chunk = [line for line in lines[line_index:end] if line[0].cy < 51.5]
            all_rows.append(_parse_row(name, chunk))

    found_insurers = {row.insurance_type for row in all_rows}
    validations.append(common.Validation("insurance_names_recognized", len(found_insurers) == 4,
                                         f"{len(found_insurers)} insurer labels recognized"))
    date_parse_ok = all(row.acquired is not None for row in all_rows
                        if row.status not in {"미가입", "해당없음"})
    validations.append(common.Validation("date_formats", date_parse_ok))
    order_ok = all(row.acquired is None or row.lost is None or row.lost >= row.acquired for row in all_rows)
    validations.append(common.Validation("loss_after_acquisition", order_ok))
    dates_before_issue = bool(issue_date) and all(
        value <= issue_date for row in all_rows for value in (row.acquired, row.lost) if value is not None
    )
    validations.append(common.Validation("dates_not_after_issue", dates_before_issue))
    if not order_ok:
        warnings.append("자격상실일이 자격취득일보다 빠른 행이 있습니다.")
    if not date_parse_ok:
        warnings.append("가입 내역의 날짜를 모두 읽지 못했습니다.")
    if not dates_before_issue:
        warnings.append("발급일보다 뒤인 자격 날짜가 있거나 발급일을 확인하지 못했습니다.")

    table_words = [word for row in all_rows for word in row.words]
    rows_data = []
    for row in all_rows:
        row.bbox = common.bbox(row.words, page_map)
        row.confidence = round(sum(word.conf for word in row.words) / len(row.words), 2) if row.words else 0.0
        rows_data.append({
            "보험종류": row.insurance_type, "가입자성명": row.subscriber_name,
            "사업장명칭": row.workplace_name,
            "사업장관리번호": row.management_number, "가입자구분": row.subscriber_category,
            "가입상태": row.status, "취득일": row.acquired.isoformat() if row.acquired else "",
            "상실일": row.lost.isoformat() if row.lost else "", "그밖의열": row.other_columns,
            "bbox": row.bbox.model_dump(mode="json") if row.bbox else None,
            "신뢰도": row.confidence,
        })
    if all_rows:
        rows_json = json.dumps(rows_data, ensure_ascii=False, separators=(",", ":"))
        fields["가입내역"] = _field(rows_json, rows_json, table_words, page_map, sources,
                                     common.confidence([len(found_insurers) >= 1, date_parse_ok]))
        latest: dict[str, str] = {}
        active: dict[str, bool] = {}
        for insurance in INSURANCE_NAMES:
            rows = [row for row in all_rows if row.insurance_type == insurance]
            acquired_rows = [row for row in rows if row.acquired]
            latest[insurance] = max((row.acquired for row in acquired_rows), default=None).isoformat() if acquired_rows else ""
            active[insurance] = any(row.status not in {"미가입", "해당없음"} and row.lost is None
                                    and row.acquired is not None for row in rows)
        latest_json = json.dumps(latest, ensure_ascii=False, separators=(",", ":"))
        active_json = json.dumps(active, ensure_ascii=False, separators=(",", ":"))
        fields["최근취득일"] = _field(latest_json, latest_json, table_words, page_map, sources,
                                      common.confidence([date_parse_ok]))
        fields["가입중"] = _field(active_json, active_json, table_words, page_map, sources,
                                   common.confidence([len(found_insurers) >= 1]))
    else:
        diagnostics["가입내역"] = "열 제목을 찾았으나 보험별 가입 행을 찾지 못함"
        warnings.append("가입 내역 표를 찾지 못해 담당자 확인이 필요합니다.")

    return Insurance4Result(detected, type_confidence, fields, all_rows, validations,
                            list(dict.fromkeys(warnings)), diagnostics)

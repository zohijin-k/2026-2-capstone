"""정부24·4대사회보험 포털 가입내역 확인서 좌표 기반 판독기.

이 서식은 발급일 현재 내역만 표시한다. 마지막 열은 취득일과 괄호 안
신고접수일이며 상실일 또는 과거 이력으로 해석하지 않는다.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace
from datetime import date

from ..pipeline.layout import Word, line_text, normalize, squash
from ..pipeline.ocr import OcrResult
from ..pipeline.preprocess import PageImage
from ..schemas.models import BBox, DocType, ExtractedField
from . import nhis_common as common, nhis_forms as forms
from .resident_abstract import kst_today
from .format_text import normalize_format_text
from .insurance_issue import select_issue_date

INSURANCE_NAMES = ("국민연금", "건강보험", "산재보험", "고용보험")
DOC_NO_RE = re.compile(r"(?<!\d)(\d{4}-\d{4}-\d{4}-\d{4,5})(?!\d)")
RRN_RE = re.compile(r"(?<!\d)(\d{6})\s*-?\s*([0-8])(?=(?:\s*\d){6}(?!\d))")
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
    date_column_words: list[Word] = field(default_factory=list)
    bbox: BBox | None = None
    confidence: float = 0.0
    date_cells_complete: bool = True
    cells_complete: bool = True


@dataclass
class Insurance4Result:
    detected_type: DocType
    type_confidence: float
    fields: dict[str, ExtractedField]
    rows: list[InsuranceRow]
    validations: list[common.Validation]
    warnings: list[str] = field(default_factory=list)
    diagnostics: dict[str, str] = field(default_factory=dict)
    form_kind: str = "government24"
    structure_complete: bool | None = None


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
    compact = normalize_format_text("".join(word.text for word in words))
    match = RRN_RE.search(compact)
    if not match:
        return None
    birth = _birth_from_rrn(match.group(1), match.group(2))
    for word in words:
        if any(char.isdigit() for char in word.text) or re.fullmatch(r"-+", normalize_format_text(word.text)):
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


def _identity_label_text(text: str) -> str:
    return re.sub(r"[()（）]", "", squash(normalize_format_text(text)))


def _form_kind(pages) -> str:
    lines = [row for page, result in pages for row in common.page_lines(page, result)]
    if any(common.label_hits([row], ("문서확인번호",)) for row in lines):
        return "government24"
    grid_rows = _portal_grid_rows(lines)
    identity_rows = _portal_identity_rows(lines)
    if len(grid_rows) != 1 or not identity_rows:
        return "unknown"
    grid_y = grid_rows[0][0].cy
    output = any(row[0].cy < grid_y and "출력일시" in squash(line_text(row)) for row in lines)
    purpose = any(row[0].cy < grid_y and any(squash(w.text) == "확인용" for w in row) for row in lines)
    return "portal" if _looks_like_insurance4(pages) and output and purpose else "unknown"


def _portal_grid_rows(lines):
    return [row for row in lines if forms.label_hits([row], ("발급번호",)) and
            forms.label_hits([row], ("발급일시",))]


def _portal_identity_rows(lines):
    return [row for row in lines if "등록번호" in _identity_label_text(line_text(row)) and
            forms.label_hits([row], ("성명",))]


def _portal_identity(words):
    """Read only the right cells of the header's resident-number/name row."""
    rows = _portal_identity_rows(common.group_lines(words))
    candidates = []
    for row in rows:
        normalized = [replace(word, text=_identity_label_text(word.text)) for word in row]
        rrn_hits = common.label_hits([normalized], ("주민외국인등록번호", "주민등록번호"))
        name_hits = common.label_hits([row], ("성명",))
        if not rrn_hits or not name_hits:
            continue
        rrn_label, name_label = rrn_hits[0][1], name_hits[0][1]
        rrn_right = max(word.x1 for word in rrn_label)
        name_left = min(word.x0 for word in name_label)
        name_right = max(word.x1 for word in name_label)
        rrn_cell = [word for word in row if rrn_right <= word.x0 < name_left]
        name_cell = [word for word in row if word.x0 >= name_right]
        rrn_text = squash(normalize_format_text(line_text(rrn_cell))).strip(":：")
        name_text = squash(line_text(name_cell)).strip(":：()（）")
        birth = (common.birth_from_rrn(rrn_text) if common.MASKED_RRN_RE.fullmatch(rrn_text) or
                 common.RRN_RE.fullmatch(rrn_text) else None)
        name = (name_text if NAME_RE.fullmatch(name_text) and
                not common.is_header_only_value(name_text) else None)
        candidates.append((name, name_cell, birth, rrn_cell))
    if len(candidates) != 1:
        # Ambiguous identity still carries all RRN-cell source words through
        # the erasure step; uncertainty must not leave full numbers behind.
        return None, [], None, [word for candidate in candidates for word in candidate[3]]
    return candidates[0]


def _portal_issue_number(lines):
    candidates = []
    for row in _portal_grid_rows(lines):
        hits = forms.label_hits([row], ("발급번호",))
        end_hits = common.label_hits([row], ("발급일시",))
        if not hits or not end_hits:
            continue
        right = max(word.x1 for word in hits[0][1])
        end = min(word.x0 for word in end_hits[0][1])
        words = [word for word in row if right <= word.x0 < end]
        value = squash(line_text(words)).strip(":：")
        candidates.append((value if ISSUE_NUMBER_RE.fullmatch(value) else None, words))
    return candidates[0] if len(candidates) == 1 else (None, [])


def _portal_table_layout(lines):
    categories = forms.label_hits(lines, ("가입자종별",))
    if len(categories) != 1:
        return None
    category_words = categories[0][1]
    cy = sum(w.cy for w in category_words) / len(category_words)
    height = max(w.y1 - w.y0 for w in category_words)
    header = [row for row in lines if abs(row[0].cy - cy) <= 2 * height and
              "가입내역" not in squash(line_text(row))]
    headers, sources = [], []
    for label in ("내역", "성명", "가입자종별", "사업장관리번호", "사업장명칭", "자격취득일", "신고접수일"):
        # The management label is stacked vertically; legacy label_hits already
        # requires overlapping x intervals for that two-word case.
        hits = common.label_hits(header, (label,))
        if len(hits) != 1:
            return None
        headers.append(hits[0][1])
        sources.extend(hits[0][1])
    header_bottom = max(w.cy for w in sources)
    body = _portal_body(lines, header_bottom)
    bounds = forms.table_columns(headers[:6], body)
    if bounds is None:
        return None
    date_left, date_right = bounds[5:7]
    if not all(date_left <= w.x0 and w.x1 <= date_right for w in headers[6]):
        return None
    # Existing row adapters take left boundaries. Source boundaries are now
    # observed corridors, including date cells printed above the row label.
    anchors = dict(zip(("insurance", "name", "category", "management", "workplace", "date"), bounds[:-1]))
    return header_bottom, anchors


def _portal_body(lines, header_bottom):
    end = min((min(w.cy for w in row) for row in lines
               if row[0].cy > header_bottom and any(w.text.startswith("▷") for w in row)), default=float('inf'))
    return [row for row in lines if header_bottom < row[0].cy < end]


def _portal_row_cells(words, anchors):
    bounds = [("name", anchors["name"], anchors["category"]),
              ("category", anchors["category"], anchors["management"]),
              ("management", anchors["management"], anchors["workplace"]),
              ("workplace", anchors["workplace"], anchors["date"])]
    cells = {}
    for key, left, right in bounds:
        value = squash(normalize_format_text(line_text([word for word in words if left <= word.x0 < right])))
        cells[key] = "" if re.fullmatch(r"[-]+", value) else value
    return cells


def _portal_dates(words):
    """Keep acquired and parenthesized receipt occurrences, even when equal."""
    acquired, received = [], []
    complete = True
    receipt_present = False
    for line in common.group_lines(words):
        text = normalize_format_text(line_text(line))
        receipt_present |= bool(re.search(r"\([^)]*\d", text))
        matches = list(common.DATE_RE.finditer(text))
        residue = list(text)
        for match in matches:
            value = common.parse_date(match.group())
            before, after = text[:match.start()].rstrip(), text[match.end():].lstrip()
            parenthesized = before.endswith("(")
            if parenthesized:
                if not after.startswith(")"):
                    complete = False
                else:
                    residue[len(before) - 1] = " "
                    residue[len(text) - len(after)] = " "
            elif after.startswith(")"):
                complete = False
            residue[match.start():match.end()] = " " * (match.end() - match.start())
            (received if parenthesized else acquired).append((value, line))
            complete &= value is not None
        if "".join(residue).strip() not in {"", "-", "(-)"}:
            complete = False
    complete &= len(acquired) == 1 and len(received) <= 1 and (not receipt_present or len(received) == 1)
    return acquired, received, receipt_present, complete


def _page_marker(lines: list[list[Word]]) -> bool:
    candidates = _page_marker_candidates(lines)
    text = re.sub(r"\s+", "", "".join(word.text for word in candidates))
    # Vision can drop the slash from the isolated top-right 1/1 marker.
    return bool(re.search(r"(?<!\d)1[/|／]1(?!\d)", text) or
                re.search(r"(?<!\d)111(?!\d)", text))


def _page_marker_candidates(lines: list[list[Word]]) -> list[Word]:
    """Return words in the top-right page-marker slot in reading order."""
    return sorted((word for line in lines for word in line
                   if 84 <= word.x0 <= 99 and 27 <= word.cy <= 33.5),
                  key=lambda word: (word.cy, word.x0))


def _portal_page_marker(lines):
    sections = [row for row in lines if "가입내역" in squash(line_text(row)) and
                any("■" in w.text or "발급일자현재기준" in squash(w.text) for w in row)]
    if len(sections) != 1:
        return []
    section = sections[0]
    hits = forms.label_hits([section], ("가입내역",))
    if len(hits) != 1:
        return []
    right = max(w.x1 for w in hits[0][1])
    return [w for w in section if w.x0 >= right and re.fullmatch(r"[\d/／\s]+", w.text)]


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


def _row_chunks(lines: list[list[Word]], header_bottom: float,
                starts: list[tuple[int, str]], *, portal=False) -> list[tuple[str, list[list[Word]]]]:
    """Group full row bands, including date cells printed above the insurance label.

    The first band's upper edge is the bottom of the two-line table header. Later
    edges are halfway between adjacent insurance labels, which delimit the rows
    when OCR does not expose the table's horizontal rules as words.
    """
    if not starts:
        return []
    centers = [lines[index][0].cy for index, _ in starts]
    chunks = []
    for i, (_, insurance) in enumerate(starts):
        top = header_bottom if i == 0 else (centers[i - 1] + centers[i]) / 2
        bottom = (centers[i] + centers[i + 1]) / 2 if i + 1 < len(starts) else (float('inf') if portal else 51.5)
        chunk = [line for line in lines if top < line[0].cy <= bottom]
        chunks.append((insurance, chunk))
    return chunks


def _table_header_y(lines: list[list[Word]]) -> float | None:
    for i in range(len(lines)):
        block = lines[i:min(i + 3, len(lines))]
        flat = squash("".join(line_text(row) for row in block))
        if "자격취득일" in flat and "신고접수일" in flat and "사업장" in flat:
            header_lines = [row for row in block if any(
                token in squash(line_text(row))
                for token in ("자격취득일", "신고접수일", "사업장"))]
            source_lines = header_lines or block
            return max(word.cy for row in source_lines for word in row)
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


def _parse_row(insurance: str, lines: list[list[Word]], anchors: dict[str, float],
               *, portal: bool = False) -> InsuranceRow:
    words = [word for line in lines for word in line if word.text]
    row = InsuranceRow(insurance_type=insurance, words=words)
    flat = squash("".join(word.text for word in words))
    cells = _portal_row_cells(words, anchors) if portal else {}
    inactive = (cells.get("name") == "미가입" and cells.get("category") in {"", "미가입"}) if portal else "미가입" in flat
    if inactive:
        row.status = "미가입"
        if portal:
            dates = squash(line_text([word for word in words if word.x0 >= anchors["date"] - (0 if portal else 3)]))
            row.cells_complete = (all(value in {"", "미가입"} for value in cells.values()) and
                                  dates in {"", "-", "(-)", "미가입"})
        return row
    row.status = "가입"
    row.date_column_words = [word for word in words if word.x0 >= anchors["date"] - (0 if portal else 3)]
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

    if portal:
        name_valid = bool(NAME_RE.fullmatch(cells["name"])) and not common.is_header_only_value(cells["name"])
        category_valid = cells["category"] in CATEGORY_NAMES
        management_valid = bool(re.fullmatch(r"\d{11}", cells["management"]))
        working = (cells["category"] in {"직장가입자", "사업장가입자"} or
                   insurance in {"산재보험", "고용보험"})
        workplace_valid = (bool(cells["workplace"]) and cells["workplace"] != "미가입" and
                           not common.is_header_only_value(cells["workplace"]))
        row.cells_complete = (name_valid and category_valid and
                              (not cells["management"] or management_valid) and
                              (not cells["workplace"] or workplace_valid) and
                              (not working or management_valid and workplace_valid))
        row.subscriber_name = cells["name"] if name_valid else ""
        row.subscriber_category = cells["category"] if category_valid else ""
        row.management_number = cells["management"] if management_valid else ""
        row.workplace_name = cells["workplace"] if workplace_valid else ""
        acquired, received, row.receipt_date_present, row.date_cells_complete = _portal_dates(row.date_column_words)
        if len(acquired) == 1:
            row.acquired, row.acquired_words = acquired[0]
        if len(received) == 1:
            row.received, row.received_words = received[0]
    else:
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
    form_kind = _form_kind(pages)
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
        portal_name, portal_name_words = None, []
        if form_kind == "portal":
            portal_name, portal_name_words, birth, birth_words = _portal_identity(words)
            # Resident numbers remain source-local; preserve the established
            # privacy contract by erasing their tokens after deriving birth.
            for word in birth_words:
                if any(char.isdigit() for char in word.text):
                    word.text = ""
        else:
            for line in lines:
                if RRN_RE.search(normalize_format_text("".join(word.text for word in line))):
                    birth = _erase_rrn(line) or birth
                    birth_words.extend(line)
        for source_word, normalized_word in zip(original_words, words):
            if not normalized_word.text and any(char.isdigit() for char in source_word.text):
                source_word.text = ""
        lines = common.group_lines(words)
        issue_scope = [w for row in _portal_grid_rows(lines) for w in row] if form_kind == "portal" else words
        selected_issue = select_issue_date(issue_scope, scoped=form_kind == "portal")
        issue = selected_issue.value
        doc_no = issue_number = name = None
        if form_kind == "portal":
            name = portal_name
        doc_words: list[Word] = []
        issue_number_words: list[Word] = []
        issue_words = selected_issue.source_words
        name_words: list[Word] = portal_name_words if form_kind == "portal" else []
        if form_kind == "portal":
            issue_number, issue_number_words = _portal_issue_number(lines)
        for line in lines:
            flat = squash(line_text(line))
            if doc_no is None:
                match = DOC_NO_RE.search(normalize_format_text("".join(word.text for word in line)))
                if match:
                    doc_no, doc_words = match.group(1), line
            if form_kind != "portal" and issue_number is None and "발급" in flat:
                candidates = [word for word in line if word.x0 < 55 and any(char.isdigit() for char in word.text)]
                joined_digits = "".join(re.findall(r"\d+", "".join(word.text for word in candidates)))
                match_number = ISSUE_NUMBER_RE.search(joined_digits)
                if match_number:
                    issue_number = match_number.group()
                    issue_number_words = candidates
            if form_kind != "portal" and name is None and "성명" in flat:
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
    marker_ok = len(headers) == 1 and _page_marker(headers[0]["lines"])
    if form_kind == "portal" and len(headers) == 1:
        marker = squash("".join(word.text for word in _portal_page_marker(headers[0]["lines"])))
        marker_ok = bool(re.fullmatch(r"1[/／]1", marker))
    validations.append(common.Validation("page_marker_1_of_1", marker_ok))
    if form_kind == "unknown":
        validations.append(common.Validation("form_recognized", False))

    for key, label in (("doc_no", "문서확인번호"), ("issue_number", "발급번호"),
                       ("issue", "발급일"), ("name", "성명"), ("birth", "생년월일")):
        if form_kind == "portal" and key == "doc_no":
            continue
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

    doc_value = fields.get("발급번호" if form_kind == "portal" else "문서확인번호")
    number_pattern = ISSUE_NUMBER_RE if form_kind == "portal" else DOC_NO_RE
    validations.append(common.Validation("document_number_format", bool(doc_value and number_pattern.fullmatch(str(doc_value.value)))))
    issue_field = fields.get("발급일")
    issue_date = date.fromisoformat(str(issue_field.value)) if issue_field else None
    validations.append(common.Validation("issue_not_future", issue_date is not None and issue_date <= today))
    names = [h["name"] for h in headers]
    validations.append(common.Validation("name_consistent", bool(names) and len(names) == len(headers) and len(set(names)) == 1))

    all_rows: list[InsuranceRow] = []
    for page, _ in pages:
        lines = page_lines[page.page]
        if form_kind == "portal":
            layout = _portal_table_layout(lines)
            validations.append(common.Validation("portal_table_columns", layout is not None))
            if layout is None:
                continue
            header_y, anchors = layout
            body = _portal_body(lines, header_y)
            starts = [(i, squash(w.text)) for i, row in enumerate(body) for w in row
                      if squash(w.text) in INSURANCE_NAMES]
            row_chunks = _row_chunks(body, header_y, starts, portal=True)
        else:
            header_y = _table_header_y(lines)
            starts = _row_starts(lines, header_y if header_y is not None else 33.5)
            row_chunks = _row_chunks(lines, header_y if header_y is not None else 33.5, starts)
            anchors = {
                "name": _header_x(lines, "성명", 22.0, header_y or 33.5),
                "category": _header_x(lines, "가입자종별", 33.5, header_y or 33.5),
                "management": _header_x(lines, "관리번호", 47.5, header_y or 33.5),
                "workplace": _header_x(lines, "사업장명칭", 64.0, header_y or 33.5),
                "date": _header_x(lines, "자격취득일", 81.5, header_y or 33.5),
            }
        for insurance, chunk in row_chunks:
            all_rows.append(_parse_row(insurance, chunk, anchors, portal=form_kind == "portal"))

    expected_order = list(INSURANCE_NAMES)
    actual_order = [row.insurance_type for row in all_rows]
    validations.append(common.Validation("four_rows_in_order", actual_order == expected_order))
    validations.append(common.Validation("insurance_names_recognized", len(set(actual_order)) == 4))
    if form_kind == "portal":
        validations.append(common.Validation("portal_row_cells", bool(all_rows) and all(row.cells_complete for row in all_rows)))
    nonempty = [row for row in all_rows if row.status != "미가입"]
    dates_read = all(row.acquired is not None and row.date_cells_complete and
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

    structure_complete = None
    if form_kind != "government24":
        structure_complete = form_kind == "portal" and all(check.passed for check in validations)
        if not structure_complete:
            for extracted in fields.values():
                extracted.confidence = min(extracted.confidence, 0.4)
            warnings.append("양식 또는 가입 표를 완전히 읽지 못해 담당자 확인이 필요합니다.")
    return Insurance4Result(detected, type_confidence, fields, all_rows, validations,
                            list(dict.fromkeys(warnings)), diagnostics, form_kind, structure_complete)

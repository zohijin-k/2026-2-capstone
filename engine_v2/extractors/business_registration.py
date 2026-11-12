"""Coordinate reader for NTS business-registration proofs."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
import re
from statistics import median

from . import job_common, nhis_common as common, nhis_forms as forms
from .resident_abstract import kst_today
from ..pipeline.layout import group_lines, line_text, normalize, squash
from ..pipeline.field_safety import is_header_only_value
from ..schemas.models import DocType, ExtractedField


ROW_LABELS = {
    "상호": ("상호(법인명)", "상호"),
    "사업자등록번호": ("사업자등록번호",),
    "성명": ("대표자성명(대표유형)", "대표자성명"),
    "등록번호": ("주민(법인)등록번호",),
    "사업장소재지": ("사업장소재지",),
    "개업일": ("개업일",),
    "사업자등록일": ("사업자등록일",),
    "업태": ("업태",),
    "종목": ("종목",),
}
REQUIRED_FIELDS = ("발급번호", "과세유형", "상호", "사업자등록번호", "성명", "생년월일",
                   "사업장소재지", "개업일", "사업자등록일", "업태", "종목", "공동사업자유무", "발급일")
ISSUE_NUMBER_RE = re.compile(r"\d{4}-\d{3}-\d{4}-\d{3}")
BUSINESS_NUMBER_RE = re.compile(r"\d{3}-\d{2}-\d{5}")
REPRESENTATIVE_RE = re.compile(r"([가-힣]{2,6})(?:\((?:대표|대표자|공동대표|각자대표|단독대표)\))?")
LABEL_VALUES = {squash(alias) for aliases in ROW_LABELS.values() for alias in aliases}


@dataclass
class Extraction:
    detected_type: DocType
    type_confidence: float
    fields: dict[str, ExtractedField]
    validations: list[common.Validation]
    warnings: list[str] = field(default_factory=list)
    form_kind: str = "nts_business_proof"
    structure_complete: bool = False


def _label_hits(lines, aliases, *, x_bounds=None):
    hits = forms.label_hits(lines, aliases, x_bounds=x_bounds)
    unique = {}
    for _, words in hits:
        unique[tuple(id(word) for word in words)] = words
    selected = []
    for words in sorted(unique.values(), key=len, reverse=True):
        if not any(all(any(word is other for other in existing) for word in words) for existing in selected):
            selected.append(words)
    return selected


def _unique_label(lines, aliases, *, x_bounds=None):
    for row in lines:
        scoped = row if x_bounds is None else [word for word in row
                                              if x_bounds[0] <= word.x0 and word.x1 <= x_bounds[1]]
        flat = squash(line_text(scoped))
        if any(flat.count(squash(alias)) > 1 for alias in aliases):
            return []
    hits = _label_hits(lines, aliases, x_bounds=x_bounds)
    return hits[0] if len(hits) == 1 else []


def _center(words):
    return sum(word.cy for word in words) / len(words)


def _text(words):
    return " ".join(line_text(row) for row in group_lines(words)).strip()


def _date(words):
    value = squash(common.normalize_format_text(_text(words))).removesuffix(".")
    return common.parse_date(value) if common.DATE_RE.fullmatch(value) else None


def representative_name(text):
    value = squash(text)
    match = REPRESENTATIVE_RE.fullmatch(value)
    if match and value not in LABEL_VALUES and not is_header_only_value(match[1]):
        return match[1]
    return None


def _grid(lines, title, joint_headers):
    """Establish the label column before accepting justified sparse labels."""
    if not title or not joint_headers:
        return {}, False
    title_bottom = max(word.y1 for word in title)
    bottom = min(word.y0 for word in joint_headers)
    region = [row for row in lines if title_bottom < row[0].cy < bottom]
    anchors = [_unique_label(region, ROW_LABELS[key]) for key in
               ("사업자등록번호", "등록번호", "사업장소재지", "사업자등록일")]
    if any(not anchor for anchor in anchors):
        return {}, False
    anchors.extend(anchor for key in ("상호", "성명")
                   if (anchor := _unique_label(region, ROW_LABELS[key])))
    glyph = median((word.x1 - word.x0) / max(len(squash(word.text)), 1)
                   for anchor in anchors for word in anchor)
    left = min(word.x0 for anchor in anchors for word in anchor) - glyph
    right = max(word.x1 for anchor in anchors for word in anchor) + glyph
    labels = {key: _unique_label(region, aliases, x_bounds=(left, right))
              for key, aliases in ROW_LABELS.items()}
    if any(not words for words in labels.values()):
        return {}, False
    centers = [_center(words) for words in labels.values()]
    if any(a >= b for a, b in zip(centers, centers[1:])):
        return {}, False
    label_right = max(word.x1 for words in labels.values() for word in words)
    step = median(b - a for a, b in zip(centers, centers[1:]))
    top = min(word.y0 for word in labels["상호"]) - step / 2
    bottom = (centers[-1] + bottom) / 2
    values = [word for row in lines for word in row
              if top < word.cy < bottom and word.x0 > label_right]
    if not values:
        return {}, False
    value_left = min(word.x0 for word in values)
    if value_left - label_right < glyph / 2:
        return {}, False
    boundary = (label_right + value_left) / 2
    bounds = [top, *[(a + b) / 2 for a, b in zip(centers, centers[1:])], bottom]
    cells = {}
    complete = True
    label_ids = {id(word) for words in labels.values() for word in words}
    for index, key in enumerate(labels):
        band = [word for row in lines for word in row if bounds[index] < word.cy < bounds[index + 1]
                and id(word) not in label_ids]
        complete &= not any(word.x0 < boundary < word.x1 for word in band)
        cells[key] = [word for word in band if word.x0 >= boundary]
    return cells, complete


def _joint_business(lines, confirmation):
    name_header = _unique_label(lines, ("성명(법인명)",))
    number_header = _unique_label(lines, ("주민(사업자)등록번호",))
    label = _unique_label(lines, ("공동사업자",))
    headers = [*name_header, *number_header]
    if not name_header or not number_header or not label or not confirmation:
        return None, headers, []
    top = max(word.y1 for word in headers)
    bottom = min(word.y0 for word in confirmation)
    boundary = (max(word.x1 for word in name_header) + min(word.x0 for word in number_header)) / 2
    glyph = median((word.x1 - word.x0) / max(len(squash(word.text)), 1) for word in headers)
    height = median(word.y1 - word.y0 for word in headers)
    left = min(word.x0 for word in name_header) - 4 * glyph
    body = [word for row in lines for word in row if top < word.cy < bottom and word.x1 > left
            and all(word is not heading for heading in label)]
    absent = []
    remaining = []
    for row in group_lines(body):
        text = squash(line_text(row)).rstrip(".")
        if text == "해당사항이없습니다":
            absent.append(row)
        else:
            remaining.extend(word for word in row if re.search(r"[가-힣A-Za-z0-9*]", word.text))
    partial = any(word.x0 < boundary < word.x1 for word in remaining)
    name_rows = []
    number_rows = []
    fragments = False
    for names in group_lines([word for word in remaining if word.x1 <= boundary]):
        name = squash(_text(names))
        name_shape = (bool(re.fullmatch(r"[가-힣A-Za-z0-9()（）·&.,]{2,80}", name))
                      and bool(re.search(r"[가-힣A-Za-z]", name)) and not is_header_only_value(name))
        normal_geometry = all(
            word.y1 - word.y0 <= 1.8 * height and
            (word.x1 - word.x0) / max(len(squash(word.text)), 1) <= 2.5 * glyph for word in names)
        if name_shape and normal_geometry:
            name_rows.append(names)
        elif not normal_geometry:
            # Oversized fragments have an unknown purpose in shape evidence.
            fragments = True
        else:
            partial = True
    for numbers in group_lines([word for word in remaining if word.x0 >= boundary]):
        number = squash(common.normalize_format_text(_text(numbers)))
        number_ok = bool((common.MASKED_RRN_RE.fullmatch(number) or common.RRN_RE.fullmatch(number))
                         and common.birth_from_rrn(number))
        if BUSINESS_NUMBER_RE.fullmatch(number):
            number_ok = job_common.brn_is_valid(number)
        if number_ok:
            number_rows.append(numbers)
        else:
            partial = True
    if partial or len(absent) > 1 or (absent and (name_rows or number_rows)) or (fragments and not absent):
        return None, headers, body
    if len(absent) == 1:
        return False, headers, body
    if not name_rows or len(name_rows) != len(number_rows):
        return None, headers, body
    offsets = [_center(numbers) - _center(names) for names, numbers in zip(name_rows, number_rows)]
    heights = [word.y1 - word.y0 for row in [*name_rows, *number_rows] for word in row]
    if len(offsets) == 1:
        aligned = abs(offsets[0]) <= .6 * max(heights)
    else:
        pitch = median(_center(b) - _center(a) for rows in (name_rows, number_rows)
                       for a, b in zip(rows, rows[1:]))
        offset = median(offsets)
        aligned = abs(offset) < .45 * pitch and all(abs(value - offset) < .45 * pitch for value in offsets)
    return (True if aligned else None), headers, body


def _issue_date(lines, confirmation):
    if not confirmation:
        return None, []
    issuer = _unique_label([row for row in lines if row[0].cy > _center(confirmation)], ("세무서장",))
    if not issuer:
        return None, []
    notice = _unique_label([row for row in lines if _center(confirmation) < row[0].cy < _center(issuer)],
                           ("발급일현재",))
    if not notice:
        return None, []
    top = max(word.y1 for word in [*confirmation, *notice])
    bottom = min(word.y0 for word in issuer)
    glyph = median((word.x1 - word.x0) / max(len(squash(word.text)), 1) for word in issuer)
    left, right = min(word.x0 for word in issuer) - glyph, max(word.x1 for word in issuer) + glyph
    issuer_bottom = max(word.y1 for word in issuer)
    competing = [word for row in lines for word in row
                 if all(word is not issuing_word for issuing_word in issuer)
                 and word.y1 > bottom and word.y0 < issuer_bottom
                 and word.x1 > left and word.x0 < right and re.search(r"\d", word.text)]
    if competing:
        return None, competing
    region = [word for row in lines
              if any(top < item.cy < bottom and item.x1 > left and item.x0 < right for item in row)
              for word in row if top < word.cy < bottom and word.x1 > left]
    candidates = [row for row in group_lines(region) if re.search(r"\d", line_text(row))]
    if len(candidates) != 1:
        return None, region
    return _date(candidates[0]), candidates[0]


def extract(pages, today=None):
    today = today or kst_today()
    fields = {}
    checks = []
    if not pages:
        return Extraction(DocType.UNKNOWN, 0, {}, [common.Validation("business_single_page", False)])
    page, result = pages[0]
    words = normalize(result.words, page.page, page.pixel_size)
    lines = group_lines(words)
    title = _unique_label([row for row in lines if row[0].cy < 35], ("사업자등록증명",))
    detected = DocType.BIZ_REG_PROOF if title else DocType.UNKNOWN
    checks.extend((common.Validation("business_title", bool(title)),
                   common.Validation("business_single_page", len(pages) == 1)))
    confirmation = _unique_label(lines, ("증명합니다",))
    joint, joint_headers, joint_words = _joint_business(lines, confirmation)
    cells, grid_ok = _grid(lines, title, joint_headers)
    checks.append(common.Validation("business_label_grid", grid_ok))
    values = {}
    evidence = {}

    def retain(key, value, source):
        if value is not None and value != "":
            values[key] = value
            evidence[key] = source

    for key in ("상호", "사업장소재지"):
        source = cells.get(key, [])
        text = _text(source)
        retain(key, text if text and squash(text) not in LABEL_VALUES and not is_header_only_value(text) else None, source)
    number_words = cells.get("사업자등록번호", [])
    number = squash(common.normalize_format_text(_text(number_words)))
    number_format = bool(BUSINESS_NUMBER_RE.fullmatch(number))
    checksum = number_format and job_common.brn_is_valid(number)
    retain("사업자등록번호", number if number_format else None, number_words)
    checks.extend((common.Validation("business_number_format", number_format),
                   common.Validation("business_number_checksum", checksum)))
    source = cells.get("성명", [])
    retain("성명", representative_name(_text(source)), source)
    code = int(number[4:6]) if checksum else 0
    personal = checksum and (1 <= code <= 79 or 90 <= code <= 99)
    birth_words = cells.get("등록번호", [])
    identifier = squash(common.normalize_format_text(_text(birth_words)))
    valid_rrn = common.MASKED_RRN_RE.fullmatch(identifier) or common.RRN_RE.fullmatch(identifier)
    birth = common.birth_from_rrn(identifier) if personal and valid_rrn else None
    retain("생년월일", birth, birth_words)
    for key in ("개업일", "사업자등록일"):
        retain(key, _date(cells.get(key, [])), cells.get(key, []))
    for key in ("업태", "종목"):
        source = cells.get(key, [])
        items = [re.sub(r"\s+", " ", item).strip() for item in _text(source).split("|")]
        retain(key, items if items and all(item and squash(item) not in LABEL_VALUES for item in items) else None, source)
    retain("공동사업자유무", joint, joint_words)
    issue, issue_words = _issue_date(lines, confirmation)
    retain("발급일", issue, issue_words)
    checks.extend((common.Validation("business_joint_section_read", joint is not None),
                   common.Validation("business_issue_location_unique", issue is not None)))
    if title and cells:
        first = min(word.y0 for word in cells["상호"]) if cells.get("상호") else max(word.y1 for word in title)
        issuance_label = _unique_label([row for row in lines if row[0].cy < first], ("발급번호",))
        candidates = []
        if issuance_label:
            left, right = min(word.x0 for word in issuance_label), max(word.x1 for word in issuance_label)
            bottom = max(word.y1 for word in issuance_label)
            candidates = [word for word in words if bottom < word.cy < first
                          and word.x1 > left and word.x0 < right]
        issuance_rows = group_lines(candidates)
        issuance = squash(common.normalize_format_text(_text(candidates)))
        retain("발급번호", issuance if len(issuance_rows) == 1 and ISSUE_NUMBER_RE.fullmatch(issuance) else None, candidates)
        tax_words = [word for word in words if max(item.y1 for item in title) < word.cy < first
                     and word.x1 > min(item.x0 for item in title)
                     and word.x0 < max(item.x1 for item in title)]
        tax_candidates = [(row, re.fullmatch(r"\(([^()]+(?:과세자|사업자)(?:\(법인\))?)\)", squash(line_text(row))))
                          for row in group_lines(tax_words)]
        tax_candidates = [(row, match) for row, match in tax_candidates if match]
        if len(tax_candidates) == 1:
            retain("과세유형", tax_candidates[0][1][1], tax_candidates[0][0])
    corporate_type = "법인" in values.get("과세유형", "")
    if corporate_type:
        values.pop("생년월일", None)
        evidence.pop("생년월일", None)
    checks.append(common.Validation("business_entity_consistent", not (corporate_type and personal)))
    checks.extend(common.Validation(f"business_{key}_read", key in values) for key in REQUIRED_FIELDS)
    registered = values.get("사업자등록일")
    date_order = issue is not None and registered is not None and registered <= issue
    checks.extend((common.Validation("business_registered_not_after_issue", date_order),
                   common.Validation("business_issue_not_future", issue is not None and issue <= today)))
    complete = all(check.passed for check in checks)
    confidence = .95 if complete else .4
    page_map = {item.page: item for item, _ in pages}
    sources = common.sources_by_page(pages)
    for key, value in values.items():
        source = evidence[key]
        raw = value.isoformat() if key == "생년월일" else _text(source)
        fields[key] = common.make_field(value, raw, source, page_map, confidence, sources)
    warnings = [] if complete else ["사업자등록증명의 필수 정보 또는 양식 구조를 완전히 확인하지 못했습니다."]
    return Extraction(detected, .95 if title else 0, fields, checks, warnings, structure_complete=complete)

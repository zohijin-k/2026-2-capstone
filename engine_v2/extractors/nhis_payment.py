"""건강보험료 납부확인서 판독기. 월별 고지 열을 기준으로 보험료를 검증한다."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date

from ..pipeline.layout import line_text, squash
from ..pipeline.ocr import OcrResult
from ..pipeline.preprocess import PageImage
from ..schemas.models import DocType, ExtractedField
from . import nhis_common as common

MONTH_RE = re.compile(r"(?<!\d)(20\d{2})\s*(?:(?:[-./]\s*)|(?:년\s*)|\s)(0?[1-9]|1[0-2])\s*월?\s*\.?(?!\d)")
COMPACT_MONTH_RE = re.compile(r"(?<!\d)(20\d{2})(0[1-9]|1[0-2])(?!\d)")
MONEY_RE = re.compile(r"(?<!\d)(-?\s*\d[\d,\s]*)(?:원)?(?!\d)")
CARE = ("장기요양보험료", "장기요양", "노인장기요양")
HEALTH = ("건강보험료", "건강보험")
MONTH_LABELS = ("년월", "보험료월", "납부월", "납부년월", "청구월", "보험료연월")
TABLE_LABELS = MONTH_LABELS + ("고지금액", "고지보험료", "납부금액", "납부보험료", "실납부",
                               "건강보험료", "장기요양보험료", "장기요양")
TABLE_LABEL_FRAGMENTS = ("고지", "금액", "납부", "보험료", "건강", "장기요양", "실납부", "년", "월")


@dataclass
class PaymentResult:
    detected_type: DocType
    type_confidence: float
    fields: dict[str, ExtractedField]
    validations: list[common.Validation]
    warnings: list[str] = field(default_factory=list)
    diagnostics: dict[str, str] = field(default_factory=dict)


def _money_words(line):
    found = []
    row_text = " ".join(word.text for word in line)
    has_month = bool(MONTH_RE.search(row_text) or COMPACT_MONTH_RE.search(row_text))
    i = 0
    while i < len(line):
        accepted = None
        date_prefix = False
        for end in range(i + 1, min(len(line), i + 4) + 1):
            words = line[i:end]
            raw = "".join(word.text for word in words).replace("원", "")
            if MONTH_RE.fullmatch(raw) or COMPACT_MONTH_RE.fullmatch(raw):
                date_prefix = True
                break
            if has_month and re.fullmatch(r"20\d{2}", raw.strip()):
                continue
            match = MONEY_RE.fullmatch(re.sub(r"\s+", "", raw))
            if not match:
                continue
            digits = match.group(1).replace(",", "").replace(" ", "")
            if digits in ("", "-"):
                continue
            if raw.rstrip().endswith(",") and end < len(line):
                next_word = line[end]
                gap = next_word.x0 - max(word.x1 for word in words)
                height = max(max(word.y1 - word.y0, 0.3) for word in words + [next_word])
                if gap <= height * 2:
                    continue
            x0, y0 = min(w.x0 for w in words), min(w.y0 for w in words)
            x1, y1 = max(w.x1 for w in words), max(w.y1 for w in words)
            px = (min(w.px[0] for w in words), min(w.px[1] for w in words),
                  max(w.px[2] for w in words), max(w.px[3] for w in words))
            merged = common.Word(raw, min(w.conf for w in words), words[0].page, x0, y0, x1, y1, px)
            accepted = (merged, int(digits))
            i = end
            break
        if accepted:
            found.append(accepted)
        elif date_prefix:
            i += 1
        else:
            i += 1
    return found


def _month_header(lines):
    def exact_header(block):
        return [(label, words) for label, words in common.label_hits(block, MONTH_LABELS)
                if squash("".join(word.text for word in words)) == squash(label)]

    found = [i for i, line in enumerate(lines) if exact_header([line])]
    for i in range(1, len(lines)):
        current_ids = {id(word) for word in lines[i]}
        prior_ids = {id(word) for line in lines[max(0, i - 2) : i] for word in line}
        if any(any(id(word) in current_ids for word in words) and
               any(id(word) in prior_ids for word in words) for _, words in exact_header(lines[max(0, i - 2) : i + 1])):
            found.append(i)
    return sorted(set(found))


def _header_block(lines, index):
    included = {index}
    cursor = index - 1
    while cursor >= 0:
        line = lines[cursor]
        flat = squash(line_text(line))
        neighbor = lines[cursor + 1]
        partial_label = common.label_hits([line, neighbor], TABLE_LABELS)
        full_label = any(label in flat for label in TABLE_LABELS) or flat in TABLE_LABEL_FRAGMENTS
        if not partial_label and not full_label:
            break
        if MONTH_RE.search(line_text(line)) or COMPACT_MONTH_RE.search(re.sub(r"\s+", "", line_text(line))):
            break
        included.add(cursor)
        cursor -= 1
    cursor = index + 1
    while cursor < len(lines):
        line = lines[cursor]
        flat = squash(line_text(line))
        neighbor = lines[cursor - 1]
        partial_label = common.label_hits([neighbor, line], TABLE_LABELS)
        full_label = any(label in flat for label in TABLE_LABELS) or flat in TABLE_LABEL_FRAGMENTS
        if not partial_label and not full_label:
            break
        if MONTH_RE.search(line_text(line)) or COMPACT_MONTH_RE.search(re.sub(r"\s+", "", line_text(line))):
            break
        included.add(cursor)
        cursor += 1
    return [lines[i] for i in sorted(included)]


def _header_x(pages, labels, page_no=None):
    positions = []
    for page, result in pages:
        if page_no is not None and page.page != page_no:
            continue
        lines = common.page_lines(page, result)
        for index in _month_header(lines):
            block = _header_block(lines, index)
            for _, words in common.label_hits(block, labels):
                if words:
                    positions.append((min(w.x0 for w in words) + max(w.x1 for w in words)) / 2)
    return positions


def _closest_amount(amounts, x):
    return min(amounts, key=lambda item: abs((item[0].x0 + item[0].x1) / 2 - x)) if amounts else None


def _extract_monthly(pages):
    charge_xs = _header_x(pages, ("고지금액", "고지보험료"))
    paid_xs = _header_x(pages, ("납부금액", "납부보험료", "실납부"))
    health_xs = _header_x(pages, HEALTH)
    care_xs = _header_x(pages, CARE)
    all_text = " ".join(result.text for _, result in pages)
    flat = squash(all_text)
    separate_components = bool(health_xs and care_xs and health_xs[0] != care_xs[0])
    combined = ("건강보험료및장기요양보험료합계" in flat or
                ("합계" in flat and any(word in flat for word in CARE) and not separate_components))

    monthly: dict[tuple[int, int], tuple[int, list[common.Word]]] = {}
    care_monthly: dict[tuple[int, int], tuple[int, list[common.Word]]] = {}
    totals: list[int] = []
    all_months: list[tuple[int, int]] = []
    target_seen: set[tuple[int, int]] = set()
    target_words: dict[tuple[int, int], list[common.Word]] = {}
    money_numeric = True
    nonpositive = False
    for page, result in pages:
        page_charge_xs = _header_x([(page, result)], ("고지금액", "고지보험료"))
        page_paid_xs = _header_x([(page, result)], ("납부금액", "납부보험료", "실납부"))
        page_health_xs = _header_x([(page, result)], HEALTH)
        page_care_xs = _header_x([(page, result)], CARE)
        lines = common.page_lines(page, result)
        header_indices = _month_header(lines)
        if not header_indices:
            continue
        table_start = max(header_indices)
        for line in lines[table_start + 1 :]:
            text = line_text(line)
            compact = COMPACT_MONTH_RE.findall(text)
            matches = MONTH_RE.findall(text) + compact
            months = [(int(y), int(m)) for y, m in matches]
            if not months:
                if "합계" in squash(text):
                    amounts = _money_words(line)
                    if amounts and page_charge_xs:
                        chosen = _closest_amount(amounts, page_charge_xs[0])
                        if chosen:
                            totals.append(chosen[1])
                continue
            for ym in months:
                all_months.append(ym)
            target = [ym for ym in months if ym[0] == 2025 and ym[1] in (10, 11, 12)]
            if not target:
                continue
            target_seen.update(target)
            for ym in target:
                target_words.setdefault(ym, list(line))
            amounts = _money_words(line)
            if not amounts:
                money_numeric = False
                continue
            if any(value <= 0 for _, value in amounts):
                nonpositive = True
                money_numeric = False
                continue
            charge_x = page_charge_xs[0] if page_charge_xs else None
            paid_x = page_paid_xs[0] if page_paid_xs else None
            care_x = page_care_xs[0] if page_care_xs else None
            component_columns = bool(page_health_xs and care_x is not None and page_health_xs[0] != care_x)
            health_x = page_health_xs[0] if component_columns else charge_x
            if charge_x is None or (paid_x is None and len(amounts) > 1 and not component_columns):
                money_numeric = False
                continue
            billed = _closest_amount(amounts, health_x if health_x is not None else charge_x)
            if billed and paid_x is not None and len(amounts) > 1:
                paid = _closest_amount(amounts, paid_x)
                if paid is billed:
                    billed = None
            if billed:
                for ym in target:
                    monthly[ym] = (billed[1], [billed[0]])
            if care_x is not None and len(amounts) > 1 and not combined:
                care_amount = _closest_amount([item for item in amounts if item is not billed], care_x)
                if care_amount:
                    for ym in target:
                        care_monthly[ym] = (care_amount[1], [care_amount[0]])

    return monthly, care_monthly, totals, all_months, target_seen, target_words, money_numeric, combined, nonpositive


def _average(values: dict[tuple[int, int], tuple[int, list[common.Word]]]):
    months = [(2025, 10), (2025, 11), (2025, 12)]
    if not all(month in values for month in months):
        return None, []
    rows = [values[month] for month in months]
    average = (sum(row[0] for row in rows) * 2 + 3) // 6
    return average, [word for _, words in rows for word in words]


def extract(pages: list[tuple[PageImage, OcrResult]], today: date | None = None) -> PaymentResult:
    del today
    headers = common.page_headers(pages)
    page_map = {page.page: page for page, _ in pages}
    sources = common.sources_by_page(pages)
    validations: list[common.Validation] = []
    warnings: list[str] = []
    fields: dict[str, ExtractedField] = {}
    diagnostics: dict[str, str] = {}

    title = squash(" ".join(result.text for _, result in pages))
    detected = DocType.NHIS_PAYMENT if any(k in title for k in ("보험료납부확인", "건강보험료납부확인")) else DocType.UNKNOWN
    type_confidence = 0.95 if detected == DocType.NHIS_PAYMENT else 0.2
    validations.append(common.Validation("document_type", detected == DocType.NHIS_PAYMENT))

    for key, label in (("name", "성명"), ("birth", "생년월일"), ("issue", "발급일")):
        value, words, same = common.consensus(headers, key)
        if key == "issue":
            same = bool(value) and all(h.issue in (None, value) for h in headers)
        validations.append(common.Validation(f"{label}_consistent", bool(value) and same))
        if value is not None:
            rendered = value.isoformat() if isinstance(value, date) else str(value)
            fields[label] = common.make_field(value=rendered, raw=rendered, words=words, pages=page_map,
                                              confidence=common.confidence([same], same), sources=sources)
        elif key in ("name", "birth", "issue"):
            warnings.append(f"{label}을 찾지 못해 담당자 확인이 필요합니다.")
            diagnostics[label] = f"라벨 '{label}' 또는 값을 찾지 못함"

    name, _, names_same = common.consensus(headers, "name")
    validations.append(common.Validation("page_names_match", bool(name) and names_same))
    if not names_same:
        warnings.append("쪽마다 성명이 같지 않거나 일부 쪽에서 찾지 못했습니다.")

    text = squash(" ".join(result.text for _, result in pages))
    insurance_type = "직장" if "직장가입자" in text or "직장가입" in text else "지역" if "지역가입자" in text or "지역가입" in text else None
    if insurance_type:
        fields["가입구분"] = common.make_field(insurance_type, insurance_type, None, page_map, 0.9, sources)
    else:
        diagnostics["가입구분"] = "가입구분 또는 직장·지역 표기를 못 찾음"
    validations.append(common.Validation("insurance_type_found", insurance_type is not None))

    monthly, care_monthly, totals, all_months, found_months_set, month_words, numeric, combined, nonpositive = _extract_monthly(pages)
    charge_headers = _header_x(pages, ("고지금액", "고지보험료"))
    paid_headers = _header_x(pages, ("납부금액", "납부보험료", "실납부"))
    month_headers = _header_x(pages, MONTH_LABELS)
    target_months = [(2025, 10), (2025, 11), (2025, 12)]
    found_months = [ym for ym in target_months if ym in found_months_set]
    month_text = ",".join(f"{year}-{month:02}" for year, month in found_months)
    if month_text:
        fields["고지월"] = common.make_field(month_text, month_text,
            [w for ym in found_months for w in month_words.get(ym, [])], page_map,
            common.confidence([len(found_months) == 3]), sources)
    validations.append(common.Validation("target_billing_months_found", len(found_months) == 3))
    all_amounts_found = all(month in monthly for month in target_months)
    validations.append(common.Validation("monthly_amounts_numeric", numeric and all_amounts_found))
    if found_months != target_months:
        warnings.append("2025년 10~12월 고지금액 중 찾지 못한 달이 있어 건강보험료를 계산하지 않았습니다.")
        missing = next((month for month in target_months if month not in found_months_set), None)
        if missing and month_headers:
            diagnostics["건강보험료"] = f"열 제목은 찾았으나 {missing[0]}-{missing[1]:02} 줄 없음"
        elif not month_headers:
            diagnostics["건강보험료"] = "열 제목 '년월' 못 찾음"
    elif not all_amounts_found:
        warnings.append("고지월은 찾았지만 일부 고지금액이 없어 건강보험료를 계산하지 않았습니다.")
        diagnostics["건강보험료"] = ("라벨 '고지금액' 못 찾음" if not charge_headers else
                                       "고지금액 후보 2개(열 구분 실패)" if not paid_headers else
                                       "고지월 줄은 찾았으나 고지금액 셀을 못 읽음")
    if combined:
        warnings.append("건강보험료와 장기요양보험료의 합계만 보여 건강보험료를 분리하지 못했습니다.")
        diagnostics["건강보험료"] = "건강보험료와 장기요양보험료 합계만 확인됨"
    if nonpositive:
        warnings.append("월별 금액에 0 또는 음수가 있어 건강보험료를 확정하지 않았습니다.")

    average, amount_words = _average(monthly)
    if average is not None and not combined:
        fields["건강보험료"] = common.make_field(str(average), str(average), amount_words, page_map,
            common.confidence([numeric, len(found_months) == 3, not combined]), sources)
    elif average is None or combined:
        warnings.append("건강보험료를 확정할 수 없어 담당자 확인이 필요합니다.")
        diagnostics.setdefault("건강보험료", "고지금액 라벨 또는 필요한 월별 금액을 확인하지 못함")

    care_average, care_words = _average(care_monthly)
    if care_average is not None:
        fields["장기요양보험료"] = common.make_field(str(care_average), str(care_average), care_words, page_map,
            common.confidence([len(care_monthly) == 3]), sources)
    else:
        care_headers = _header_x(pages, CARE)
        diagnostics["장기요양보험료"] = ("라벨 '장기요양보험료' 못 찾음" if not care_headers else
                                         "장기요양보험료 월별 셀을 모두 읽지 못함")

    ordered = sorted(all_months)
    continuous = all((b[0] - a[0]) * 12 + b[1] - a[1] == 1 for a, b in zip(ordered, ordered[1:]))
    validations.append(common.Validation("months_continuous", bool(ordered) and continuous))
    if ordered and not continuous:
        warnings.append("월별 표의 년월이 연속되지 않아 담당자 확인이 필요합니다.")

    total_matches = not totals or (len(totals) == 1 and all_amounts_found and found_months == target_months and
                                   totals[0] == sum(monthly[m][0] for m in target_months))
    validations.append(common.Validation("monthly_total_matches", total_matches))
    if not total_matches:
        warnings.append("월별 고지금액 합계가 표의 합계와 맞지 않습니다.")

    return PaymentResult(detected, type_confidence, fields, validations,
                         list(dict.fromkeys(warnings)), diagnostics)

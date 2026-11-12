"""공통 단어·날짜·머리글 처리. 위치 판단은 페이지 대비 퍼센트 좌표를 쓴다."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import date

from ..pipeline.layout import Word, group_lines, line_text, normalize, squash
from ..pipeline.field_safety import is_header_only_value
from ..pipeline.ocr import OcrResult
from ..pipeline.preprocess import PageImage, PageSource
from ..schemas.models import BBox, ExtractedField, FieldSource

from .format_text import normalize_format_text

DATE_RE = re.compile(r"(?<!\d)(\d{4})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})\s*일?(?!\d)")
COMPACT_DATE_RE = re.compile(r"(?<!\d)(20\d{2})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])(?!\d)")
RRN_RE = re.compile(r"(\d{6})\s*[-‐‑‒–—―−﹘﹣－]\s*([1-8])\s*\d{6}")
MASKED_RRN_RE = re.compile(r"(\d{6})\s*[-‐‑‒–—―−﹘﹣－]\s*([1-8])\s*[*＊●•○◦∙·xX×✱✳Ｘ]{1,7}")
NAME_RE = re.compile(r"[가-힣]{2,6}")


@dataclass
class Validation:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class PageHeader:
    page: int
    name: str | None = None
    name_words: list[Word] | None = None
    birth: date | None = None
    birth_words: list[Word] | None = None
    issue: date | None = None
    issue_words: list[Word] | None = None


def birth_from_rrn(text: str) -> date | None:
    """Reuse the established NHIS masked/full RRN century mapping."""
    value = re.sub(r"\s+", "", normalize_format_text(text))
    match = MASKED_RRN_RE.search(value) or RRN_RE.search(value)
    if match is None:
        return None
    yy, mm, dd = int(match[1][:2]), int(match[1][2:4]), int(match[1][4:6])
    century = 2000 if match[2] in "3478" else 1900
    try:
        return date(century + yy, mm, dd)
    except ValueError:
        return None


def parse_date(text: str) -> date | None:
    text = normalize_format_text(text)
    match = DATE_RE.search(text)
    if not match:
        match = COMPACT_DATE_RE.search(re.sub(r"\s+", "", text))
        if not match:
            return None
    try:
        return date(*(int(part) for part in match.groups()))
    except ValueError:
        return None


def dates_in_line(line: list[Word]) -> list[tuple[date, list[Word]]]:
    parts = []
    spans: list[tuple[int, int, Word]] = []
    cursor = 0
    for i, word in enumerate(line):
        if i:
            parts.append(" ")
            cursor += 1
        start = cursor
        parts.append(word.text)
        cursor += len(word.text)
        spans.append((start, cursor, word))
    text = normalize_format_text("".join(parts))
    compact_parts: list[str] = []
    compact_spans: list[tuple[int, int, Word]] = []
    compact_cursor = 0
    for word in line:
        value = re.sub(r"\s+", "", normalize_format_text(word.text))
        if value:
            compact_parts.append(value)
            compact_spans.append((compact_cursor, compact_cursor + len(value), word))
            compact_cursor += len(value)
    compact_text = "".join(compact_parts)
    matches = list(DATE_RE.finditer(text))
    matches.extend(COMPACT_DATE_RE.finditer(compact_text))
    found = []
    for match in matches:
        value = parse_date(match.group())
        if value is None:
            continue
        if match.re is COMPACT_DATE_RE:
            relevant = [word for start, end, word in compact_spans
                        if start < match.end() and end > match.start()]
        else:
            relevant = [word for start, end, word in spans if start < match.end() and end > match.start()]
        if not any(value == existing for existing, _ in found):
            found.append((value, relevant))
    return found


def page_lines(page: PageImage, result: OcrResult) -> list[list[Word]]:
    if not page.pixel_size:
        return []
    return group_lines(normalize(result.words, page.page, page.pixel_size))


def label_hits(lines: list[list[Word]], aliases: tuple[str, ...]) -> list[tuple[str, list[Word]]]:
    """Find label words in a line or vertically stacked lines sharing an x column."""
    hits: list[tuple[str, list[Word]]] = []
    for line in lines:
        flat = "".join(squash(word.text) for word in line)
        char_words = [word for word in line for _ in squash(word.text)]
        for alias in aliases:
            key = squash(alias)
            start = flat.find(key)
            if start >= 0:
                selected = []
                for word in char_words[start : start + len(key)]:
                    if all(word is not seen for seen in selected):
                        selected.append(word)
                hits.append((alias, selected))
    for gap in (1, 2):
        for index, first in enumerate(lines[:-gap]):
            second = lines[index + gap]
            if not first or not second:
                continue
            for upper in first:
                for lower in second:
                    if min(upper.x1, lower.x1) <= max(upper.x0, lower.x0):
                        continue
                    flat = squash(upper.text + lower.text)
                    for alias in aliases:
                        if squash(alias) == flat:
                            hits.append((alias, [upper, lower]))
    return hits


def header_for_page(page: PageImage, result: OcrResult) -> PageHeader:
    lines = page_lines(page, result)
    header = PageHeader(page.page)
    for index, line in enumerate(lines):
        text = line_text(line)
        flat = squash(text)
        if header.name is None and "성명" in flat:
            hits = label_hits([line], ("성명",))
            label_words = hits[0][1] if hits else []

            def candidate_name(word, *, label=False):
                raw = squash(re.sub(r"[()（）]", "", word.text))
                if label:
                    raw = raw.partition("성명")[2].lstrip(":：")
                if is_header_only_value(raw) or raw in {"주민등록", "확인청구자"}:
                    return None
                return raw if NAME_RE.fullmatch(raw) else None

            if label_words:
                x0, x1 = min(w.x0 for w in label_words), max(w.x1 for w in label_words)
                candidates = [(word, candidate_name(word, label=True)) for word in label_words]
                candidates += [(word, candidate_name(word)) for word in line if word.x0 >= x1]
                # An adjacent column header is not a value. If the header row
                # contains no name, inspect only nearby rows in the name column.
                if not any(value for _, value in candidates):
                    candidates = [(word, candidate_name(word))
                                  for below in lines[index + 1:index + 4]
                                  if below[0].cy - line[0].cy <= 6.0
                                  for word in below if word.x1 >= x0 and word.x0 <= x1]
                value = next(((word, value) for word, value in candidates if value), None)
                if value:
                    header.name_words, header.name = [value[0]], value[1]
        if header.birth is None and "주민등록번호" in flat:
            hits = label_hits([line], ("주민등록번호",))
            label_words = hits[0][1] if hits else []
            # OCR can put the label and number on different nearby lines, with
            # another header label between them. Keep the search tightly bound
            # to the label's immediate header neighborhood and require an RRN
            # shaped value, rather than scanning arbitrary page numbers.
            candidate_lines = [line]
            label_y = max((word.cy for word in label_words), default=line[0].cy)
            for following in lines[index + 1 : index + 4]:
                if following[0].cy - label_y > 6.0:
                    break
                candidate_lines.append(following)
            rrn = None
            rrn_words = []
            for start in range(len(candidate_lines)):
                for end in range(start + 1, min(len(candidate_lines), start + 3) + 1):
                    candidates = [word for row in candidate_lines[start:end] for word in row]
                    # The label line itself may include a value after the label;
                    # later lines are constrained by the small vertical window.
                    if start == 0 and label_words:
                        right = max(word.x1 for word in label_words)
                        inline = [word for word in candidates if word.x0 >= right]
                        if inline:
                            candidates = inline
                    rrn_text = re.sub(r"\s+", "", normalize_format_text(" ".join(w.text for w in candidates)))
                    match = MASKED_RRN_RE.search(rrn_text) or RRN_RE.search(rrn_text)
                    if match:
                        rrn, rrn_words = match, candidates
                        break
                if rrn:
                    break
            if rrn:
                header.birth = birth_from_rrn(rrn.group())
                if header.birth is not None:
                    header.birth_words = rrn_words or line
        elif header.birth is None and "생년월일" in flat:
            birth_match = DATE_RE.search(normalize_format_text(text))
            birth_words = [word for word in line if parse_date(word.text)]
            if not birth_match:
                birth_match = COMPACT_DATE_RE.search(re.sub(r"\s+", "", text))
                if birth_match:
                    birth_words = [word for word in line if parse_date(word.text)]
            if not birth_match:
                labels = ("생년월일",)
                hits = label_hits([line], labels)
                label_words = hits[0][1] if hits else []
                if label_words:
                    x0, x1 = min(w.x0 for w in label_words), max(w.x1 for w in label_words)
                    candidates = [w for w in line if w.x0 >= x1]
                    if not candidates:
                        candidates = [w for below in lines[index + 1 :] for w in below
                                      if w.x1 >= x0 and w.x0 <= x1]
                    birth_match = next((m for word in candidates if (m := DATE_RE.search(normalize_format_text(word.text))) or
                                        (m := COMPACT_DATE_RE.search(re.sub(r"\s+", "", word.text)))), None)
                    if birth_match:
                        birth_words = candidates
            if birth_match:
                header.birth = parse_date(birth_match.group())
                header.birth_words = birth_words or line
        if header.issue is None and any(label in flat for label in ("발급일", "발급일자", "발행일", "출력일")):
            header.issue = parse_date(text)
            if header.issue:
                header.issue_words = [word for word in line if parse_date(word.text)] or line
    return header


def page_headers(pages: list[tuple[PageImage, OcrResult]]) -> list[PageHeader]:
    headers = [header_for_page(page, result) for page, result in pages]
    if pages and not any(header.issue is not None for header in headers):
        issue, words, ambiguous = _closing_issue_date(*pages[-1])
        if issue is not None and not ambiguous:
            headers[-1].issue = issue
            headers[-1].issue_words = words
    return headers


def _closing_issue_date(page: PageImage, result: OcrResult) -> tuple[date | None, list[Word], bool]:
    """Read an unlabeled date only from the final confirmation/signatory block."""
    lines = page_lines(page, result)
    normalized = [squash(line_text(line)) for line in lines]
    confirmations = [i for i, text in enumerate(normalized) if "확인합니다" in text]
    issuers = [i for i, text in enumerate(normalized)
               if "국민건강보험공단" in text and "이사장" in text]
    if not confirmations or not issuers:
        return None, [], False
    confirmation = confirmations[-1]
    issuer = next((i for i in issuers if i > confirmation), None)
    if issuer is None:
        return None, [], False

    date_lines = []
    block_dates = []
    for index in range(confirmation + 1, min(issuer + 3, len(lines))):
        found = dates_in_line(lines[index])
        if not found:
            continue
        block_dates.extend(value for value, _ in found)
        if len(found) != 1:
            continue
        text = normalize_format_text(line_text(lines[index]))
        residue = re.sub(r"[\d\s년월일年月日./:\-‐‑‒–—―−﹘﹣－]", "", text)
        if not residue:
            date_lines.append((index, found[0][0], found[0][1]))
    # A lone date immediately before the issuing officer is the primary value.
    # Other dates in this same block (including a seal date) only corroborate it.
    primary = [item for item in date_lines if item[0] == issuer - 1]
    if len(primary) != 1:
        return None, [], False
    values = set(block_dates)
    if len(values) > 1:
        return None, [], True
    return primary[0][1], primary[0][2], False


def bbox(words: list[Word] | None, pages: dict[int, PageImage]) -> BBox | None:
    if not words:
        return None
    page = pages.get(words[0].page)
    if page is None:
        return None
    x0, y0 = min(w.px[0] for w in words), min(w.px[1] for w in words)
    x1, y1 = max(w.px[2] for w in words), max(w.px[3] for w in words)
    a, b = page.px_to_pt(x0, y0)
    c, d = page.px_to_pt(x1, y1)
    return BBox(page=page.page, x0=round(a, 1), y0=round(b, 1), x1=round(c, 1), y1=round(d, 1))


def make_field(value, raw: str, words: list[Word] | None, pages: dict[int, PageImage], confidence: float,
               sources: dict[int, FieldSource]) -> ExtractedField:
    page_no = words[0].page if words else None
    source = sources.get(page_no, FieldSource.OCR)
    return ExtractedField(value=value, raw_text=raw, confidence=confidence, source=source,
                          bbox=bbox(words, pages))


def sources_by_page(pages: list[tuple[PageImage, OcrResult]]) -> dict[int, FieldSource]:
    return {page.page: FieldSource.TEXT_LAYER if page.source == PageSource.TEXT_LAYER else FieldSource.OCR
            for page, _ in pages}


def consensus(headers: list[PageHeader], key: str) -> tuple[object | None, list[Word], bool]:
    available = [(getattr(header, key), getattr(header, f"{key}_words") or []) for header in headers
                 if getattr(header, key) is not None]
    if not available:
        return None, [], False
    value, _ = Counter(v for v, _ in available).most_common(1)[0]
    words = next(ws for v, ws in available if v == value)
    return value, words, len(available) == len(headers) and all(v == value for v, _ in available)


def confidence(checks: list[bool], consistent: bool = True) -> float:
    if not checks:
        return 0.5
    score = round(0.4 + 0.6 * sum(checks) / len(checks), 2)
    return min(0.6, score) if not consistent else score

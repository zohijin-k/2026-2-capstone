"""공통 단어·날짜·머리글 처리. 위치 판단은 페이지 대비 퍼센트 좌표를 쓴다."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import date

from ..pipeline.layout import Word, group_lines, line_text, normalize, squash
from ..pipeline.ocr import OcrResult
from ..pipeline.preprocess import PageImage, PageSource
from ..schemas.models import BBox, ExtractedField, FieldSource

DATE_RE = re.compile(r"(?<!\d)(\d{4})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})\s*일?(?!\d)")
COMPACT_DATE_RE = re.compile(r"(?<!\d)(20\d{2})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])(?!\d)")
RRN_RE = re.compile(r"(\d{6})\s*-\s*([1-8])\d{6}")
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


def parse_date(text: str) -> date | None:
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
    text = "".join(parts)
    matches = list(DATE_RE.finditer(text))
    matches.extend(COMPACT_DATE_RE.finditer(re.sub(r"\s+", "", text)))
    found = []
    for match in matches:
        value = parse_date(match.group())
        if value is None:
            continue
        if match.re is COMPACT_DATE_RE:
            relevant = line
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
            if label_words:
                x0, x1 = min(w.x0 for w in label_words), max(w.x1 for w in label_words)
                candidates = [w for w in line if w.x0 >= x1]
                if not candidates:
                    candidates = [w for below in lines[index + 1 :] for w in below
                                  if w.x1 >= x0 and w.x0 <= x1]
            else:
                candidates = line
            remainder = flat[flat.find("성명") + len("성명"):]
            inline = NAME_RE.search(re.sub(r"[()（）]", "", remainder))
            if inline and not candidates:
                candidates = line
            for word in candidates:
                raw = re.sub(r"[()（）]", "", word.text.strip())
                name = NAME_RE.fullmatch(raw)
                if not name and inline:
                    name = inline
                    word = next((w for w in line if w.x0 >= max((x.x1 for x in label_words), default=-1)), word)
                if name and name.group() not in {"성명", "주민등록"}:
                    header.name = name.group()
                    header.name_words = [word]
                    break
        if header.birth is None and ("생년월일" in flat or "주민등록번호" in flat):
            birth_match = DATE_RE.search(text)
            birth_words = [word for word in line if parse_date(word.text)]
            if not birth_match:
                birth_match = COMPACT_DATE_RE.search(re.sub(r"\s+", "", text))
                if birth_match:
                    birth_words = [word for word in line if parse_date(word.text)]
            if not birth_match:
                labels = ("생년월일", "주민등록번호")
                hits = label_hits([line], labels)
                label_words = hits[0][1] if hits else []
                if label_words:
                    x0, x1 = min(w.x0 for w in label_words), max(w.x1 for w in label_words)
                    candidates = [w for w in line if w.x0 >= x1]
                    if not candidates:
                        candidates = [w for below in lines[index + 1 :] for w in below
                                      if w.x1 >= x0 and w.x0 <= x1]
                    birth_match = next((m for word in candidates if (m := DATE_RE.search(word.text)) or
                                        (m := COMPACT_DATE_RE.search(re.sub(r"\s+", "", word.text)))), None)
                    if birth_match:
                        birth_words = candidates
            if birth_match:
                header.birth = parse_date(birth_match.group())
                header.birth_words = birth_words or line
            else:
                rrn = RRN_RE.search(text)
                if rrn:
                    yy, mm, dd = int(rrn.group(1)[:2]), int(rrn.group(1)[2:4]), int(rrn.group(1)[4:6])
                    gender = rrn.group(2)
                    century = 2000 if gender in "3478" else 1900
                    try:
                        header.birth = date(century + yy, mm, dd)
                        header.birth_words = [word for word in line if RRN_RE.search(word.text)] or line
                    except ValueError:
                        pass
        if header.issue is None and any(label in flat for label in ("발급일", "발급일자", "발행일", "출력일")):
            header.issue = parse_date(text)
            if header.issue:
                header.issue_words = [word for word in line if parse_date(word.text)] or line
    return header


def page_headers(pages: list[tuple[PageImage, OcrResult]]) -> list[PageHeader]:
    return [header_for_page(page, result) for page, result in pages]


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

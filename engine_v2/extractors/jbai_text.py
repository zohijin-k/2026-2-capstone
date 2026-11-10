"""전북AI의 bbox 없는 텍스트·OTSL 결과를 기존 문서 결과 계약으로 변환한다.

좌표는 추정 근거로 사용하지 않는다. 기존 추출 로직의 열 순서 처리를 재사용할
때만 임시 격자 좌표를 만들고, 반환 필드에서는 bbox를 비운다.
"""

from __future__ import annotations

import re
from datetime import date

from ..pipeline.jbai_ocr import JBAIDocumentResult, JBAIPageResult
from ..pipeline.ocr import OcrResult, OcrWord
from ..pipeline.preprocess import PageImage, PageSource
from ..schemas.models import DocType, FieldSource
from . import nhis_acquisition_loss, nhis_payment, resident_abstract

_PAGE_SIZE = (10000, 14000)
_TOKEN = re.compile(
    r"\d{4}\s*년\s*\d{1,2}\s*월\s*\d{1,2}\s*일|"
    r"\d{4}[./-]\d{1,2}[./-]\d{1,2}|\d{8}|\d{6}-[0-9*]{7}|[^\s|]+"
)
_MONTH = re.compile(r"^(?:20\d{2}[.\-/년 ]*)?(?:0?[1-9]|1[0-2])월$")
_MONEY = re.compile(r"^[-−]?\d[\d,]*원?$")


def _line_y(line: str, index: int, count: int, doc_type: DocType) -> float:
    flat = re.sub(r"\s+", "", line)
    if doc_type in {DocType.RESIDENT_ABSTRACT, DocType.RESIDENT_REGISTER}:
        if "문서확인번호" in flat or re.fullmatch(r"\d{1,2}/\d{1,2}", flat):
            return 3.0
        if "주민등록표" in flat or "초본" in flat or "등본" in flat:
            return 8.0
        if "발급일" in flat:
            return 12.8
        if "성명" in flat:
            return 17.7
        if "생년월일" in flat:
            return 19.3
        if "신청인" in flat:
            return 20.0
        if "번호" in flat and ("주소" in flat or "발생일" in flat or "신고일" in flat):
            return 28.0
        return min(75.0, 31.0 + index * 1.8)
    if "문서확인번호" in flat:
        return 3.0
    if "납부확인서" in flat or "자격득실확인서" in flat:
        return 8.0
    if "성명" in flat:
        return 12.0
    if "생년월일" in flat:
        return 15.0
    if "발급일" in flat:
        return 18.0
    if "사업장" in flat:
        return 20.0
    if "납부자번호" in flat:
        return 21.0
    if "확인합니다" in flat:
        return 89.0
    if "국민건강보험공단" in flat:
        return 96.0
    if re.search(r"20\d{2}.*년.*월.*일", line) and index:
        return 92.0
    if "조회기간" in flat or "대상기간" in flat or "납부내역" in flat:
        return 21.0
    return min(78.0, 8.0 + index * (65.0 / max(count, 1)))


def _put_word(out: list[OcrWord], text: str, x: float, y: float, width: float | None = None) -> None:
    w = width if width is not None else max(1.0, min(20.0, len(text) * 1.4))
    top = y * 140
    out.append(OcrWord(text, 0.85, (x * 100, top, min(9999.0, x * 100 + w * 100), top + 90)))


def _text_words(lines: list[str], doc_type: DocType, page: int) -> list[OcrWord]:
    result: list[OcrWord] = []
    for index, line in enumerate(lines):
        tokens = [token for token in _TOKEN.findall(line) if token not in {"|", "·", "•"}]
        if not tokens:
            continue
        total = sum(max(len(token), 1) for token in tokens) + max(len(tokens) - 1, 0) * 2
        cursor = 5.0
        available = 90.0
        y = _line_y(line, index, len(lines), doc_type)
        flat = re.sub(r"\s+", "", line)
        if doc_type in {DocType.RESIDENT_ABSTRACT, DocType.RESIDENT_REGISTER}:
            if flat.startswith("발급일"):
                _put_word(result, "발급일", 5.0, y)
                for token in tokens:
                    if "발급일" not in token:
                        _put_word(result, token, 58.0, y)
                continue
            if flat.startswith("성명"):
                _put_word(result, "성명", 5.0, y)
                for token in tokens:
                    if "성명" not in token:
                        _put_word(result, token, 23.0, y)
                continue
            if flat.startswith("생년월일"):
                _put_word(result, "생년월일", 5.0, y)
                for token in tokens:
                    if "생년월일" not in token:
                        _put_word(result, token, 65.0, y)
                continue
        for token in tokens:
            span = available * max(len(token), 1) / max(total, 1)
            _put_word(result, token, cursor, y, max(span * 0.85, 1.0))
            cursor += span + available * 2 / max(total, 1)
    return result


def _table_words(tables, page: int, y_offset: float, doc_type: DocType) -> list[OcrWord]:
    result: list[OcrWord] = []
    for table_index, table in enumerate(tables):
        if not table.rows:
            continue
        active: dict[int, tuple[int, int]] = {}
        placements: list[tuple[int, int, int, int, str]] = []
        max_col = 0
        for row_index, row in enumerate(table.rows):
            col = 0
            for cell_index, cell in enumerate(row):
                while active.get(col, (0, -1))[0] > row_index:
                    col += 1
                month_amount = None
                header_label = None
                if doc_type == DocType.NHIS_PAYMENT and cell_index == 0:
                    month_amount = re.match(r"((?:20\d{2}\s*[-./년 ]*)?(?:0?[1-9]|1[0-2])월)\s+([-−]?\d[\d,]*)", cell.text)
                    header_label = re.match(r"월별\s+(.+)", cell.text)
                if month_amount:
                    placements.append((row_index, col, 1, 1, month_amount.group(1)))
                    placements.append((row_index, col + 1, 1, 1, month_amount.group(2)))
                    col += 2
                    max_col = max(max_col, col)
                    continue
                if header_label:
                    placements.append((row_index, col, 1, 1, "월별"))
                    placements.append((row_index, col + 1, 1, 1, header_label.group(1)))
                    col += 2
                    max_col = max(max_col, col)
                    continue
                placements.append((row_index, col, cell.rowspan, cell.colspan, cell.text))
                for offset in range(cell.colspan):
                    active[col + offset] = (row_index + cell.rowspan, row_index)
                col += cell.colspan
            max_col = max(max_col, col, max(active, default=-1) + 1)
        max_col = max(max_col, 1)
        for row_index, col, rowspan, colspan, text in placements:
            if not text:
                continue
            if doc_type in {DocType.RESIDENT_ABSTRACT, DocType.RESIDENT_REGISTER} and max_col == 5:
                centers = [9.0, 30.0, 55.0, 67.0, 84.0]
                left = centers[min(col, 4)] - 3.0
                right = centers[min(col + colspan - 1, 4)] + 3.0
            elif doc_type == DocType.NHIS_ACQUISITION_LOSS and max_col == 4:
                centers = [12.0, 39.0, 62.0, 86.0]
                left = centers[min(col, 3)] - 3.0
                right = centers[min(col + colspan - 1, 3)] + 3.0
            elif doc_type == DocType.NHIS_PAYMENT:
                centers = [5.0 + 10.0 * index for index in range(max_col)]
                left = centers[min(col, max_col - 1)] - 4.0
                right = centers[min(col + colspan - 1, max_col - 1)] + 4.0
            else:
                left = 4.0 + 92.0 * col / max_col
                right = 4.0 + 92.0 * (col + colspan) / max_col
            cell_left = left
            cell_width = max(2.0, right - left)
            y = min(78.0, y_offset + table_index * 28.0 + row_index * 2.6)
            tokens = [token for token in _TOKEN.findall(text) if token not in {"|", "·", "•"}]
            total = sum(max(1, len(token)) for token in tokens) + max(len(tokens) - 1, 0)
            cursor = cell_left + cell_width * 0.08
            for token in tokens:
                width = cell_width * 0.82 * max(1, len(token)) / max(total, 1)
                _put_word(result, token, cursor, y, max(width * 0.9, 0.8))
                cursor += width + cell_width * 0.82 / max(total, 1)
    return result


def _relevant_tables(tables, doc_type: DocType):
    relevant = []
    for table in tables:
        rows = table.rows
        start = None
        for index, row in enumerate(rows):
            flat = "".join(re.sub(r"\s+", "", cell.text) for cell in row)
            if doc_type in {DocType.RESIDENT_ABSTRACT, DocType.RESIDENT_REGISTER}:
                is_header = ("주소" in flat and "신고일" in flat and
                             ("번호" in flat or "변호" in flat or "발생일" in flat or "발행일" in flat))
            elif doc_type == DocType.NHIS_PAYMENT:
                is_header = "월별" in flat and any(word in flat for word in
                                                    ("고지금액", "건강보험료", "건강", "장기요양"))
            else:
                is_header = ("자격취득일" in flat and
                             ("자격상실일" in flat or "상실일" in flat) and
                             ("가입자구분" in flat or "자격구분" in flat or
                              "사업장명칭" in flat or "사업장명" in flat))
            if is_header:
                start = max(0, index - (1 if doc_type == DocType.NHIS_PAYMENT else 0))
                break
        if start is not None:
            selected = list(rows[start:])
            if doc_type in {DocType.RESIDENT_ABSTRACT, DocType.RESIDENT_REGISTER}:
                # The synthetic replay surfaced a frequent OCR confusion in the first header cell.
                # Normalize only when the surrounding address-history headings identify the table.
                header_index = next((i for i, row in enumerate(selected)
                                     if "주소" in "".join(cell.text for cell in row)
                                     and "신고일" in "".join(cell.text for cell in row)), None)
                if header_index is not None:
                    header = list(selected[header_index])
                    if header and re.sub(r"\s+", "", header[0].text) == "변호":
                        header[0] = type(header[0])("번호", rowspan=header[0].rowspan,
                                                   colspan=header[0].colspan, header=header[0].header)
                        selected[header_index] = header
            if (doc_type == DocType.NHIS_PAYMENT and len(selected) > 1 and
                    any("고지금액" in cell.text for cell in selected[0]) and
                    any("월별" in cell.text for cell in selected[1])):
                selected[0] = [type(selected[0][0])("", header=True), *selected[0]]
            relevant.append(type(table)(rows=selected))
    return relevant


def _keep_text_line(line: str, doc_type: DocType) -> bool:
    flat = re.sub(r"\s+", "", line)
    if doc_type == DocType.NHIS_PAYMENT:
        labels = ("문서확인번호", "납부확인서", "가입자", "성명", "생년월일", "사업장명칭",
                  "사업장명", "발급일", "직장가입", "지역가입", "납부내역", "확인합니다", "국민건강보험공단")
        return any(label in flat for label in labels) or bool(
            re.search(r"20\d{2}년\s*0?[1-9]\d?월.*[~～-].*20\d{2}년\s*0?[1-9]\d?월", line)
        )
    if doc_type == DocType.NHIS_ACQUISITION_LOSS:
        labels = ("문서확인번호", "자격득실확인서", "성명", "생년월일", "발급일", "조회기간", "대상기간")
        return any(label in flat for label in labels) or bool(re.fullmatch(r"\d{1,2}/\d{1,2}", flat))
    if doc_type in {DocType.RESIDENT_ABSTRACT, DocType.RESIDENT_REGISTER}:
        labels = ("문서확인번호", "주민등록표", "초본", "등본", "발급일", "성명", "생년월일", "신청인",
                  "시장", "군수", "구청장")
        return any(label in flat for label in labels) or bool(re.fullmatch(r"\d{1,2}/\d{1,2}", flat))
    return True


def virtual_pages(document: JBAIDocumentResult, doc_type: DocType) -> list[tuple[PageImage, OcrResult]]:
    """기존 추출기의 표 열 처리에만 쓰는 임시 순서 격자를 만든다."""
    pages = []
    for page in document.pages:
        words = _text_words([line for line in page.text_lines if _keep_text_line(line, doc_type)],
                            doc_type, page.page)
        tables = _relevant_tables(page.tables, doc_type)
        words.extend(_table_words(tables, page.page, 31.0, doc_type))
        image = PageImage(page=page.page, source=PageSource.RENDER,
                          page_size_pt=(595.0, 842.0), pixel_size=_PAGE_SIZE)
        pages.append((image, OcrResult("jbai", words)))
    return pages


def extract(document: JBAIDocumentResult, doc_type: DocType, today: date | None = None):
    pages = virtual_pages(document, doc_type)
    extractor = {
        DocType.RESIDENT_ABSTRACT: resident_abstract.extract,
        DocType.RESIDENT_REGISTER: resident_abstract.extract,
        DocType.NHIS_PAYMENT: nhis_payment.extract,
        DocType.NHIS_ACQUISITION_LOSS: nhis_acquisition_loss.extract,
    }.get(doc_type)
    if extractor is None:
        raise ValueError(f"전북AI 텍스트 판독기가 지원하지 않는 서류 종류: {doc_type.value}")
    result = extractor(pages, today=today)
    for field in result.fields.values():
        field.source = FieldSource.VLM
        field.bbox = None
    return result

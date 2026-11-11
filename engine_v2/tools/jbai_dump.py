"""Print only a masked structural summary of a JBAI OCR response.

This tool deliberately never writes the source image or response to disk.
"""

from __future__ import annotations

import argparse
import os
import re
from collections import Counter
from pathlib import Path

from ..pipeline.jbai_ocr import run_jbai_file_pair


_LABELS = (
    "주민등록번호", "문서확인번호", "발급번호", "사업장관리번호", "사업장명칭",
    "생년월일", "변동사유", "발급일시", "발급일자", "발급일", "신청인",
    "성명", "주소", "발생일", "신고일", "전입", "세대주", "쪽",
    "국민연금", "건강보험", "고용보험", "산재보험", "사회보험", "가입내역",
    "확인서", "가입자", "사업장", "명칭", "관리번호", "구분", "자격",
    "취득일", "상실일", "미가입", "해당없음", "지역", "직장", "외국인",
    "등록번호", "현재", "기준", "공단", "고지금액", "납부금액",
)
_REGIONS = (
    "서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시", "대전광역시",
    "울산광역시", "세종특별자치시", "경기도", "강원특별자치도", "강원도", "충청북도",
    "충청남도", "전북특별자치도", "전라북도", "전라남도", "경상북도", "경상남도",
    "제주특별자치도", "제주도", "서울", "부산", "대구", "인천", "광주", "대전",
    "울산", "세종", "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
)
_PRESERVE = tuple(sorted(set(_LABELS + _REGIONS + ("주민번호",)), key=len, reverse=True))
_RRN = re.compile(r"(?<!\d)\d{6}\s*[-− ]\s*(?:\d|\*){7}(?![\d*])")
_TOKEN = re.compile("|".join(re.escape(token) for token in _PRESERVE))
_OTSL = re.compile(r"<(?:fcel|ecel|lcel|ucel|xcel|nl)>")


def mask_text(value: str) -> str:
    """Mask personal text while preserving known form labels and province names."""
    value = _RRN.sub("[주민번호]", value)
    out: list[str] = []
    cursor = 0
    for match in _TOKEN.finditer(value):
        out.append(_mask_chars(value[cursor:match.start()]))
        out.append(match.group())
        cursor = match.end()
    out.append(_mask_chars(value[cursor:]))
    return "".join(out)


def _mask_chars(value: str) -> str:
    chars = []
    for char in value:
        code = ord(char)
        if 0xAC00 <= code <= 0xD7A3 or 0x1100 <= code <= 0x11FF or 0x3130 <= code <= 0x318F:
            chars.append("가")
        elif char.isdigit():
            chars.append("9")
        elif char.isascii() and char.isalpha():
            chars.append("a")
        else:
            chars.append(char)
    return "".join(chars)


def _table_kind(page) -> str:
    content = page.table_content
    if re.search(r"<table\b", content, re.IGNORECASE):
        return "HTML"
    if _OTSL.search(content):
        return "OTSL"
    return "기타"


def _cell_kinds(page) -> Counter[str]:
    content = page.table_content
    if _table_kind(page) == "OTSL":
        found = Counter(token[1:-1] for token in _OTSL.findall(content))
        return found
    if _table_kind(page) == "HTML":
        return Counter({"셀": sum(len(row) for table in page.tables for row in table.rows),
                        "병합": sum(cell.rowspan > 1 or cell.colspan > 1
                                    for table in page.tables for row in table.rows for cell in row)})
    return Counter({"셀": sum(len(row) for table in page.tables for row in table.rows)})


def summarize(document) -> str:
    lines = [f"요청 수: {document.request_count}", f"전체 소요: {document.elapsed_sec:.2f}초"]
    for page in document.pages:
        lines.append(f"쪽 {page.page + 1}: OCR {page.ocr_elapsed_sec:.2f}초 / 표 {page.table_elapsed_sec:.2f}초, "
                     f"이미지 {page.image_size[0]}×{page.image_size[1]}px, JPEG {page.jpeg_bytes}바이트")
        lines.append(f"  OCR 줄 수: {len(page.text_lines)}")
        lines.extend(f"    {mask_text(line)}" for line in page.text_lines)
        kind = _table_kind(page)
        lines.append(f"  표 형식: {kind}, 표 개수: {len(page.tables)}")
        lines.append(f"  셀 종류: {dict(_cell_kinds(page))}")
        for index, table in enumerate(page.tables, 1):
            row_count = len(table.rows)
            col_count = max((sum(cell.colspan for cell in row) for row in table.rows), default=0)
            lines.append(f"  표 {index}: {row_count}행×{col_count}열")
            for row in table.rows[:3]:
                lines.append("    " + " | ".join(mask_text(cell.text) for cell in row))
        lines.append(f"  응답 앞 200자(가림): {mask_text((page.raw_content + page.table_content)[:200])}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="전북AI OCR 응답의 가린 구조 요약을 출력합니다.")
    parser.add_argument("file", type=Path)
    args = parser.parse_args()
    if os.environ.get("JBAI_ALLOW_REAL_DOCS", "").strip().lower() not in {"1", "true", "yes", "on"}:
        raise SystemExit("실제 서류 판독은 JBAI_ALLOW_REAL_DOCS=true일 때만 실행할 수 있습니다.")
    if not args.file.is_file():
        raise SystemExit("입력 파일을 찾을 수 없습니다.")
    try:
        document = run_jbai_file_pair(args.file)
    except Exception as error:  # Never echo potentially sensitive request or response details.
        raise SystemExit(f"전북AI 판독 실패: {type(error).__name__}") from None
    print(summarize(document))


if __name__ == "__main__":
    main()

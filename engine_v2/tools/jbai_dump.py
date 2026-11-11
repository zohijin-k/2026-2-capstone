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
_OTSL = re.compile(r"<(?:fcel|ecel|lcel|ucel|xcel|nl)>")
from .privacy import mask_text


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
        lines.append(f"  특수 토큰 제거 수: {page.special_token_count}, 환각 점수: {page.hallucination_score:.3f}")
        if page.unsupported_options:
            lines.append(f"  서버가 거부해 제거한 요청 옵션: {', '.join(page.unsupported_options)} (400)")
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

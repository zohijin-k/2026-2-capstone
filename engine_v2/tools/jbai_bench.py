"""Compare JBAI input variants using numeric-only output.

Example (run locally after loading .env):
  JBAI_ALLOW_REAL_DOCS=true python -m engine_v2.tools.jbai_bench <file.pdf> \
    --temperature-zero --gray-contrast --stripes 4 --dpi 300 --doc resident_abstract
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import time
from collections import Counter
from pathlib import Path

from ..pipeline import jbai_ocr
from ..pipeline.jbai_ocr import JBAIDocumentResult, JBAIPageResult


LABELS = ("문서확인번호", "성명", "주민등록번호", "발생일", "신고일", "전입")
REQUESTS_PER_IMAGE = 2
OVERLAP_FRACTION = 0.10
MAX_CONFIRMED_REQUESTS = 100


def _jpeg_bands(data: bytes, count: int, overlap: float = OVERLAP_FRACTION) -> list[tuple[bytes, tuple[int, int]]]:
    from PIL import Image

    with Image.open(io.BytesIO(data)) as original:
        image = original.convert("RGB")
        width, height = image.size
        bands = []
        band_height = height / count
        extra = int(height * overlap)
        for index in range(count):
            top = max(0, int(index * band_height) - extra)
            bottom = min(height, int((index + 1) * band_height) + extra)
            encoded = jbai_ocr._encode_jpeg(image.crop((0, top, width, bottom)))
            bands.append((encoded, (width, bottom - top)))
        return bands


def _merge_stripes(parts: list[JBAIPageResult], page_index: int,
                   original_size: tuple[int, int]) -> JBAIPageResult:
    text_lines = []
    for part in parts:
        for line in part.text_lines:
            if not text_lines or text_lines[-1] != line:
                text_lines.append(line)
    tables = [table for part in parts for table in part.tables]
    table_content = "\n".join(part.table_content for part in parts)
    assessment = __import__("engine_v2.pipeline.jbai_quality", fromlist=["assess_page"]).assess_page(
        text_lines, table_content, original_size)
    return JBAIPageResult(
        page=page_index, text_lines=text_lines, tables=tables,
        elapsed_sec=sum(part.elapsed_sec for part in parts),
        raw_content="\n".join(part.raw_content for part in parts), table_content=table_content,
        ocr_elapsed_sec=sum(part.ocr_elapsed_sec for part in parts),
        table_elapsed_sec=sum(part.table_elapsed_sec for part in parts),
        image_size=original_size, jpeg_bytes=sum(part.jpeg_bytes for part in parts),
        request_count=sum(part.request_count for part in parts),
        special_token_count=sum(part.special_token_count for part in parts),
        unsupported_options=tuple(dict.fromkeys(option for part in parts for option in part.unsupported_options)),
        hallucination_score=assessment.score,
        hangul_ratio=assessment.hangul_ratio,
        non_local_script_ratio=assessment.non_local_script_ratio,
        repeated_line_ratio=assessment.repeated_line_ratio,
        repeated_phrase_ratio=assessment.repeated_phrase_ratio,
        characters_per_megapixel=assessment.characters_per_megapixel,
        hallucination_reasons=assessment.reasons,
    )


def run_variant(rendered_pages, *, source_path: Path | None = None, stripe_count: int = 1,
                temperature: float | None = 0.0, max_tokens: int | None = None) -> JBAIDocumentResult:
    started = time.monotonic()
    pages = []
    for page_index, image, size in rendered_pages:
        inputs = [(image, size)] if stripe_count == 1 else _jpeg_bands(image, stripe_count)
        parts = [jbai_ocr.run_jbai_image_pair(
            data, part_size, page=page_index, source_path=source_path,
            temperature=temperature, max_tokens=max_tokens,
        ) for data, part_size in inputs]
        pages.append(_merge_stripes(parts, page_index, size) if stripe_count > 1 else parts[0])
    return JBAIDocumentResult(pages, time.monotonic() - started,
                              request_count_override=sum(page.request_count for page in pages))


def _label_counts(page: JBAIPageResult) -> dict[str, int]:
    text = "\n".join(page.text_lines) + "\n" + page.table_content
    return {label: len(re.findall(re.escape(label), text)) for label in LABELS}


def _print_document(name: str, result: JBAIDocumentResult) -> None:
    print(f"[{name}] 요청 {result.request_count}회 / 전체 {result.elapsed_sec:.2f}초")
    for page in result.pages:
        print(f"  쪽 {page.page + 1}: {page.elapsed_sec:.2f}초, 줄 {len(page.text_lines)}, "
              f"한글 비율 {page.hangul_ratio:.3f}, 비한글 비율 {page.non_local_script_ratio:.3f}, "
              f"특수 토큰 {page.special_token_count}")
        print("    라벨: " + ", ".join(f"{label} {count}" for label, count in _label_counts(page).items()))
        print(f"    표 {len(page.tables)}개: " + ", ".join(
            f"{len(table.rows)}×{max((sum(cell.colspan for cell in row) for row in table.rows), default=0)}"
            for table in page.tables))
        print(f"    환각 점수 {page.hallucination_score:.3f}")
        if page.unsupported_options:
            print(f"    서버가 거부해 제거한 요청 옵션: {', '.join(page.unsupported_options)} (HTTP 400 응답 기준)")


def _compare_gt(result: JBAIDocumentResult, doc: str, gt_path: Path) -> None:
    from ..extractors.jbai_text import extract
    from ..schemas.models import DocType
    from .extract_check import _expected

    doc_type = {
        "resident_abstract": DocType.RESIDENT_ABSTRACT,
        "nhis_payment": DocType.NHIS_PAYMENT,
        "nhis_acquisition_loss": DocType.NHIS_ACQUISITION_LOSS,
    }[doc]
    gt = json.loads(gt_path.read_text(encoding="utf-8"))
    output = extract(result, doc_type)
    if doc == "resident_abstract":
        pairs = (("name", "name"), ("birth_date", "birth_date"), ("issue_date", "issue_date"))
        matches = []
        for key, source in pairs:
            if source in gt:
                value = output.fields.get(key)
                expected = gt[source]
                actual = value.value.isoformat() if value and hasattr(value.value, "isoformat") else (
                    str(value.value) if value else None)
                matches.append((key, actual == expected.replace(" ", "")))
        if gt.get("address_contains"):
            field = output.fields.get("current_address")
            actual_address = re.sub(r"\s+", "", str(field.value)) if field else ""
            matches.append(("current_address", all(
                re.sub(r"\s+", "", part) in actual_address for part in gt["address_contains"])))
        print("  GT 필드 O/X: " + ", ".join(f"{key} {'O' if ok else 'X'}" for key, ok in matches))
        print(f"  이력 건수: {len(output.history)}")
        expected_dates = gt.get("move_in_dates", [])
        found_dates = {value for entry in output.history for value in (entry.occurred, entry.reported) if value}
        if expected_dates:
            matches_dates = [value in found_dates for value in expected_dates]
            print(f"  정답 이력 날짜 O/X: {sum(matches_dates)}/{len(matches_dates)}")
        return
    expected = _expected(doc, gt)
    matches = []
    for key, wanted in expected.items():
        field = output.fields.get(key)
        actual = str(field.value) if field else None
        matches.append((key, actual == wanted))
    print("  GT 필드 O/X: " + ", ".join(f"{key} {'O' if ok else 'X'}" for key, ok in matches))
    if doc == "nhis_acquisition_loss":
        data = output.fields.get("자격이력자료")
        try:
            history_count = len(json.loads(data.value).get("rows", [])) if data else 0
        except (ValueError, TypeError):
            history_count = 0
        print(f"  이력 건수: {history_count}")


def _page_count(path: Path) -> int:
    if path.suffix.lower() == ".pdf":
        import pymupdf
        with pymupdf.open(path) as document:
            return document.page_count
    return 1


def main() -> None:
    parser = argparse.ArgumentParser(description="전북AI 입력 방식 비교 (값은 출력하지 않습니다)")
    parser.add_argument("file", type=Path)
    parser.add_argument("--temperature-zero", action="store_true")
    parser.add_argument("--gray-contrast", action="store_true")
    parser.add_argument("--stripes", type=int, metavar="N", help="가로 띠 수, 각 경계 10%% 겹침")
    parser.add_argument("--dpi", type=int, choices=range(200, 601), metavar="DPI")
    parser.add_argument("--doc", choices=("resident_abstract", "nhis_payment", "nhis_acquisition_loss"),
                        default="resident_abstract")
    parser.add_argument("--gt", type=Path)
    parser.add_argument("--yes", action="store_true", help="예상 요청이 100회를 넘을 때 확인을 건너뜀")
    args = parser.parse_args()

    if os.environ.get("JBAI_ALLOW_REAL_DOCS", "").strip().lower() not in {"1", "true", "yes", "on"}:
        raise SystemExit("실제 서류 비교는 JBAI_ALLOW_REAL_DOCS=true일 때만 실행할 수 있습니다.")
    if not os.environ.get("JBAI_API_KEY", "").strip():
        raise SystemExit("JBAI_API_KEY가 설정되지 않았습니다.")
    if not args.file.is_file():
        raise SystemExit("입력 파일을 찾을 수 없습니다.")
    if args.stripes is not None and not 2 <= args.stripes <= 8:
        raise SystemExit("--stripes는 2~8이어야 합니다.")
    if args.gt and not args.gt.is_file():
        raise SystemExit("정답 파일을 찾을 수 없습니다.")

    page_count = _page_count(args.file)
    baseline_requests = page_count * REQUESTS_PER_IMAGE
    selected = any((args.temperature_zero, args.gray_contrast, args.stripes, args.dpi))
    variant_images = page_count * (args.stripes or 1) * REQUESTS_PER_IMAGE if selected else 0
    expected_calls = baseline_requests + variant_images
    print(f"예상 요청 수: {expected_calls}회 (기준 {baseline_requests} + 선택 조합 {variant_images})")
    if expected_calls > MAX_CONFIRMED_REQUESTS and not args.yes:
        raise SystemExit("예상 요청이 100회를 넘습니다. 검토 후 --yes를 붙여 다시 실행하세요.")

    base_render = jbai_ocr.render_pdf_pages_200dpi(args.file)
    baseline = run_variant(base_render, source_path=args.file, temperature=None, max_tokens=0)
    _print_document("기준 · 200dpi 전체 쪽", baseline)
    if args.gt:
        _compare_gt(baseline, args.doc, args.gt)

    if selected:
        dpi = args.dpi or jbai_ocr.RENDER_DPI
        tuned_render = jbai_ocr.render_pdf_pages_200dpi(args.file, dpi=dpi,
                                                        grayscale_contrast=args.gray_contrast)
        tuned = run_variant(tuned_render, source_path=args.file,
                            stripe_count=args.stripes or 1,
                            temperature=0.0 if args.temperature_zero else None,
                            max_tokens=None)
        labels = []
        if args.temperature_zero:
            labels.append("temperature 0")
        if args.gray_contrast:
            labels.append("회색조·대비")
        if args.stripes:
            labels.append(f"가로 {args.stripes}등분")
        if args.dpi:
            labels.append(f"{args.dpi}dpi")
        _print_document("선택 조합 · " + ", ".join(labels), tuned)
        if args.gt:
            _compare_gt(tuned, args.doc, args.gt)


if __name__ == "__main__":
    main()

"""Original bitmap size and independently readable page markers, without type guesses."""
import json
import math
from pathlib import Path
import re


# Narrow provisional product boundary, documented in task design (not an OCR limit).
MIN_SHORT_EDGE = 600
MIN_LONG_EDGE = 800


def _dominant_image(page):
    import pymupdf

    images = [image for image in page.get_image_info() if
              pymupdf.Rect(image["bbox"]).get_area() >= .9 * page.rect.get_area()]
    return max(images, key=lambda item: item["width"] * item["height"]) if images else None


def original_image_sizes(file_path: str) -> list[dict[str, int]]:
    path = Path(file_path)
    try:
        if path.suffix.lower() in {".png", ".jpg", ".jpeg"}:
            from PIL import Image
            with Image.open(path) as image:
                width, height = image.size
            return [{"page": 0, "width": width, "height": height}]
        if path.suffix.lower() == ".pdf":
            import pymupdf
            from engine_v2.pipeline.preprocess import TEXT_LAYER_MIN_CHARS
            sizes = []
            with pymupdf.open(path) as doc:
                if doc.needs_pass:
                    return []
                for index, page in enumerate(doc):
                    if len(page.get_text().strip()) >= TEXT_LAYER_MIN_CHARS:
                        continue  # A scalable text-layer page is not limited by its background bitmap.
                    # Only a dominant source bitmap, never a rendered/upscaled page.
                    image = _dominant_image(page)
                    if image is not None:
                        sizes.append({"page": index, "width": image["width"], "height": image["height"]})
            return sizes
    except (OSError, ValueError, RuntimeError):
        pass  # Reading/format failures retain the existing unreadable-file path.
    return []


def objective_image_quality(file_path: str, *, excluded_pages=()) -> float:
    """Original resolution proxy only; OCR success, blur and brightness are unused.

    Keep the established raw-image pixel and embedded-PDF DPI score bands.
    Scalable text and unmeasured sources are neutral, never inferred poor quality.
    """
    path = Path(file_path)
    if path.suffix.lower() in {".png", ".jpg", ".jpeg"}:
        sizes = original_image_sizes(file_path)
        if not sizes:
            return 1.0
        short = min(sizes[0]["width"], sizes[0]["height"])
        return .9 if short >= 1400 else .75 if short >= 1000 else .55 if short >= 700 else .35
    if path.suffix.lower() != ".pdf":
        return 1.0
    try:
        import pymupdf
        from engine_v2.pipeline.preprocess import TEXT_LAYER_MIN_CHARS

        scores = []
        with pymupdf.open(path) as doc:
            if doc.needs_pass:
                return 1.0  # The reader retains its separate unreadable-file evidence.
            for index, page in enumerate(doc, 1):
                if index in excluded_pages:
                    continue
                if len(page.get_text().strip()) >= TEXT_LAYER_MIN_CHARS:
                    scores.append(1.0)
                    continue
                image = _dominant_image(page)
                if image is None:
                    scores.append(1.0)  # Rendering cannot establish original resolution.
                    continue
                # The original pixel-width axis can be rotated in the PDF.
                # Its transform vector, rather than the enclosing box width,
                # preserves the same physical DPI for rotated scans.
                width_pt = math.hypot(*image["transform"][:2])
                if width_pt <= 0:
                    scores.append(1.0)
                    continue
                dpi = image["width"] / (width_pt / 72)
                scores.append(.9 if dpi >= 200 else .7 if dpi >= 150 else .5)
        return min(scores, default=1.0)
    except (OSError, ValueError, RuntimeError):
        return 1.0


def normalize_image_quality(result, file_path):
    """Measure the same original pages as the established bounded form reader."""
    if result.is_encrypted or result.tier == "fixture":
        return result
    from ..rules.doc_types import DocType

    excluded = []
    if result.detected_doc_type in {DocType.INSURANCE_4, DocType.NHIS_PAYMENT,
                                    DocType.NHIS_ACQUISITION_LOSS, DocType.NHIS_QUALIFICATION}:
        try:
            pages = json.loads(result.fields.get("추가첨부쪽", "[]"))
            count = result.page_count
            if (isinstance(pages, list) and type(count) is int and
                    all(type(value) is int and 1 <= value <= count for value in pages) and
                    len(set(pages)) == len(pages) < count):
                excluded = pages
        except (ValueError, TypeError):
            pass
    result.image_quality = objective_image_quality(file_path, excluded_pages=excluded)
    return result


def attach_file_evidence(result, file_path):
    if not result.is_encrypted and result.tier != "fixture":
        sizes = original_image_sizes(file_path)
        if sizes:
            result.fields["원본이미지크기"] = json.dumps(sizes, separators=(",", ":"))
    return result


def independent_page_markers(pages):
    from engine_v2.extractors.nhis_common import page_lines
    from engine_v2.pipeline.layout import squash

    markers, confidences = [], []
    for page, result in pages:
        candidates = []
        # Top-right folio region; an arbitrary body fraction is not a page marker.
        for row in page_lines(page, result):
            selected = [w for w in row if w.x0 >= 70 and w.cy < 10]
            text = squash("".join(w.text for w in selected))
            match = re.fullmatch(r"([0-9]{1,2})[/／]([0-9]{1,2})", text)
            if match and 1 <= int(match[1]) <= int(match[2]):
                candidates.append(([int(match[1]), int(match[2])], min(w.conf for w in selected)))
        if len(candidates) != 1:
            return None
        marker, confidence = candidates[0]
        markers.append(marker)
        confidences.append(confidence)
    return {"markers": markers, "confidence": min(confidences)} if markers else None


def resolution_defect(ocr) -> dict[str, int] | None:
    from ..rules.doc_types import DocType
    try:
        sizes = json.loads(ocr.fields.get("원본이미지크기", "[]"))
        identity_forms = {DocType.RESIDENT_ABSTRACT, DocType.RESIDENT_CERTIFICATE,
                          DocType.INSURANCE_4, DocType.DAILY_WORK_RECORD,
                          DocType.NHIS_PAYMENT, DocType.NHIS_QUALIFICATION,
                          DocType.NHIS_ACQUISITION_LOSS, DocType.BIZ_REG_PROOF}
        essential_fields = ("성명", "생년월일", "발급일") if ocr.detected_doc_type in identity_forms else {
            DocType.PAYMENT_RECEIPT: ("결제금액", "결제일"),
            DocType.EXAM_CONFIRMATION: ("성명", "응시일"),
            DocType.EXAM_TRANSCRIPT: ("성명", "응시일"),
            DocType.INTERVIEW_CONFIRMATION: ("성명", "면접일", "회사명"),
        }.get(ocr.detected_doc_type, ())
        readable = sum(bool(ocr.fields.get(key) or key == "발급일" and ocr.issue_date)
                       for key in essential_fields)
        unreadable = (ocr.detected_doc_type is None or
                      bool(essential_fields) and readable * 2 < len(essential_fields))
        if not unreadable:
            return None
        for size in sizes:
            width, height = size["width"], size["height"]
            if type(width) is int and type(height) is int and 0 < min(width, height) < MIN_SHORT_EDGE and max(width, height) < MIN_LONG_EDGE:
                return size
    except (ValueError, TypeError, KeyError):
        pass
    return None

"""Authored fictitious daily records with the observed four-page word bands."""
from engine_v2.pipeline.ocr import OcrWord
from engine_v2.tests import fail_case_samples as base


def daily_short_birth(*, two_digit=True):
    """Preserve layout/labels, with wholly fictitious identity and work values."""
    pages = base.daily(months=("2025-01", "2025-02", "2025-03", "2025-04", "2025-05",
                               "2025-06", "2025-10", "2025-12", "2026-02"))
    for page, result in pages:
        if page.page % 2:
            for word in result.words:
                if "확인합니다" in word.text:
                    word.bbox_px = (220, 162, 375, 174)
                elif "2026년" in word.text:
                    word.bbox_px = (255, 191, 340, 202)
                elif word.text == "근로복지공단이사장":
                    word.bbox_px = (226, 237, 368, 255)
            continue
        for word in result.words:
            if word.text.startswith("일용근로·"):
                word.bbox_px = (112, 68, 483, 89)
            elif word.text == "발급일자":
                word.bbox_px = (234, 105, 271, 117)
            elif word.text == "2026년03월03일":
                word.bbox_px = (292, 105, 370, 117)
            elif word.text == "성명":
                word.bbox_px = (122, 134, 143, 145)
            elif word.text == base.NAME:
                word.bbox_px = (224, 134, 252, 145)
            elif word.text == "생년월일":
                word.bbox_px = (331, 134, 369, 145)
            elif word.text == "1990년01월01일":
                word.text = "90년01월01일" if two_digit else word.text
                word.bbox_px = (432, 134, 504, 145)
            elif word.text == "조회기간":
                word.bbox_px = (55, 168, 93, 180)
            elif word.text == "2025년09월~":
                word.text = "2025년01월~"
            elif word.text == "2026년03월":
                word.bbox_px = (337, 158, 397, 170)
        result.words.extend([
            OcrWord("접수번호", 1, (390, 105, 428, 117)),
            OcrWord("0000-0000-F00000F", 1, (445, 105, 542, 117)),
            OcrWord("(합성시험용 가짜 안내문 0번)", 1, (219, 177, 441, 189)),
        ])
    return pages

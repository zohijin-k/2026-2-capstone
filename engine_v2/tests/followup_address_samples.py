"""Authored fictitious labels/addresses in the observed sparse header geometry."""
from engine_v2.pipeline.ocr import OcrWord
from engine_v2.tests import fail_case_samples as sample


def sparse_dates(*, rows=3, digit=False, headers=True):
    pages = sample.missing_address_dates()
    page, result = pages[0]
    # Widely justified address glyphs are not a reliable joined legacy label.
    result.words = [w for w in result.words if w.text not in {"주소", "신 고 일"}]
    result.words += [OcrWord("주", .95, (236,429,259,452)),
                     OcrWord("소", .95, (376,431,399,451)),
                     OcrWord("9ㄱ 신 고 일", .71, (607,417,745,443)),
                     OcrWord("가짜 주석 0000.00.00.", .94, (124,628,519,648)),
                     OcrWord("=이하여백=", .94, (423,804,545,826))]
    if not headers:
        result.words = [w for w in result.words if "생일" not in w.text.replace(" ", "")
                        and "신고일" not in w.text.replace(" ", "")]
    for w in result.words:
        if "전북특별자치도" in w.text:
            w.text = "가짜시 가짜구 가짜로 0"
    if rows < 3:
        result.words = [w for w in result.words if not (510 < w.bbox_px[1] < 620)]
    if digit:
        result.words.append(OcrWord("0", .2, (550,475,564,495)))
    page.dpi = 100  # Deliberately low quality; independent geometry is unchanged.
    return pages

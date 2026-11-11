"""CPU own OCR on authored synthetic images from the existing D renderer."""
from datetime import date
import importlib.util
import io

import pytest

from engine_v2.extractors import insurance_4, resident_abstract
from engine_v2.pipeline.ocr import run_ocr
from engine_v2.pipeline.preprocess import PageImage, PageSource
from engine_v2.tools.extract_diag import synthetic_cases, diagnose_safe_issue
from engine_v2.tools.fetch_own_models import ASSETS, MODEL_DIR
from engine_v2.tools.fetch_synth_fonts import font_path
from engine_v2.tools.make_synth_eval import render
from engine_v2.tools.synth_bench import field_matches


def _available():
    if not all((MODEL_DIR / name).is_file() for name in ASSETS):
        pytest.skip("own models absent; run .venv/bin/python engine_v2/tools/fetch_own_models.py")
    if importlib.util.find_spec("onnxruntime") is None:
        pytest.skip("onnxruntime not installed")
    try:
        return font_path("nanummyeongjo")
    except ValueError:
        pytest.skip("synthetic font absent; run .venv/bin/python -m engine_v2.tools.fetch_synth_fonts")


def _ocr(image):
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    page = PageImage(0, PageSource.UPLOAD, (595, 842), png=buf.getvalue(), pixel_size=image.size, dpi=300)
    result = run_ocr("own", page.png, image.size)
    assert result.error is None, "Own OCR failed on synthetic image"
    return [(page, result)]


def insurance_image(*, empty=False):
    """Entirely fictional certificate header; truth is independent of OCR."""
    from PIL import ImageDraw, ImageFont
    font = _available()
    cells = [(15, 13, "4대 사회보험"), (14, 16, "가입자 가입내역 확인서"),
             (10, 21, "발급번호"), (30, 21, "98765432109876"),
             (58, 21, "발급일시"), (10, 25, "주민(외국인)등록번호"),
             (34, 25, "990101-1******"), (60, 25, "성명"), (80, 25, "가상시험"),
             (10, 75, "합성 평가 전용 가짜 서류")]
    if not empty:
        cells.append((74, 21, "2026–11–10 10:20"))
    image = render(cells, font)
    draw = ImageDraw.Draw(image)
    # Bigger than the header's 300 dpi 10pt text, and closer than the title.
    stamp_font = ImageFont.truetype(str(font), 65)
    draw.text((40, 555), "2026/11/09", font=stamp_font, fill="black")
    draw.text((40, 630), "09:30:12 KST", font=stamp_font, fill="black")
    return image


@pytest.mark.parametrize("empty", (False, True))
def test_own_insurance_stamp_and_right_cell(empty):
    pairs = _ocr(insurance_image(empty=empty))
    diagnostic = diagnose_safe_issue(pairs)
    assert diagnostic["issue_label_found"]
    assert diagnostic["stamp_date_candidate_present"]
    assert diagnostic["right_cell_present"] == (not empty)
    assert diagnostic["selected_via_label"] == (not empty)
    result = insurance_4.extract(pairs, today=date(2026, 11, 11))
    if empty:
        assert "발급일" not in result.fields
        assert not next(v for v in result.validations if v.name == "발급일_consistent").passed
    else:
        assert result.fields["발급일"].value == date(2026, 11, 10)


def test_own_four_myeongjo_conditions_recover_all_fields():
    _available()
    measured = {}
    for case in synthetic_cases():
        if case["font"] != "nanummyeongjo" or case["document"] != "resident_abstract":
            continue
        if case["degradation"] not in ("clean", "scan300", "blur", "rotate"):
            break
        result = resident_abstract.extract(_ocr(case["image"]), today=date(2026, 11, 11))
        matches = field_matches(result, case["truth"])
        measured[case["degradation"]] = sum(matches.values())
    assert measured == {"clean": 4, "scan300": 4, "blur": 4, "rotate": 4}

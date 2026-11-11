"""Model-free metric and synthetic truth tests."""
from datetime import date

import numpy as np
from PIL import Image

from engine_v2.pipeline.ocr import OcrResult, OcrWord
from engine_v2.pipeline.preprocess import PageImage, PageSource
from engine_v2.tools.make_synth_eval import documents, degrade
from engine_v2.tools.synth_bench import alignment, calibration, cer, field_matches, EXTRACTORS


def test_cer_nfc_whitespace_and_edits():
    assert cer("가 나\n다", "가나다") == 0
    assert cer("가나다", "가라다") == 1/3
    assert cer("가", "가나다") == 2
    assert cer("", "") == 0
    assert cer("", "가") == 1
    assert alignment("가나", "가다")[1] == [True, False]


def test_calibration_aligns_repeated_characters_not_membership():
    bins = calibration("가나", [OcrWord("가가", .95, (0,0,20,10))])
    assert bins[-1]["count"] == 2
    assert bins[-1]["accuracy"] == .5
    assert bins[0]["accuracy"] is None


def test_degradation_seed_reproducible():
    base = Image.new("RGB", (50,70), "white")
    a = degrade(base, "noise", np.random.default_rng(12))
    b = degrade(base, "noise", np.random.default_rng(12))
    assert a.tobytes() == b.tobytes()
    assert a.tobytes() != base.tobytes()


def test_authored_fields_match_existing_extractors_on_perfect_ocr():
    for kind, cells, truth in documents():
        words = [OcrWord(t, 1, (x*24.8, (y-1)*35.08, (x+len(t)*1.3)*24.8, y*35.08)) for x,y,t in cells]
        page = PageImage(0, PageSource.UPLOAD, (595,842), pixel_size=(2480,3508))
        result = EXTRACTORS[kind]([(page, OcrResult("perfect", words))], today=date(2026,11,11))
        matches = field_matches(result, truth)
        assert all(matches.values()), (kind, matches, {k:v.value for k,v in result.fields.items()})


import pytest


@pytest.mark.parametrize("kind", ["resident_abstract", "nhis_payment"])
def test_own_synthetic_extractor_integration(kind):
    import io
    import importlib.util
    from engine_v2.tools.fetch_own_models import MODEL_DIR, ASSETS
    if not all((MODEL_DIR / name).is_file() for name in ASSETS):
        pytest.skip("own models absent; run engine_v2/tools/fetch_own_models.py")
    if importlib.util.find_spec("onnxruntime") is None:
        pytest.skip("onnxruntime is not installed")
    from engine_v2.tools.make_synth_eval import render
    from engine_v2.pipeline.ocr import run_ocr
    _, cells, truth = next(item for item in documents() if item[0] == kind)
    image = render(cells)
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    page = PageImage(0, PageSource.UPLOAD, (595,842), png=buf.getvalue(), pixel_size=image.size, dpi=300)
    result = run_ocr("own", page.png, image.size)
    assert result.error is None, result.error
    extracted = EXTRACTORS[kind]([(page, result)], today=date(2026,11,11))
    assert all(field_matches(extracted, truth).values())

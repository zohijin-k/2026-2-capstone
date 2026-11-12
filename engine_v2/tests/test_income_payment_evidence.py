"""Fictitious workplace cells establish B without confusing absent and blank."""
import pytest

from engine_v2.extractors import nhis_payment
from engine_v2.tests import p2_payment_samples as sample


@pytest.mark.parametrize("workplace,state", [("", "확실한 공란"), ("가상 OIl 사업장", "값 있음"),
                                             ("???", "못 읽음")])
@pytest.mark.parametrize("scale,jitter,skew", [(1, 0, 0), (1.7, 3, 12)])
def test_workplace_evidence_preserves_original_text_and_ocr_geometry(workplace, state, scale, jitter, skew):
    cells, size = sample.payment(workplace=workplace)
    result = nhis_payment.extract([sample.page(cells, size=size, scale=scale, jitter=jitter, skew=skew)])
    assert result.structure_complete
    assert result.fields["사업장명칭"].value == workplace
    assert result.fields["사업장명칭_상태"].value == state
    assert result.fields["사업장명칭_상태"].bbox is not None
    assert all(field.confidence >= .85 for field in result.fields.values())
    assert "가입구분" not in result.fields


@pytest.mark.parametrize("defect", ["missing-label", "duplicate-label", "crossing", "partial-height",
                                    "low-confidence", "header-only", "incomplete"])
def test_unreadable_workplace_never_establishes_regional_evidence(defect):
    cells, size = sample.payment()
    if defect == "missing-label":
        cells = [cell for cell in cells if cell[4] != "사업장명칭"]
    elif defect == "duplicate-label":
        cells.append(sample.cell(167, 350, 344, 400, "사업장명칭", 1))
    elif defect == "incomplete":
        cells = [(*cell[:4], "165,001", cell[5]) if cell[0] == 738 else cell for cell in cells]
    else:
        x0, y0, x1, y1 = (330, 587, 800, 638) if defect == "crossing" else (650, 587, 930, 638)
        if defect == "partial-height":
            y0, y1 = 646, 690
        cells.append(sample.cell(x0, y0, x1, y1, "사업장명칭" if defect == "header-only" else "가상사업장",
                                 .4 if defect == "low-confidence" else 1))
    result = nhis_payment.extract([sample.page(cells, size=size)])
    assert result.fields["사업장명칭_상태"].value == "못 읽음"
    if defect == "low-confidence":
        assert result.structure_complete  # income-specific uncertainty keeps old document behavior
        assert all(field.confidence >= .85 for field in result.fields.values())


@pytest.mark.parametrize("explicit", ["직장가입자", "지역가입자"])
def test_legacy_payment_printed_category_is_preserved(explicit):
    from engine_v2.tests.test_nhis_extractors import payment_pages

    pages = payment_pages()
    for word in pages[0][1].words:
        if word.text == "직장가입자":
            word.text = explicit
    result = nhis_payment.extract(pages)
    assert result.form_kind is None
    assert result.fields["가입구분"].value == explicit[:2]
    assert "사업장명칭_상태" not in result.fields
    assert all(validation.passed for validation in result.validations)


def _text_pdf(path, cells, size):
    import pymupdf

    font = pymupdf.Font("cjk")
    with pymupdf.open() as document:
        page = document.new_page(width=595, height=842)
        for x0, y0, x1, y1, text, _ in cells:
            width, height = (x1 - x0) / size[0] * 595, (y1 - y0) / size[1] * 842
            fontsize = min(width / font.text_length(text, fontsize=1), height / (font.ascender - font.descender))
            writer = pymupdf.TextWriter(page.rect)
            writer.append((x0 / size[0] * 595, y0 / size[1] * 842 + font.ascender * fontsize),
                          text, font=font, fontsize=fontsize)
            writer.write_text(page)
        document.save(path)
    return path


@pytest.mark.parametrize("source", ["own", "text"])
@pytest.mark.parametrize("mode", ["present", "blank", "missing", "malformed"])
def test_payment_evidence_survives_pdf_adapter_with_arbitrary_expected_type(source, mode, tmp_path, monkeypatch):
    from demo.backend.ocr import read_document
    from demo.backend.rules.doc_types import DocType
    from demo.backend.tests.test_p2_nhis_uploads import image_pdf, use_own_words

    cells, size = sample.payment(workplace={"present": "가상사업장", "malformed": "???"}.get(mode, ""))
    if mode == "missing":
        cells = [cell for cell in cells if cell[4] != "사업장명칭"]
    if source == "own":
        use_own_words(monkeypatch, cells, size)
        path = image_pdf(tmp_path / "FAKE-image.pdf", size)
    else:
        monkeypatch.setenv("ENGINE_V2_OCR", "off")
        path = _text_pdf(tmp_path / "FAKE-text.pdf", cells, size)
    result = read_document(str(path), DocType.RESIDENT_ABSTRACT)
    assert result.detected_doc_type == DocType.NHIS_PAYMENT
    assert result.fields["사업장명칭_상태"] == {
        "present": "값 있음", "blank": "확실한 공란", "missing": "못 읽음", "malformed": "못 읽음"}[mode]
    if mode == "missing":
        assert result.fields["양식판독상태"] == "불완전"
    else:
        assert result.fields["양식판독상태"] == "완전"
        assert result.confidence >= .85
        assert result.fields["사업장명칭"] == {"present": "가상사업장", "blank": "", "malformed": "???"}[mode]
    assert "가입구분" not in result.fields

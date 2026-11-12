"""NHIS form completeness reaches final review without business false rejection."""
from datetime import date
import pytest

from demo.backend.ocr import read_document
from demo.backend.ocr.localocr import _from_nhis
from demo.backend.rules.doc_check import check_document
from demo.backend.rules.doc_types import DocType
from demo.backend.rules.identity import Identity
from demo.backend.rules.required_docs import DocRequirement
from engine_v2.extractors import nhis_acquisition_loss
from engine_v2.schemas.models import DocType as V2DocType
from engine_v2.tests.nhis_form_samples import NAME, acquisition_cells, coordinate_page, text_pdf


def requirement():
    return DocRequirement(slot_key="nhis_acquisition_loss", doc_type=DocType.NHIS_ACQUISITION_LOSS,
                          label="가짜 자격득실 확인서", min_issue_date=date(2026, 3, 3), recent_years=5)


@pytest.mark.parametrize("defect", ["marker", "number", "page"])
def test_incomplete_nhis_skips_five_year_rejection_on_partial_history(defect):
    cells = [cell for cell in acquisition_cells() if cell[1] != 47]
    if defect == "marker":
        cells = [cell for cell in cells if cell[1] != 52]
    elif defect == "number":
        cells = [(x, y, "7" if x == 7 and y == 42 else t) for x, y, t in cells]
    else:
        cells = [(x, y, "1 / 2" if y == 4 else t) for x, y, t in cells]
    pages = [coordinate_page(cells)]
    ex = nhis_acquisition_loss.extract(pages)
    assert not next(v.passed for v in ex.validations if v.name == "recent_five_years_covered")
    ocr = _from_nhis(ex, pages, V2DocType)
    assert ocr.confidence < .85
    assert ocr.fields["양식판독상태"] == "불완전"
    result = check_document(requirement(), ocr, identity=Identity(NAME, date(1990, 1, 1)))
    assert result.status == "NEEDS_REVIEW"
    assert result.codes == ["REQUIRED_FIELD_UNREADABLE"]


def test_same_nhis_pdf_under_renamed_file_and_expected_type_is_stable(tmp_path, monkeypatch):
    monkeypatch.setenv("ENGINE_V2_OCR", "off")
    source = text_pdf(tmp_path / "fake-alpha.pdf")
    renamed = tmp_path / "fake-beta.pdf"
    renamed.write_bytes(source.read_bytes())
    results = [read_document(str(path), expected) for path, expected in [
        (source, None), (source, DocType.NHIS_QUALIFICATION), (renamed, DocType.RESIDENT_ABSTRACT)]]
    for result in results:
        assert result.tier == "localocr"
        assert result.engine == "pdftext"
        assert result.detected_doc_type == DocType.NHIS_ACQUISITION_LOSS
        assert result.fields == results[0].fields
        assert result.fields["양식판독상태"] == "완전"
    result = check_document(requirement(), results[0], identity=Identity(NAME, date(1990, 1, 1)))
    assert result.status == "PASS"


def test_real_text_pdf_long_employer_and_empty_region_keep_date_cells(tmp_path, monkeypatch):
    monkeypatch.setenv("ENGINE_V2_OCR", "off")
    cells = [(x, y, "가짜상사 (FAKE,Corp) 가짜긴사업부 가짜센터 가짜사업부가짜" if x == 33 and y == 37 else t)
             for x, y, t in acquisition_cells()]
    result = read_document(str(text_pdf(tmp_path / "fake-long.pdf", cells)))
    assert result.fields["양식판독상태"] == "완전"
    assert result.fields["취득일"] == "2024-01-01"
    assert check_document(requirement(), result, identity=Identity(NAME, date(1990, 1, 1))).status == "PASS"

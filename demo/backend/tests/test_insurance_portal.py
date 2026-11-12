"""Portal text PDF/decision regressions with synthetic identity values."""
from datetime import date
import pytest
from demo.backend.ocr import read_document
from demo.backend.ocr.localocr import _from_insurance4
from demo.backend.rules.doc_check import check_document
from demo.backend.rules.doc_types import DocType
from demo.backend.rules.identity import Identity
from demo.backend.rules.required_docs import DocRequirement
from engine_v2.extractors import insurance_4
from engine_v2.tests.nhis_form_samples import NAME, insurance_portal_cells, coordinate_page, text_pdf


def req():
    return DocRequirement(slot_key="work_proof", doc_type=DocType.INSURANCE_4,
                          label="가짜 근로 확인서", min_issue_date=date(2026, 3, 3))


@pytest.mark.parametrize("missing,phrase", [
    ([(80, 25)], "성명을 읽지 못했습니다"),
    ([(34, 25)], "생년월일을 읽지 못했습니다"),
    ([(80, 25), (34, 25)], "성명·생년월일을 모두 읽지 못했습니다"),
])
def test_portal_warning_names_only_the_missing_identity_fields(missing, phrase):
    cells = [cell for cell in insurance_portal_cells() if cell[:2] not in missing]
    pages = [coordinate_page(cells)]
    converted = _from_insurance4(insurance_4.extract(pages), pages)
    result = check_document(req(), converted, identity=Identity(NAME, date(1990, 1, 1)))
    assert result.status == "NEEDS_REVIEW"
    assert any(phrase in finding.message for finding in result.findings)
    assert all(finding.severity != "FAIL" for finding in result.findings)


def test_portal_actual_text_pdf_reads_birth_and_keeps_output_timestamp_separate(tmp_path, monkeypatch):
    monkeypatch.setenv("ENGINE_V2_OCR", "off")
    result = read_document(str(text_pdf(tmp_path / "fake-portal.pdf", insurance_portal_cells())))
    assert result.tier == "localocr"
    assert result.engine == "pdftext"
    assert result.fields["성명"] == NAME
    assert result.fields["생년월일"] == "1990-01-01"
    assert result.fields["발급일"] == "2026-03-03"
    assert result.fields["양식판독상태"] == "완전"
    decision = check_document(req(), result, date(2026, 3, 3), identity=Identity(NAME, date(1990, 1, 1)))
    assert decision.status == "PASS"
    assert not decision.findings


def test_portal_final_conversion_rechecks_header_only_identity_fields():
    pages = [coordinate_page(insurance_portal_cells())]
    extracted = insurance_4.extract(pages)
    extracted.fields["성명"].value = "주 민 등 록 번 호"
    result = _from_insurance4(extracted, pages)
    assert "성명" not in result.fields
    assert result.fields["양식판독상태"] == "불완전"
    assert "성명_required" in result.fields["판독검증실패"]
    assert result.confidence < .85
    assert check_document(req(), result).status == "NEEDS_REVIEW"


@pytest.mark.parametrize("defect", ["headings", "category", "management", "duplicate-identity"])
def test_incomplete_portal_structure_cannot_pass_final_decision(defect):
    cells = insurance_portal_cells()
    if defect == "headings":
        cells = [cell for cell in cells if cell[1] not in {31, 32}]
    elif defect == "category":
        cells = [cell for cell in cells if cell[:2] != (34, 40)]
    elif defect == "management":
        cells = [(x, y, "가짜번호000" if (x, y) == (48, 40) else text) for x, y, text in cells]
    else:
        cells += [(10, 26.5, "주민(외국인)등록번호"), (34, 26.5, "900101-1******"),
                  (60, 26.5, "성명"), (80, 26.5, NAME)]
    pages = [coordinate_page(cells)]
    result = _from_insurance4(insurance_4.extract(pages), pages)
    assert result.confidence < .85
    assert result.fields["양식판독상태"] == "불완전"
    assert result.fields["판독검증실패"]
    decision = check_document(req(), result, identity=Identity(NAME, date(1990, 1, 1)))
    assert decision.status == "NEEDS_REVIEW"
    assert decision.codes == ["REQUIRED_FIELD_UNREADABLE"]

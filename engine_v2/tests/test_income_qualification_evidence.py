"""Fictitious management cells distinguish observed blanks from unreadable ones."""
import pytest

from engine_v2.extractors import nhis_qualification as reader
from engine_v2.tests import p2_form_samples as sample


@pytest.mark.parametrize("empty", [False, True])
@pytest.mark.parametrize("scale,jitter,skew", [(1, 0, 0), (2, 3, 16)])
def test_management_present_and_blank_with_ocr_geometry(empty, scale, jitter, skew):
    cells, size = sample.qualification(empty_management=empty)
    result = reader.extract([sample.page(cells, size=size, scale=scale, jitter=jitter, skew=skew)])
    assert result.structure_complete
    assert result.fields["사업장관리번호_상태"].value == ("확실한 공란" if empty else "값 있음")
    assert result.fields["사업장관리번호"].value == ("" if empty else "00000000000")
    assert result.fields["사업장관리번호_상태"].bbox is not None
    assert all(check.passed for check in result.validations)


@pytest.mark.parametrize("defect", ["missing-label", "duplicate-label", "missing-pair", "missing-top",
                                    "malformed", "crossing", "low-confidence", "incomplete"])
def test_management_uncertainty_is_not_a_regional_blank(defect):
    cells, size = sample.qualification()
    if defect.startswith("missing"):
        label = {"missing-label": "사업장관리번호", "missing-pair": "증번호",
                 "missing-top": "자격확인요청일"}[defect]
        cells = [cell for cell in cells if cell[4] != label]
    elif defect == "duplicate-label":
        cells.append(sample.cell(1180, 600, 1506, 650, "사업장관리번호", 1))
    elif defect == "incomplete":
        cells = [cell for cell in cells if cell[4] != "이하여백"]
    else:
        x = 1490 if defect == "crossing" else 1841
        text = "00000X00000" if defect == "malformed" else "00000000000"
        confidence = .4 if defect == "low-confidence" else 1
        cells.append(sample.cell(x, 826, 2079, 878, text, confidence))
    result = reader.extract([sample.page(cells, size=size)])
    assert result.fields["사업장관리번호_상태"].value == "못 읽음"
    assert "사업장관리번호" not in result.fields
    if defect != "incomplete":
        assert result.structure_complete  # optional income evidence does not alter existing checks
        assert all(field.confidence >= .85 for field in result.fields.values())


def test_split_number_and_marked_empty_cell():
    cells, size = sample.qualification()
    cells.extend([sample.cell(1841, 826, 1930, 878, "00000", 1),
                  sample.cell(1940, 826, 2079, 878, "000000", 1)])
    result = reader.extract([sample.page(cells, size=size)])
    assert result.fields["사업장관리번호_상태"].value == "값 있음"
    assert result.fields["사업장관리번호"].value == "00000000000"
    cells = [cell for cell in cells if cell[0] not in {1841, 1940} or cell[1] != 826]
    cells.append(sample.cell(1841, 826, 2079, 878, "---", 1))
    result = reader.extract([sample.page(cells, size=size)])
    assert result.fields["사업장관리번호_상태"].value == "확실한 공란"


@pytest.mark.parametrize("fragment", ["-", ".", "X"])
def test_numeric_cell_never_discards_residue_between_digits(fragment):
    cells, size = sample.qualification()
    cells.extend([sample.cell(1700, 826, 1800, 878, "00000", 1),
                  sample.cell(1810, 826, 1830, 878, fragment, 1),
                  sample.cell(1841, 826, 2079, 878, "000000", 1)])
    result = reader.extract([sample.page(cells, size=size)])
    assert result.fields["사업장관리번호_상태"].value == "못 읽음"
    assert "사업장관리번호" not in result.fields


@pytest.mark.parametrize("mode", ["present", "blank", "missing", "malformed"])
def test_text_layer_pdf_management_evidence_survives_adapter(mode, tmp_path, monkeypatch):
    from demo.backend.ocr import read_document
    from demo.backend.rules.doc_types import DocType
    from engine_v2.tests.nhis_form_samples import qualification_cells, text_pdf

    monkeypatch.setenv("ENGINE_V2_OCR", "off")
    cells = qualification_cells()
    if mode == "blank":
        cells = [cell for cell in cells if cell[:2] != (78, 23)]
    elif mode == "missing":
        cells = [cell for cell in cells if cell[:2] != (57, 23)]
    elif mode == "malformed":
        cells = [(x, y, "FAKE000" if (x, y) == (78, 23) else value) for x, y, value in cells]
    path = text_pdf(tmp_path / "FAKE-evidence.pdf", cells)
    result = read_document(str(path), DocType.RESIDENT_ABSTRACT)
    expected = {"present": "값 있음", "blank": "확실한 공란", "missing": "못 읽음", "malformed": "못 읽음"}
    assert result.detected_doc_type == DocType.NHIS_QUALIFICATION
    assert result.fields["양식판독상태"] == "완전"
    assert result.fields["사업장관리번호_상태"] == expected[mode]
    assert result.confidence >= .85
    if mode in {"present", "blank"}:
        assert result.fields["사업장관리번호"] == ("00000000000" if mode == "present" else "")
    else:
        assert "사업장관리번호" not in result.fields

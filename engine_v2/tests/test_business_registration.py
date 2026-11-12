"""Business-proof completeness is independent of filenames and slot hints."""
from datetime import date

import pytest

from engine_v2.engine import EXTRACTORS, _load_pages
from engine_v2.extractors import business_registration as reader
from engine_v2.schemas.models import DocType, DocumentInput
from . import p2_business_samples as sample


def extract(cells=None, **options):
    authored, size = sample.business(**options)
    return reader.extract([sample.page(authored if cells is None else cells, size=size)], today=date(2026, 3, 4))


def test_observed_own_form_reads_all_thirteen_fields():
    result = extract()
    assert result.detected_type is DocType.BIZ_REG_PROOF
    assert result.structure_complete
    assert all(check.passed for check in result.validations)
    assert not result.warnings
    assert set(result.fields) == set(reader.REQUIRED_FIELDS)
    assert result.fields["성명"].value == sample.NAME
    assert result.fields["생년월일"].value == date(1990, 1, 1)
    assert result.fields["사업자등록번호"].value == sample.NUMBER
    assert result.fields["과세유형"].value == "일반과세자"
    assert result.fields["업태"].value == ["가상업종가", "합성 품목가 제공업", "가짜서비스"]
    assert result.fields["종목"].value == ["가상품목가", "가상 상품가 판매업", "합성서비스업"]
    assert result.fields["공동사업자유무"].value is False
    assert result.fields["발급일"].value == date(2026, 3, 3)
    assert EXTRACTORS[DocType.BIZ_REG_PROOF] is reader.extract
    assert "654321" not in repr(result)


def test_last_category_continuation_is_read_until_joint_header_boundary():
    cells, _ = sample.business(noise=False)
    cells.append(sample.cell(633, 1560, 1380, 1600, "|추가누락가상품목", .99))
    result = extract(cells)
    assert result.structure_complete
    assert result.fields["종목"].value[-1] == "추가누락가상품목"
    assert result.warnings == []


@pytest.mark.parametrize("top,bottom", [(1590, 1630), (1605, 1645)])
def test_grid_value_crossing_joint_header_is_incomplete(top, bottom):
    cells, _ = sample.business(noise=False)
    cells.append(sample.cell(633, top, 1380, bottom, "|경계확인품목", .99))
    result = extract(cells)
    assert not result.structure_complete
    assert not next(check.passed for check in result.validations if check.name == "business_label_grid")


def test_competing_left_column_grid_content_requires_review():
    cells, _ = sample.business(noise=False)
    cells.append(sample.cell(260, 1550, 500, 1590, "가상추가표제", .99))
    result = extract(cells)
    assert not result.structure_complete
    assert not next(check.passed for check in result.validations if check.name == "business_label_grid")


@pytest.mark.parametrize("partial", [False, True])
def test_joint_name_left_of_centered_header_is_accounted_for(partial):
    cells, _ = sample.business(noise=False, joint_count=0 if partial else 1)
    cells = [cell for cell in cells if cell[4] != "이합성"]
    cells.append(sample.cell(650, 1690, 730, 1735, "이합성", .99))
    result = extract(cells)
    assert result.structure_complete is (not partial)
    if not partial:
        assert result.fields["공동사업자유무"].value is True
    else:
        assert not next(check.passed for check in result.validations if check.name == "business_joint_section_read")


@pytest.mark.parametrize("left,right", [(500, 620), (1100, 1400)])
def test_joint_word_crossing_observed_cell_boundary_requires_review(left, right):
    cells, _ = sample.business(noise=False, joint_count=1)
    cells = [(left, cell[1], right, cell[3], cell[4], cell[5]) if cell[4] == "이합성" else cell
             for cell in cells]
    result = extract(cells)
    assert not result.structure_complete
    assert not next(check.passed for check in result.validations if check.name == "business_joint_section_read")


@pytest.mark.parametrize("name", ["가상", "김가상", "가상합성"])
@pytest.mark.parametrize("scale,jitter,skew", [(1, 0, 0), (.6, 3, 8), (1.4, 4, -10)])
@pytest.mark.parametrize("blank_rows", [False, True])
def test_relative_geometry_names_and_blank_rows(name, scale, jitter, skew, blank_rows):
    cells, size = sample.business(name=name, blank_rows=blank_rows)
    result = reader.extract([sample.page(cells, size=size, scale=scale, jitter=jitter, skew=skew)],
                            today=date(2026, 3, 4))
    assert result.structure_complete, [check.name for check in result.validations if not check.passed]
    assert result.fields["성명"].value == name


@pytest.mark.parametrize("count", range(1, 11))
@pytest.mark.parametrize("jitter,skew", [(0, 0), (3, 16), (3, -16)])
def test_all_joint_participant_rows_are_read(count, jitter, skew):
    cells, size = sample.business(joint_count=count, multiline=True)
    result = reader.extract([sample.page(cells, size=size, jitter=jitter, skew=skew)], today=date(2026, 3, 4))
    assert result.structure_complete
    assert result.fields["공동사업자유무"].value is True
    assert result.fields["업태"].value[-1] == "추가합성업"
    assert result.fields["종목"].value[-1] == "추가가상품목"


@pytest.mark.parametrize("number", [sample.CORPORATE_NUMBER, "123-80-12344", "123-89-12347"])
def test_corporate_or_unknown_entity_never_derives_birth_from_legal_number(number):
    result = extract(number=number)
    assert next(check.passed for check in result.validations if check.name == "business_number_checksum")
    assert not result.structure_complete
    assert "생년월일" not in result.fields
    assert result.warnings
    assert all(field.confidence <= .4 for field in result.fields.values())


@pytest.mark.parametrize("number", ["123-01-12349", "123-79-12348", "123-90-12343", "123-99-12346"])
def test_valid_personal_entity_ranges_keep_birth(number):
    result = extract(number=number)
    assert result.structure_complete
    assert result.fields["생년월일"].value == date(1990, 1, 1)


@pytest.mark.parametrize("tax_type", ["(법인사업자)", "(일반과세자(법인))", "split"])
def test_corporate_type_evidence_conflicting_with_personal_number_suppresses_birth(tax_type):
    cells, _ = sample.business()
    if tax_type == "split":
        cells = [cell for cell in cells if cell[4] != "(일반과세자)"]
        cells.extend([sample.cell(850, 452, 940, 513, "(법", 1),
                      sample.cell(945, 452, 1215, 513, "인사업자)", 1)])
    else:
        cells = [(*cell[:4], tax_type, cell[5]) if cell[4] == "(일반과세자)" else cell for cell in cells]
    result = extract(cells)
    assert not result.structure_complete
    assert "생년월일" not in result.fields
    assert not next(check.passed for check in result.validations if check.name == "business_entity_consistent")


@pytest.mark.parametrize("missing", reader.REQUIRED_FIELDS)
def test_missing_required_values_cannot_pass(missing):
    cells, _ = sample.business(noise=False)
    removed = {
        "발급번호": "1234-567-8901-234", "과세유형": "(일반과세자)", "상호": "가상합성상점",
        "사업자등록번호": sample.NUMBER, "성명": sample.NAME, "생년월일": "900101-1654321",
        "사업장소재지": "전북특별자치도 전주시 가상구 합성9길 12,345동 678호(가상동9가)",
        "개업일": "2018년 01월 02일", "사업자등록일": "2018년 01월 03일",
        "업태": "가상업종가|합성 품목가 제공업|가짜서비스", "종목": "가상품목가|가상 상품가 판매업|합성서비스업",
        "공동사업자유무": "해당사항이 없습니다.", "발급일": "2026년 3월 3일",
    }[missing]
    result = extract([cell for cell in cells if cell[4] != removed])
    assert not result.structure_complete
    assert any(not check.passed for check in result.validations)
    assert all(field.confidence <= .4 for field in result.fields.values())


@pytest.mark.parametrize("defect", ["checksum", "duplicate-label", "duplicate-issue", "malformed-issue",
                                  "missing-notice", "missing-issuer", "future-issue", "joint-partial",
                                  "joint-conflict", "representative-residue", "representative-header", "date-residue"])
def test_ambiguous_or_corrupt_cells_are_reviewable(defect):
    cells, _ = sample.business(noise=False)
    if defect == "checksum":
        cells = [(*cell[:4], "123-45-67890", cell[5]) if cell[4] == sample.NUMBER else cell for cell in cells]
    elif defect == "duplicate-label":
        cells.append(sample.cell(245, 700, 530, 740, "사업자등록번호", 1))
    elif defect == "duplicate-issue":
        cells.append(sample.cell(1311, 2190, 1567, 2234, "2026년 3월 3일", .99))
    elif defect in {"malformed-issue", "future-issue"}:
        replacement = "2026년 13월 3일" if defect == "malformed-issue" else "2027년 3월 3일"
        cells = [(*cell[:4], replacement, cell[5]) if cell[4] == "2026년 3월 3일" else cell for cell in cells]
    elif defect in {"missing-notice", "missing-issuer"}:
        cells = [cell for cell in cells if not ("발급일 현재" in cell[4] if defect == "missing-notice" else "세무서장" in cell[4])]
    elif defect in {"joint-partial", "joint-conflict"}:
        cells.append(sample.cell(867, 1690, 1047, 1735, "이합성", .99))
        if defect == "joint-conflict":
            cells.append(sample.cell(1445, 1690, 1740, 1735, "910202-2******", .99))
    elif defect == "representative-residue":
        cells = [(*cell[:4], sample.NAME + "(알수없음)", cell[5]) if cell[4] == sample.NAME else cell for cell in cells]
    elif defect == "representative-header":
        cells = [(*cell[:4], "대표자성명", cell[5]) if cell[4] == sample.NAME else cell for cell in cells]
    else:
        cells = [(*cell[:4], "2018년 01월 02일 999", cell[5]) if cell[4] == "2018년 01월 02일" else cell for cell in cells]
    result = extract(cells)
    assert not result.structure_complete
    assert result.warnings


def test_explicit_representative_role_and_text_layer_are_supported(tmp_path):
    cells, size = sample.business(representative_role="공동대표")
    path = sample.text_pdf(tmp_path / "FAKE-unrelated.pdf", cells, size)
    pages = _load_pages(DocumentInput(doc_id="FAKE", declared_type=DocType.BIZ_REG_PROOF, file_path=str(path)), "off")
    result = reader.extract(pages, today=date(2026, 3, 4))
    assert result.structure_complete, [check.name for check in result.validations if not check.passed]
    assert result.fields["성명"].value == sample.NAME


def test_future_opening_date_is_read_without_an_employment_inference():
    cells, _ = sample.business()
    cells = [(*cell[:4], "2030년 01월 02일", cell[5]) if cell[4] == "2018년 01월 02일" else cell for cell in cells]
    result = extract(cells)
    assert result.structure_complete
    assert result.fields["개업일"].value == date(2030, 1, 2)
    assert not result.warnings
    assert all(check.passed for check in result.validations)


@pytest.mark.parametrize("top", [2240, 2260])
@pytest.mark.parametrize("extra", ["2025.01.01", "2026.13.01", "2026년 O월 3일"])
def test_numeric_date_evidence_overlapping_issuer_is_ambiguous(top, extra):
    cells, _ = sample.business()
    cells.append(sample.cell(1311, top, 1567, top + 44, extra, 1))
    result = extract(cells)
    assert not result.structure_complete
    assert "발급일" not in result.fields
    assert not next(check.passed for check in result.validations if check.name == "business_issue_location_unique")


def test_equal_joint_column_counts_cannot_hide_a_missing_first_and_last_row():
    cells, _ = sample.business(joint_count=10)
    cells = [cell for cell in cells if not (cell[0] == 867 and cell[1] == 1690)
             and not (cell[0] == 1445 and cell[1] == 1879)]
    result = extract(cells)
    assert not result.structure_complete
    assert "공동사업자유무" not in result.fields


def test_multiple_pages_and_wrong_title_cannot_complete():
    cells, size = sample.business()
    page = sample.page(cells, size=size)
    result = reader.extract([page, page], today=date(2026, 3, 4))
    assert not result.structure_complete
    changed = [(*cell[:4], "사업자등록증", cell[5]) if "사업자등록증명" in cell[4].replace(" ", "") else cell for cell in cells]
    result = extract(changed)
    assert result.detected_type is DocType.UNKNOWN
    assert not result.structure_complete

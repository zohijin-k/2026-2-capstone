"""Synthetic coordinate regressions for OCR-only NHIS layout variations."""
from dataclasses import replace
from datetime import date

import pytest

from engine_v2.extractors import nhis_common as common, nhis_forms as forms
from engine_v2.tests import observed_form_samples as sample
from engine_v2.tests.nhis_form_samples import acquisition_cells, coordinate_page


@pytest.mark.parametrize("role", ["", " 이사", " 이사장"])
def test_issue_date_uses_unique_closing_organization_with_obscured_role(role):
    cells = [(x, y, "국민건강보험공단" + role if y == 76 else text)
             for x, y, text in acquisition_cells()]
    cells.extend([(70, 1, "국민건강보험공단"),
                  (15, 60, "자격확인요청일 2026.03.03"),
                  (15, 81, "2026.03.03 까지 유효합니다.")])
    value, words, valid = forms.confirmation_issue_date(*coordinate_page(cells))
    assert valid
    assert value == date(2026, 3, 3)
    assert common.line_text(words) == "2026.03.03"


@pytest.mark.parametrize("extra", ["2026.03.03", "2026.99.99", "가상문자 2026.03.03"])
def test_issue_date_keeps_duplicate_malformed_and_residual_date_failures(extra):
    cells = [*acquisition_cells(), (43, 74, extra)]
    assert forms.confirmation_issue_date(*coordinate_page(cells)) == (None, [], False)


def test_two_closing_organizations_remain_ambiguous():
    cells = [*acquisition_cells(), (30, 78, "국민건강보험공단")]
    assert forms.confirmation_issue_date(*coordinate_page(cells)) == (None, [], False)


@pytest.mark.parametrize("label", ["업태", "종목", "개업일"])
def test_justified_labels_require_observed_label_cell_bounds(label):
    cells = [sample.word(30 + index * 70, 30, 10, char, 12)
             for index, char in enumerate(label)]
    cells.append(sample.word(260, 30, 90, "가상 업 태 값", 12))
    lines = common.page_lines(*sample.page(cells))
    before = [word.text for row in lines for word in row]
    assert not forms.label_hits(lines, (label,))
    # Bounds use the same normalized coordinate space as the observed words.
    bounds = (20 / 595 * 100, 220 / 595 * 100)
    hits = forms.label_hits(lines, (label,), x_bounds=bounds)
    assert len(hits) == 1
    assert common.line_text(hits[0][1]).replace(" ", "") == label
    assert [word.text for row in lines for word in row] == before


def test_bounded_label_does_not_recruit_value_glyphs():
    cells = [sample.word(30, 30, 10, "업", 12), sample.word(260, 30, 10, "태", 12)]
    lines = common.page_lines(*sample.page(cells))
    assert not forms.label_hits(lines, ("업태",), x_bounds=(0, 40))


@pytest.mark.parametrize("count", [1, 3, 10])
@pytest.mark.parametrize("scale,jitter", [(1, 0), (3, 1)])
def test_observed_headers_support_empty_rightmost_optional_columns(count, scale, jitter):
    cells = [sample.word(30, 30, 30, "성명"), sample.word(130, 30, 65, "주민등록번호"),
             sample.word(260, 30, 65, "자격취득일"), sample.word(370, 30, 65, "자격상실일"),
             sample.word(480, 30, 65, "급여정지사유")]
    for index in range(count):
        y = 60 + 25 * index
        cells.extend([sample.word(25, y, 30, "가상인"),
                      sample.word(115, y, 80, "900101-1******"),
                      sample.word(265, y, 55, "2020.01.01")])
    lines = common.page_lines(*sample.page(cells, scale=scale, jitter=jitter))
    labels = ("성명", "주민등록번호", "자격취득일", "자격상실일", "급여정지")
    headers = [forms.label_hits([lines[0]], (label,))[0][1] for label in labels]
    assert forms.table_columns(headers, lines[1:]) is None
    bounds = forms.table_columns(headers, lines[1:], optional_columns=(3, 4))
    assert bounds is not None
    for row in lines[1:]:
        separated = forms.column_cells(row, bounds)
        assert separated is not None
        assert common.line_text(separated[0]) == "가상인"
        assert common.line_text(separated[1]) == "900101-1******"
        assert common.line_text(separated[2]) == "2020.01.01"
        assert separated[3:] == [[], []]


def test_marker_body_gap_preserves_empty_middle_column_with_offset_header():
    cells = [sample.word(10, 30, 12, "No"), sample.word(40, 30, 45, "가입자구분"),
             sample.word(160, 30, 60, "사업장명칭"), sample.word(280, 30, 60, "자격취득일"),
             sample.word(400, 30, 60, "자격상실일"),
             sample.word(12, 60, 7, "1"), sample.word(35, 60, 40, "지역세대주"),
             sample.word(285, 60, 50, "2020.01.01"),
             sample.word(110, 90, 35, "이하여백")]
    lines = common.page_lines(*sample.page(cells))
    labels = ("No", "가입자구분", "사업장명칭", "자격취득일", "자격상실일")
    headers = [forms.label_hits([lines[0]], (label,))[0][1] for label in labels]
    bounds = forms.table_columns(headers, lines[1:], optional_columns=(2, 4))
    assert bounds is not None
    marker = lines[-1][0]
    assert bounds[2] <= marker.x0 < marker.x1 <= bounds[3]


def test_optional_header_never_repairs_an_ambiguous_occupied_corridor():
    cells = [sample.word(10, 10, 10, "첫째"), sample.word(90, 10, 10, "둘째"),
             sample.word(10, 30, 10, "가상"), sample.word(50, 30, 10, "중간"),
             sample.word(90, 30, 10, "가상")]
    lines = common.page_lines(*sample.page(cells))
    assert forms.table_columns([[lines[0][0]], [lines[0][1]]], [lines[1]], optional_columns=(1,)) is None


def test_optional_column_still_requires_observed_header():
    lines = common.page_lines(*sample.page([sample.word(10, 30, 10, "가상")]))
    assert forms.table_columns([[lines[0][0]], []], lines, optional_columns=(1,)) is None


def test_table_noise_requires_both_confidence_and_geometry_evidence():
    ordinary = common.page_lines(*sample.page([sample.word(10, 30, 20, "가상", 12)]))[0][0]
    height = ordinary.y1 - ordinary.y0
    low = replace(ordinary, conf=.1)
    tall = replace(ordinary, y1=ordinary.y0 + 4 * height, conf=.64)
    tiny = replace(ordinary, x1=ordinary.x0 + height / 2,
                   y1=ordinary.y0 + height / 2, conf=.18)
    assert not forms.table_noise(low, height)
    assert forms.table_noise(tall, height)
    assert forms.table_noise(tiny, height)
    assert not forms.table_noise(replace(tall, conf=.99), height)
    assert not forms.table_noise(replace(tiny, conf=.99), height)
    assert not forms.table_noise(tall, 0)

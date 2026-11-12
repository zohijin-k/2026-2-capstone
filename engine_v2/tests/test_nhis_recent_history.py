"""Tri-state coverage needs complete evidence, using only fictitious inputs."""
from dataclasses import replace
from datetime import date
import json

import pytest

from engine_v2.extractors import nhis_acquisition_loss as reader
from engine_v2.pipeline.preprocess import PageSource
from engine_v2.tests.nhis_form_samples import coordinate_page
from engine_v2.tests.nhis_recent_history_samples import ISSUE, cells_for


@pytest.mark.parametrize("source", [PageSource.TEXT_LAYER, PageSource.EMBEDDED])
@pytest.mark.parametrize("case,covered,basis,complete", [
    ("complete", True, "full_history", True),
    ("missing-marker", None, "undetermined", False),
    ("bad-structure", None, "undetermined", False),
    ("short-period", False, "query_period", True),
    ("full-period", True, "query_period", True),
    ("unreadable-period", None, "undetermined", True),
    ("old", True, "history_rows", True),
])
def test_serialized_coverage_matches_evidence_and_structure(source, case, covered, basis, complete):
    page, words = coordinate_page(cells_for(case))
    result = reader.extract([(replace(page, source=source), words)])
    history = json.loads(result.fields["자격이력자료"].value)
    assert result.form_kind == "nhis"
    assert result.structure_complete is complete
    assert history["recent_five_years_covered"] is covered
    assert history["coverage_basis"] == basis
    assert history["coverage_years"] == 5
    assert history["period_label_present"] is ("period" in case)
    assert result.fields["변동내역"].value == {
        True: "최근 5년 포함", False: "최근 5년 미포함", None: "최근 5년 확인 필요"}[covered]
    assert next(v.passed for v in result.validations if v.name == "recent_five_years_covered") is (covered is True)
    if case == "complete":
        assert history["period"] is None
        assert history["rows"] == [
            {"category": "직장가입자", "acquired": "2030-01-01", "lost": None,
             "acquired_confidence":.99,"lost_confidence":None},
            {"category": "지역세대주", "acquired": "2028-01-01", "lost": "2029-01-01",
             "acquired_confidence":.99,"lost_confidence":.99}]
        assert len(result.history) == 2
        assert result.history[1].lost < result.history[0].acquired  # exactly one gap
        assert result.history[1].acquired > date(2026, 7, 8)
        assert all(v.passed for v in result.validations)
        assert not result.warnings


@pytest.mark.parametrize("marker", ["이하여백", "이 하 여 백", "== 이 하 여 백 ==", "이하여뱍"])
def test_bounded_marker_variants_allow_recent_complete_history(marker):
    result = reader.extract([coordinate_page(cells_for(marker=marker))])
    assert result.structure_complete
    assert json.loads(result.fields["자격이력자료"].value)["coverage_basis"] == "full_history"


@pytest.mark.parametrize("defect", ["side", "notice", "neighbor", "hidden-row", "unknown-spelling"])
def test_marker_cannot_hide_unreadable_or_out_of_table_evidence(defect):
    cells = cells_for()
    if defect in {"side", "notice"}:
        cells = [(5 if defect == "side" else x, 82 if defect == "notice" else y, text)
                 if text == "이하여백" else (x, y, text) for x, y, text in cells]
    elif defect == "neighbor":
        cells.append((15, 52, "지역세대주"))
    elif defect == "hidden-row":
        cells.extend([(7, 57, "3"), (15, 57, "지역세대주"), (65, 57, "2027.01.01")])
    else:
        cells = [(x, y, "이하불명" if text == "이하여백" else text) for x, y, text in cells]
    result = reader.extract([coordinate_page(cells)])
    assert not result.structure_complete
    assert json.loads(result.fields["자격이력자료"].value)["recent_five_years_covered"] is None


def test_unreadable_period_label_overrides_old_row_and_blank_marker():
    cells = cells_for("old") + [(10, 29, "대상기간")]
    result = reader.extract([coordinate_page(cells)])
    data = json.loads(result.fields["자격이력자료"].value)
    assert result.structure_complete
    assert data["period_label_present"] is True
    assert data["coverage_basis"] == "undetermined"
    assert data["recent_five_years_covered"] is None


def test_conflicting_query_periods_do_not_form_a_false_union():
    cells = cells_for("short-period") + [(10, 58, "대상기간"), (30, 58, "2020.01.01"),
                                          (55, 58, "2021.01.01")]
    result = reader.extract([coordinate_page(cells)])
    data = json.loads(result.fields["자격이력자료"].value)
    assert data["period"] is None
    assert data["recent_five_years_covered"] is None


def test_non_nhis_recent_rows_remain_unknown_without_full_history_proof():
    covered, basis = reader.assess_history_coverage(
        date.fromisoformat(ISSUE), None, [(date(2030, 1, 1), None)],
        period_label_present=False, structure_valid=True, complete_nhis_history=False)
    assert covered is None
    assert basis == "undetermined"

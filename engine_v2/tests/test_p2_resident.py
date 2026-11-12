"""Separated law-note numbering and unresolved history confidence propagate."""
from datetime import date

import pytest

from engine_v2.engine import evaluate_document, load_rulepack
from engine_v2.extractors import resident_abstract as reader
from engine_v2.pipeline.ocr import OcrWord
from engine_v2.schemas.models import Verdict
from engine_v2.tests import p2_resident_samples as sample
from engine_v2.tests.test_engine import app


@pytest.mark.parametrize("name", ["가상", "가상인", "가상인명"])
@pytest.mark.parametrize("scale,jitter,skew", [(1, 0, 0), (.7, 1, 4), (1.8, 2, -5)])
@pytest.mark.parametrize("boundary", [False, True])
def test_unequal_font_note_numbers_preserve_multisheet_history(name, scale, jitter, skew, boundary):
    pages = sample.resident(name=name, scale=scale, jitter=jitter, skew=skew, boundary=boundary)
    result = reader.extract(pages)
    assert all(validation.passed for validation in result.validations), [v for v in result.validations if not v.passed]
    assert result.warnings == []
    assert result.fields["name"].value == name
    assert result.fields["birth_date"].value == date(1999, 1, 1)
    assert result.fields["issue_date"].value == date(2026, 3, 3)
    assert [entry.no for entry in result.history] == [1, 2, 3, 4, 5, 6, 7, 9, 11]
    assert result.history[-1].notes[0].startswith("[행정구역")
    assert result.history[-2].notes[0].startswith("[도로명")
    assert all(field.confidence >= .9 for key, field in result.fields.items() if key != "issuer")


@pytest.mark.parametrize("defect", ["first", "last", "all", "middle", "note", "duplicate", "unreadable"])
def test_unreadable_or_missing_number_stays_failed_and_caps_all_fields(defect):
    result = reader.extract(sample.damage(sample.resident(), defect))
    assert not next(v.passed for v in result.validations if v.name == "history_numbers_sequential")
    assert result.warnings
    assert all(field.confidence <= .4 for field in result.fields.values())
    assert result.fields["name"].value == sample.NAME
    assert result.fields["issue_date"].value == date(2026, 3, 3)


@pytest.mark.parametrize("offset", [4, 20])
def test_contiguous_numbering_start_remains_compatible(offset):
    result = reader.extract(sample.resident(offset=offset))
    assert all(validation.passed for validation in result.validations)
    assert result.warnings == []


def test_orphan_number_cannot_be_discarded_as_continuation():
    pages = sample.resident()
    pages[2][1].words.append(OcrWord("12", .99, (170, 1250, 221, 1296)))
    result = reader.extract(pages)
    assert not next(v.passed for v in result.validations if v.name == "history_numbers_sequential")


def test_ambiguous_note_numbers_do_not_complete_history():
    pages = sample.resident()
    pages[2][1].words.append(OcrWord("10", .99, (171, 1102, 222, 1148)))
    result = reader.extract(pages)
    assert not next(v.passed for v in result.validations if v.name == "history_numbers_sequential")


@pytest.mark.parametrize("wrong_issue,wrong_residence", [(True, False), (False, True), (True, True)])
def test_core_resident_evaluation_does_not_reject_untrusted_history(wrong_issue, wrong_residence):
    pages = sample.damage(sample.resident(), "middle")
    if wrong_residence:
        for page, result in pages:
            for word in result.words:
                word.text = word.text.replace("전라북도", "경기도").replace("전북특별자치도", "경기도")
    application = app(name=sample.NAME, birth=date(1999, 1, 1),
                      issue="2026-03-02" if wrong_issue else sample.ISSUE, announce=date(2026, 3, 1))
    result = evaluate_document(application.documents[0], pages, application, load_rulepack("doubling_savings"))
    assert result.verdict == Verdict.NEEDS_REVIEW
    assert result.review_reasons


def test_non_note_near_number_is_never_reclassified_as_a_note():
    pages = sample.resident()
    note = next(word for word in pages[2][1].words if word.text.startswith("[행정구역"))
    note.text = "전북특별자치도 가상시 가상로"
    result = reader.extract(pages)
    assert not next(v.passed for v in result.validations if v.name == "history_numbers_sequential")


@pytest.mark.parametrize("continuation", [False, True])
def test_unnumbered_bracketed_annotation_keeps_legacy_note_semantics(continuation):
    pages = sample.resident()
    y = 1158 if continuation else 1250
    pages[2][1].words.append(OcrWord("[가상 추가 안내]", .99, (278, y, 1054, y + 28)))
    result = reader.extract(pages)
    assert all(validation.passed for validation in result.validations)
    assert result.warnings == []

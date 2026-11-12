"""Only independently readable, consistent selection counts establish partial FAIL."""
from datetime import date
import json
import pytest

from demo.backend.ocr.localocr import _from_nhis
from demo.backend.rules.doc_check import check_document
from demo.backend.rules.doc_types import DocType
from demo.backend.rules.identity import Identity
from demo.backend.rules.programs import PROGRAMS, DOUBLE_SAVINGS
from demo.backend.rules.required_docs import WorkCategory
from demo.backend.rules.work_continuity import assess_work
from demo.backend.tests.test_followup_daily_reproduction import document, requirement
from engine_v2.extractors.daily_work_record import extract, selection_status
from engine_v2.schemas.models import DocType as V2Type
from engine_v2.tests import fail_case_samples as base
from engine_v2.tests.followup3_daily_samples import daily_notices


def assess(pages):
    ex = extract(pages, today=date(2026,3,3))
    read = _from_nhis(ex, pages, V2Type, detected_override=DocType.DAILY_WORK_RECORD)
    result = check_document(requirement(), read, identity=Identity(base.NAME, base.BIRTH))
    program = PROGRAMS[DOUBLE_SAVINGS]
    work = assess_work(program, program.announcement_date, WorkCategory.LOCAL,
                       [document(read, result.status)], Identity(base.NAME, base.BIRTH))
    return ex, read, result, work


@pytest.mark.parametrize("total,selected", [(10,9), (20,9)])
def test_certain_partial_selection_fails_but_work_remains_unknown(total, selected):
    ex, read, result, work = assess(daily_notices(total=total, selected=selected))
    assert ex.structure_complete is True
    assert selection_status(read.fields) == "PARTIAL"
    assert result.status == "FAIL" and result.codes == ["DAILY_RECORDS_PARTIALLY_SELECTED"]
    assert result.findings[0].how_to_fix == "전체 이력을 선택해 다시 발급받아 올려 주세요"
    assert work.status == "UNDETERMINED" and work.detail_codes == ["WORK_DAILY_SELECTION_INCOMPLETE"]


@pytest.mark.parametrize("defect", ["unreadable", "low-confidence", "conflict", "one-copy-absent", "extra-count", "bad-order",
                                    "missing-open", "missing-close", "damaged-label", "row-count"])
def test_unreadable_or_conflicting_counts_never_establish_partial_fail(defect):
    pages = daily_notices()
    for page, recognized in pages:
        for word in list(recognized.words):
            if not word.text.startswith("(조회기간"):
                continue
            if defect == "unreadable":
                word.text = "(조회기간 총 FAKE개 이력 중 ?개 이력 선택 발급 요청)"
            elif defect == "low-confidence":
                word.text = "(조회기간 총 10개 이력 중 9개 이력 선택 발급 요청)"
                word.confidence = .4
            elif defect == "conflict" and page.page == 2:
                word.text = "(조회기간 총 10개 이력 중 9개 이력 선택 발급 요청)"
            elif defect == "one-copy-absent" and page.page == 2:
                recognized.words.remove(word)
            elif defect == "extra-count":
                word.text = "(조회기간 총 10개 이력 중 9개 이력 선택 발급 요청) 0"
            elif defect == "bad-order":
                word.text = "(조회기간 총 8개 이력 중 9개 이력 선택 발급 요청)"
            elif defect == "missing-open":
                word.text = word.text[1:]
            elif defect == "missing-close":
                word.text = word.text[:-1]
            elif defect == "damaged-label":
                word.text = word.text.replace("조회기간", "조회기FAKE")
            elif defect == "row-count":
                word.text = "(조회기간 총 10개 이력 중 8개 이력 선택 발급 요청)"
    ex, read, result, work = assess(pages)
    assert selection_status(read.fields) in {"UNREADABLE", "CONFLICT"}
    assert result.status != "FAIL" and "DAILY_RECORDS_PARTIALLY_SELECTED" not in result.codes
    assert work.status == "UNDETERMINED" and "WORK_DAILY_SELECTION_UNCONFIRMED" in work.detail_codes


def test_unknown_graphic_marks_are_reference_warning_only():
    ex, read, result, work = assess(daily_notices())
    assert ex.structure_complete is True and read.confidence >= .9
    assert json.loads(read.fields["보험구분"]) == ["미확인"]
    assert result.status == "PASS" and work.status == "NOT_MET"
    assert "참고 정보" in read.fields["판독경고"]


@pytest.mark.parametrize("partial", [False, True])
def test_copy_row_disagreement_retains_review(partial):
    pages = daily_notices(total=10 if partial else 9)
    for word in pages[2][1].words:
        if word.text == "가짜사업장":
            word.text = "다른가짜사업장"
    ex, read, result, work = assess(pages)
    assert ex.structure_complete is False
    assert result.status == "NEEDS_REVIEW"
    assert "REQUIRED_FIELD_UNREADABLE" in result.codes
    assert work.status == "UNDETERMINED"

"""Pre-fix reproduction of all six failed validations through a fake text PDF."""
from datetime import date
from demo.backend.ocr import read_document
from demo.backend.rules.doc_check import check_document
from demo.backend.rules.doc_types import DocType
from demo.backend.rules.identity import identity_of
from demo.backend.rules.programs import DOUBLE_SAVINGS, PROGRAMS
from demo.backend.rules.required_docs import WorkCategory
from demo.backend.rules.work_continuity import assess_work
from demo.backend.tests.test_daily_work_uploads import text_pdf
from demo.backend.tests.test_followup_daily_reproduction import document, requirement
from demo.backend.tools.verify_upload import _identity_from_ocr
from engine_v2.extractors.daily_work_record import extract
from engine_v2.tests.followup3_daily_samples import daily_notices


EXPECTED_FAILURES = {f"daily_{copy}_{check}" for copy in (0, 1)
                     for check in ("query_period", "confirmation", "continuation")}


def test_source_notice_and_selection_note_reproduce_actual_structural_failure(tmp_path, monkeypatch):
    pages = daily_notices()
    direct = extract(pages, today=date(2026,3,3))
    assert {v.name for v in direct.validations if not v.passed} == EXPECTED_FAILURES
    path = text_pdf(tmp_path / "FAKE-opaque.pdf", pages)
    monkeypatch.setenv("ENGINE_V2_OCR", "off")
    read = read_document(str(path), DocType.NHIS_PAYMENT)
    assert read.detected_doc_type == DocType.DAILY_WORK_RECORD
    assert read.page_count == 4 and read.confidence == .4
    assert read.fields["양식판독상태"] == "불완전"
    assert set(read.fields["판독검증실패"].split(", ")) == EXPECTED_FAILURES
    assert "조회기간" not in read.fields and "생년월일" not in read.fields
    for key in ("발급번호", "발급일", "성명", "생년월일표기", "생년월일후보", "보험구분", "일용근로내역자료"):
        assert key in read.fields
    program = PROGRAMS[DOUBLE_SAVINGS]
    identity = _identity_from_ocr(read, program)
    assert identity is not None
    result = check_document(requirement(), read, identity=identity_of(identity))
    assert result.status == "NEEDS_REVIEW" and "REQUIRED_FIELD_UNREADABLE" in result.codes
    work = assess_work(program, program.announcement_date, WorkCategory.LOCAL,
                       [document(read, result.status)], identity)
    assert work.status == "UNDETERMINED"
    assert work.detail_codes == ["WORK_STRUCTURE_UNCONFIRMED"]

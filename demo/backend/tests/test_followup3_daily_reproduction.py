"""The exact query/continuation reproduction now proves work rejection."""
from datetime import date
from demo.backend.ocr import read_document
from demo.backend.rules.doc_check import check_document
from demo.backend.rules.doc_types import DocType
from demo.backend.rules.identity import identity_of
from demo.backend.rules.eligibility_blockers import eligibility_blockers
from demo.backend.rules.programs import DOUBLE_SAVINGS, PROGRAMS
from demo.backend.rules.required_docs import WorkCategory
from demo.backend.rules.work_continuity import assess_work
from demo.backend.tests.test_daily_work_uploads import text_pdf
from demo.backend.tests.test_followup_daily_reproduction import document, requirement
from demo.backend.tools.verify_upload import _identity_from_ocr
from engine_v2.extractors.daily_work_record import extract
from engine_v2.tests.followup3_daily_samples import daily_notices


def test_source_notice_and_selection_note_now_prove_complete_daily_work(tmp_path, monkeypatch):
    pages = daily_notices()
    direct = extract(pages, today=date(2026,3,3))
    assert all(v.passed for v in direct.validations)
    path = text_pdf(tmp_path / "FAKE-opaque.pdf", pages)
    monkeypatch.setenv("ENGINE_V2_OCR", "off")
    read = read_document(str(path), DocType.NHIS_PAYMENT)
    assert read.detected_doc_type == DocType.DAILY_WORK_RECORD
    assert read.page_count == 4 and read.confidence >= .9
    assert read.fields["양식판독상태"] == "완전"
    assert "판독검증실패" not in read.fields
    assert "조회기간" in read.fields and "생년월일" not in read.fields
    for key in ("발급번호", "발급일", "성명", "생년월일표기", "생년월일후보", "보험구분", "일용근로내역자료"):
        assert key in read.fields
    program = PROGRAMS[DOUBLE_SAVINGS]
    identity = _identity_from_ocr(read, program)
    assert identity is not None
    result = check_document(requirement(), read, identity=identity_of(identity))
    assert result.status == "PASS" and "REQUIRED_FIELD_UNREADABLE" not in result.codes
    work = assess_work(program, program.announcement_date, WorkCategory.LOCAL,
                       [document(read, result.status)], identity)
    assert work.status == "NOT_MET" and work.reason_code == "WORK_CONTINUITY_NOT_MET"
    assert work.detail_codes == ["WORK_DAILY_MONTHS_MISSING"]
    blockers = eligibility_blockers(program, {}, identity, [document(read, result.status)], WorkCategory.LOCAL,
                                    {"announcement_date": program.announcement_date.isoformat()})
    assert any(b["target"] == "work" and b["code"] == "WORK_CONTINUITY_NOT_MET" for b in blockers)

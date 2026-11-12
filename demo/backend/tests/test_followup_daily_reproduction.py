"""Synthetic reproduction limits and the proven short-year CLI identity gap."""
from datetime import date
import json

from demo.backend.ocr.localocr import _from_nhis
from demo.backend.rules.doc_check import check_document
from demo.backend.rules.doc_types import DocType
from demo.backend.rules.eligibility_blockers import eligibility_blockers
from demo.backend.rules.identity import Identity
from demo.backend.rules.programs import PROGRAMS, DOUBLE_SAVINGS
from demo.backend.rules.required_docs import DocRequirement, WorkCategory
from demo.backend.rules.work_continuity import assess_work
from demo.backend.tools.verify_upload import _identity_from_ocr
from engine_v2.extractors.daily_work_record import extract
from engine_v2.schemas.models import DocType as V2Type
from engine_v2.tests import fail_case_samples as base
from engine_v2.tests.followup_daily_samples import daily_short_birth


def converted(pages=None):
    pages = pages or daily_short_birth()
    extracted = extract(pages, today=date(2026, 3, 3))
    return extracted, _from_nhis(extracted, pages, V2Type,
                                 detected_override=DocType.DAILY_WORK_RECORD)


def document(read, status="PASS"):
    return {"doc_type": str(DocType.DAILY_WORK_RECORD), "status": status,
            "fields": read.fields, "confidence": read.confidence,
            "image_quality": read.image_quality, "issue_date": read.issue_date}


def requirement():
    return DocRequirement(slot_key="work_proof", doc_type=DocType.DAILY_WORK_RECORD,
                          label="가짜 근로서류")


def test_observed_layout_and_short_birth_alone_do_not_reproduce_structural_failure():
    extracted, read = converted()
    assert extracted.structure_complete is True
    assert all(check.passed for check in extracted.validations)
    assert read.confidence >= .9
    assert read.fields["양식판독상태"] == "완전"
    assert "생년월일" not in read.fields
    assert read.fields.get("성명") and read.fields.get("발급일")
    assert len(json.loads(read.fields["생년월일후보"])) == 2
    identity = Identity(base.NAME, base.BIRTH)
    result = check_document(requirement(), read, identity=identity)
    assert result.status == "PASS"
    assert "REQUIRED_FIELD_UNREADABLE" not in result.codes


def test_short_birth_cli_reference_is_absent_before_followup():
    _, read = converted()
    assert _identity_from_ocr(read) is None
    program = PROGRAMS[DOUBLE_SAVINGS]
    docs = [document(read)]
    work = assess_work(program, program.announcement_date, WorkCategory.LOCAL, docs, None)
    assert work.status == "UNDETERMINED"
    assert work.reason_code == "WORK_CONTINUITY_UNDETERMINED"
    assert work.detail_codes == ["WORK_IDENTITY_UNCONFIRMED"]
    assert eligibility_blockers(program, {}, None, docs, WorkCategory.LOCAL,
                                {"announcement_date": program.announcement_date.isoformat()}) == []


def test_short_birth_with_korean_date_spaces_already_produces_candidates():
    pages = daily_short_birth()
    for _, recognized in pages:
        for word in recognized.words:
            if word.text == "90년01월01일":
                word.text = "90년 01월 01일"
    extracted, read = converted(pages)
    assert extracted.structure_complete is True
    assert "생년월일" not in read.fields
    assert len(json.loads(read.fields["생년월일후보"])) == 2

"""Source-shaped work cases connect extraction, review, officer checklist and submission blockers."""
import json
from sqlmodel import select
import pytest
from demo.backend import models
from demo.backend.api.officer import Entry,_eligibility
from demo.backend.api.review import _run_review
from demo.backend.ocr.localocr import _from_nhis,_from_supported_form
from demo.backend.rules.doc_types import DocType
from demo.backend.rules.required_docs import WorkCategory
from demo.backend.tests.test_eligibility_blockers import ready
from demo.backend.tests.test_income_review import make_application
from demo.backend.tests.test_portal_uploads import client
from engine_v2.tests import fail_case_samples as sample
from engine_v2.extractors import daily_work_record,insurance_4
from engine_v2.schemas.models import DocType as V2Type


@pytest.mark.parametrize("case",["3a","3b"])
def test_source_shaped_work_failure_reaches_all_consumers(client,case):
    app=ready(make_application(premium=1))
    if case=="3a":
        pages=sample.daily()
        read=_from_nhis(daily_work_record.extract(pages),pages,V2Type,
                        detected_override=DocType.DAILY_WORK_RECORD)
        category=WorkCategory.LOCAL
    else:
        read=_from_supported_form(insurance_4,sample.mixed_portal(),V2Type,"가짜 양식",DocType.INSURANCE_4)
        category=WorkCategory.EMPLOYEE
        assert json.loads(read.fields["추가첨부쪽"])==[2,3]
    assert read.fields["양식판독상태"]=="완전" and read.confidence>=.9
    with models.get_session() as session:
        stored=session.get(models.Application,app.id)
        stored.form1_json={**stored.form1_json,"name":sample.NAME,"birth":sample.BIRTH.isoformat()}
        stored.identity_json={"name":sample.NAME,"birth":sample.BIRTH.isoformat()}
        stored.doc_context_json={**stored.doc_context_json,"work_category":str(category)}
        docs=session.exec(select(models.Document).where(models.Document.application_id==app.id)).all()
        for doc in docs:
            fields={**doc.ocr_json["fields"],"성명":sample.NAME,"생년월일":sample.BIRTH.isoformat()}
            if doc.slot_key=="work_proof":
                doc.doc_type=doc.expected_doc_type=str(read.detected_doc_type)
                doc.ocr_json={"fields":read.fields,"confidence":read.confidence,"image_quality":read.image_quality,
                              "issue_date":read.issue_date.isoformat()}
            else:
                doc.ocr_json={**doc.ocr_json,"fields":fields}
            session.add(doc)
        session.add(stored)
        session.commit()
        session.refresh(stored)
        app=stored
    review=_run_review(app)
    assert review.final_status==review.stage2_status=="FAIL"
    work=review.review_payload_json["work_continuity"]
    assert work["status"]=="NOT_MET" and work["reason_code"]=="WORK_CONTINUITY_NOT_MET"
    if case=="3a":
        assert work["missing_months"]==["2025-11","2026-01"]
    else:
        assert "WORK_ALL_ACQUISITIONS_AFTER_START" in work["detail_codes"]
    officer=next(row for row in _eligibility(Entry(app,review),{}) if row["key"]=="work")
    assert officer["ok"] is False and officer["basis"]==work["basis"]
    final=client.get(f"/api/applications/{app.id}/final-check").json()
    item=next(item for item in final["blockers"] if item["kind"]=="eligibility" and item["target"]=="work")
    assert not final["can_submit"] and item["code"]=="WORK_CONTINUITY_NOT_MET"
    assert client.post(f"/api/applications/{app.id}/submit").status_code==400

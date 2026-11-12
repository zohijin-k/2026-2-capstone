"""Certain eligibility blockers carry public numeric evidence and are rechecked on submit."""
from datetime import date, timedelta
import json
import pytest
from sqlmodel import select
from demo.backend import models
from demo.backend.api.common import document_fact
from demo.backend.api import review as review_api
from demo.backend.rules.criteria import for_application, read_criteria
from demo.backend.rules.eligibility_blockers import eligibility_blockers
from demo.backend.rules.programs import PROGRAMS, DOUBLE_SAVINGS, JOB_PACKAGE
from demo.backend.rules.scoring import MEDIAN_INCOME_140
from demo.backend.tests.test_income_review import make_application
from demo.backend.tests.test_portal_uploads import client


def ready(app):
    program=PROGRAMS[app.program_code]
    with models.get_session() as session:
        stored=session.get(models.Application,app.id)
        stored.form1_json={**dict.fromkeys((key for key,_ in program.required_form_fields),"FAKE"),
                           **stored.form1_json,"email":"fake@example.invalid"}
        for consent in program.consent_types:
            session.add(models.Consent(application_id=app.id,consent_type=consent,agreed=True))
        session.add(stored)
        session.commit()
        session.refresh(stored)
        return stored


def blockers(app):
    with models.get_session() as session:
        docs=session.exec(select(models.Document).where(models.Document.application_id==app.id)).all()
        rows=[document_fact(doc) for doc in docs]
    return eligibility_blockers(PROGRAMS[app.program_code],app.form1_json,app.identity_json,
        rows,(app.doc_context_json or {}).get("work_category"),read_criteria(for_application(app)))


def test_confirmed_regional_excess_includes_numeric_evidence_without_scores(client):
    app=ready(make_application(premium=MEDIAN_INCOME_140[1]["지역"]+1))
    data=client.get(f"/api/applications/{app.id}/final-check").json()
    item=next(item for item in data["blockers"] if item["kind"]=="eligibility" and item["target"]=="income")
    assert not data["can_submit"]
    assert item["code"]=="OVER_LIMIT" and item["goto"]=="upload"
    assert item["evidence"]["limits_140"]=={"지역":46072}
    assert item["evidence"]["household_size"]==1 and item["evidence"]["monthly_premium"]==46073
    assert all(word in item["message"] for word in ["1명","지역","46,072","46,073","140%","2025년 10월~12월","콜센터","다시 올려"])
    assert not any(word in json.dumps(item,ensure_ascii=False) for word in ["총점","배점","tiebreak","income_percent"])
    response=client.post(f"/api/applications/{app.id}/submit")
    assert response.status_code==400


def test_submit_rechecks_income_after_a_previously_clear_final_check(client):
    app=ready(make_application(premium=1))
    assert client.get(f"/api/applications/{app.id}/final-check").json()["can_submit"] is True
    with models.get_session() as session:
        payment=session.exec(select(models.Document).where(models.Document.application_id==app.id,
                            models.Document.slot_key=="nhis_payment")).one()
        fields=dict(payment.ocr_json["fields"])
        fields["월별고지금액"]=json.dumps(dict.fromkeys(["2025-10","2025-11","2025-12"],"999999999"))
        payment.ocr_json={**payment.ocr_json,"fields":fields}
        session.add(payment)
        session.commit()
    response=client.post(f"/api/applications/{app.id}/submit")
    assert response.status_code==400
    assert "소득" in response.json()["detail"]
    with models.get_session() as session:
        assert session.get(models.Application,app.id).status==models.STATUS_DRAFT
        assert session.exec(select(models.Review).where(models.Review.application_id==app.id)).first() is None


def test_age_outside_range_has_same_early_reason_and_final_blocker(client):
    aid=client.post("/api/applications",json={"program_code":DOUBLE_SAVINGS}).json()["id"]
    birth=(PROGRAMS[DOUBLE_SAVINGS].birth_range[0]-timedelta(days=1)).isoformat()
    payload={"name":"가짜신청","birth":birth,"phone":"01000000000","pledge":True,
             "signature_data_url":"data:image/png;base64,aW52ZW50ZWQtc2lnbmF0dXJl"}
    response=client.post(f"/api/applications/{aid}/identity",json=payload)
    assert response.status_code==200
    item=response.json()["eligibility_blockers"][0]
    assert item["code"]=="AGE_OUT_OF_RANGE"
    assert birth in item["message"]
    assert all(value.isoformat() in item["message"] for value in PROGRAMS[DOUBLE_SAVINGS].birth_range)
    assert client.get(f"/api/applications/{aid}").json()["eligibility_blockers"]==[item]
    assert client.get(f"/api/applications/{aid}/status").json()["eligibility_blockers"]==[item]
    final=client.get(f"/api/applications/{aid}/final-check").json()
    assert item in final["blockers"] and not final["can_submit"]
    assert client.post(f"/api/applications/{aid}/submit").status_code==400


def test_work_not_met_blocks_final_and_direct_submit(client):
    app=ready(make_application(premium=1))
    with models.get_session() as session:
        doc=session.exec(select(models.Document).where(models.Document.application_id==app.id,
                        models.Document.slot_key=="work_proof")).one()
        fields=dict(doc.ocr_json["fields"])
        rows=json.loads(fields["가입내역"])
        for row in rows:
            if row["상태"]=="가입":
                row["자격취득일"]="2026-01-01"
        fields["가입내역"]=json.dumps(rows,ensure_ascii=False)
        doc.ocr_json={**doc.ocr_json,"fields":fields}
        session.add(doc)
        session.commit()
    data=client.get(f"/api/applications/{app.id}/final-check").json()
    item=next(item for item in data["blockers"] if item["kind"]=="eligibility" and item["target"]=="work")
    assert not data["can_submit"]
    assert item["evidence"]["status"]=="NOT_MET"
    assert all(value in item["message"] for value in ["2025-10-03","2026-03-03","2026-01-01","콜센터"])
    assert client.post(f"/api/applications/{app.id}/submit").status_code==400


@pytest.mark.parametrize("problem",["untrusted","missing-month","no-household"])
def test_undetermined_income_remains_submittable_for_officer_review(client,problem):
    app=ready(make_application(premium=1,payment_problem=problem))
    assert blockers(app)==[]
    assert client.get(f"/api/applications/{app.id}/final-check").json()["can_submit"] is True
    assert client.post(f"/api/applications/{app.id}/submit").status_code==200


def test_no_work_or_income_requirement_has_no_savings_blockers(client):
    app=make_application(program_code=JOB_PACKAGE,premium=999999999)
    assert blockers(app)==[]


def test_unknown_work_remains_submittable_and_final_review_is_consistent(client):
    app=ready(make_application(premium=1))
    with models.get_session() as session:
        doc=session.exec(select(models.Document).where(models.Document.application_id==app.id,
                        models.Document.slot_key=="work_proof")).one()
        fields=dict(doc.ocr_json["fields"])
        fields.pop("가입내역")
        doc.ocr_json={**doc.ocr_json,"fields":fields}
        session.add(doc)
        session.commit()
    data=client.get(f"/api/applications/{app.id}/final-check").json()
    assert data["can_submit"] is True
    assert not any(item["kind"]=="eligibility" for item in data["blockers"])
    assert client.post(f"/api/applications/{app.id}/submit").status_code==200
    with models.get_session() as session:
        reviewed=session.exec(select(models.Review).where(models.Review.application_id==app.id)).one()
        assert reviewed.final_status=="NEEDS_REVIEW"
        assert reviewed.review_payload_json["work_continuity"]["status"]=="UNDETERMINED"


@pytest.mark.parametrize("kind",["age","work"])
def test_submit_rechecks_other_eligibility_after_clear_final_check(client,kind):
    app=ready(make_application(premium=1))
    assert client.get(f"/api/applications/{app.id}/final-check").json()["can_submit"] is True
    with models.get_session() as session:
        if kind=="age":
            stored=session.get(models.Application,app.id)
            birth=(PROGRAMS[DOUBLE_SAVINGS].birth_range[0]-timedelta(days=1)).isoformat()
            stored.form1_json={**stored.form1_json,"birth":birth}
            stored.identity_json={**stored.identity_json,"birth":birth}
            session.add(stored)
        else:
            stored=session.exec(select(models.Document).where(models.Document.application_id==app.id,
                                models.Document.slot_key=="work_proof")).one()
            fields=dict(stored.ocr_json["fields"])
            rows=json.loads(fields["가입내역"])
            for row in rows:
                row["자격취득일"]="2026-01-01"
            fields["가입내역"]=json.dumps(rows,ensure_ascii=False)
            stored.ocr_json={**stored.ocr_json,"fields":fields}
            session.add(stored)
        session.commit()
    response=client.post(f"/api/applications/{app.id}/submit")
    assert response.status_code==400
    assert ("연령" if kind=="age" else "근로") in response.json()["detail"]


def test_program_without_configured_call_center_uses_public_contact_page(client):
    from demo.backend.rules.eligibility_blockers import age_blockers
    program=PROGRAMS[JOB_PACKAGE]
    birth=(program.birth_range[0]-timedelta(days=1)).isoformat()
    message=age_blockers(program,{"birth":birth},{"birth":birth})[0]["message"]
    assert program.site_url in message
    assert "콜센터 연락처" in message
    assert "콜센터 ." not in message

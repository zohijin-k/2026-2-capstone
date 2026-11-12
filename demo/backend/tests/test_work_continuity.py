"""Fictitious complete work evidence exercises provisional five-month coverage."""
from dataclasses import replace
from datetime import date
import json

import pytest
from sqlmodel import select

from demo.backend import models
from demo.backend.api.officer import Entry, _eligibility
from demo.backend.api.review import _run_review
from demo.backend.rules.doc_types import DocType
from demo.backend.rules.programs import PROGRAMS, DOUBLE_SAVINGS, JOB_PACKAGE
from demo.backend.rules.required_docs import WorkCategory
from demo.backend.rules.work_continuity import assess_work
from demo.backend.tests.test_income_review import isolated_db, make_application


PROGRAM = PROGRAMS[DOUBLE_SAVINGS]
NOTICE = date(2026,3,3)
IDENTITY = {"name":"가상근로","birth":"1990-01-01"}


def proof(kind, extra=None):
    return {"document_id":0,"doc_type":str(kind),"status":"PASS","confidence":.97,"image_quality":.95,
            "issue_date":NOTICE,"fields":{"성명":"가상근로","생년월일":"1990-01-01",
            "발급일":NOTICE.isoformat(),"양식판독상태":"완전",**(extra or {})}}


def insurance(acquired="2025-10-03"):
    rows = [{"보험":kind,"성명":"가상근로","가입자종별":category,"상태":"가입","자격취득일":acquired}
            for kind,category in (("국민연금","사업장가입자"),("건강보험","직장가입자"),
                                  ("고용보험","근로자"),("산재보험","근로자"))]
    return proof(DocType.INSURANCE_4,{"가입내역":json.dumps(rows,ensure_ascii=False)})


def daily(months=None, period=None):
    months = months if months is not None else ["2025-10","2025-11","2025-12","2026-01","2026-02"]
    return proof(DocType.DAILY_WORK_RECORD,{"일용근로내역자료":json.dumps({
        "period":period or ["2025-10","2026-03"],"copies_consistent":True,
        "rows":[{"month":month,"workplace":"가짜사업장","work_dates":[1],"days":1,
                 "wage":100000,"remuneration":100000,"worker_category":"근로자"} for month in months]},ensure_ascii=False)})


def history(intervals, full=True):
    return proof(DocType.NHIS_ACQUISITION_LOSS,{"자격이력자료":json.dumps({"period":None,
        "coverage_basis":"full_history" if full else "undetermined",
        "rows":[{"category":"직장","acquired":a,"lost":b} for a,b in intervals]})})


def assess(*docs, category=WorkCategory.EMPLOYEE, program=PROGRAM, identity=IDENTITY):
    return assess_work(program,NOTICE,category,list(docs),identity)


@pytest.mark.parametrize("acquired,expected",[("2020-01-01","MET"),("2025-10-03","MET"),("2025-10-04","NOT_MET")])
def test_full_current_insurance_rows_enforce_inclusive_start(acquired,expected):
    result = assess(insurance(acquired))
    assert result.status==expected
    assert result.period_start==date(2025,10,3) and result.period_end==NOTICE
    assert result.provisional
    assert acquired in result.basis
    assert result.review_status==("FAIL" if expected=="NOT_MET" else "PASS")


@pytest.mark.parametrize("defect",["summary-only","bad-json","row-name","missing-row","identity-name","identity-birth",
                                    "low-confidence","nan-confidence","bool-confidence","bad-quality","low-quality",
                                    "incomplete","failed-check","early-issue","review-status","invalid-date"])
def test_uncertain_insurance_evidence_never_rejects(defect):
    doc=insurance("2026-01-01")
    fields=doc["fields"]
    if defect=="summary-only":
        fields.pop("가입내역");fields["근로관련최초취득일"]="2026-01-01"
    elif defect=="bad-json":fields["가입내역"]="FAKE"
    elif defect in {"row-name","missing-row"}:
        rows=json.loads(fields["가입내역"])
        if defect=="row-name":rows[2]["성명"]="가상다름"
        else:rows.pop()
        fields["가입내역"]=json.dumps(rows)
    elif defect=="identity-name":fields["성명"]="가상다름"
    elif defect=="identity-birth":fields["생년월일"]="1991-01-01"
    elif defect in {"low-confidence","nan-confidence","bool-confidence"}:
        doc["confidence"]={"low-confidence":.4,"nan-confidence":float("nan"),"bool-confidence":True}[defect]
    elif defect in {"bad-quality","low-quality"}:doc["image_quality"]="FAKE" if defect=="bad-quality" else .5
    elif defect=="incomplete":fields["양식판독상태"]="불완전"
    elif defect=="failed-check":fields["판독검증실패"]="date_formats"
    elif defect=="early-issue":doc["issue_date"]=date(2026,3,2)
    elif defect=="review-status":doc["status"]="NEEDS_REVIEW"
    else:fields["가입내역"]=fields["가입내역"].replace("2026-01-01","2026-99-99")
    result=assess(doc)
    assert result.status=="UNDETERMINED" and result.review_status=="NEEDS_REVIEW"
    assert result.reason_code=="WORK_CONTINUITY_UNDETERMINED"


def test_missing_reference_identity_is_unknown():
    assert assess(insurance("2026-01-01"),identity=None).status=="UNDETERMINED"


@pytest.mark.parametrize("acquired",["2020-01-01","2026-01-01"])
def test_fresh_insurance_low_confidence_date_cannot_prove_positive_or_negative(acquired):
    doc=insurance(acquired);rows=json.loads(doc["fields"]["가입내역"])
    for row in rows:row["자격취득일신뢰도"]=.4
    doc["fields"]["가입내역"]=json.dumps(rows)
    assert assess(doc).status=="UNDETERMINED"


def test_fresh_history_unreadable_date_confidence_prevents_gap_rejection():
    doc=history([("2020-01-01","2026-01-01"),("2026-01-02",None)])
    data=json.loads(doc["fields"]["자격이력자료"])
    data["rows"][0]["lost_confidence"]=.4
    doc["fields"]["자격이력자료"]=json.dumps(data)
    assert assess(doc).status=="UNDETERMINED"


@pytest.mark.parametrize("gap,expected",[(False,"MET"),(True,"NOT_MET")])
def test_full_history_requires_next_acquisition_no_later_than_previous_loss(gap,expected):
    result=assess(history([("2020-01-01","2026-01-01"),("2026-01-02" if gap else "2026-01-01",None)]))
    assert result.status==expected
    assert ("WORK_HISTORY_GAP" in result.detail_codes) is gap
    assert "2026-01-01" in result.basis


def test_partial_history_cannot_prove_a_gap_and_ongoing_interval_can_prove_positive():
    assert assess(history([("2025-11-01",None)],full=False)).status=="UNDETERMINED"
    assert assess(history([("2020-01-01",None)],full=False)).status=="MET"
    assert assess(history([("2020-01-01","2026-03-03")])).status=="NOT_MET"


def test_equal_acquisition_dates_do_not_crash_and_unknown_category_stays_unknown():
    assert assess(history([("2020-01-01",None),("2020-01-01","2021-01-01")])).status=="UNDETERMINED"
    doc=history([("2025-11-01",None)])
    data=json.loads(doc["fields"]["자격이력자료"]);data["rows"][0]["category"]="FAKE"
    doc["fields"]["자격이력자료"]=json.dumps(data)
    assert assess(doc).status=="UNDETERMINED"


@pytest.mark.parametrize("missing",[None,"2025-11","2026-01"])
def test_daily_needs_one_day_in_each_required_month_and_not_march(missing):
    doc=daily()
    data=json.loads(doc["fields"]["일용근로내역자료"])
    if missing:data["rows"]=[row for row in data["rows"] if row["month"]!=missing]
    doc["fields"]["일용근로내역자료"]=json.dumps(data)
    result=assess(doc,category=WorkCategory.LOCAL)
    assert result.status==("NOT_MET" if missing else "MET")
    assert result.missing_months==([missing] if missing else [])
    if missing:assert missing in result.basis


@pytest.mark.parametrize("period",[["2025-11","2026-03"],["2025-10","2026-02"]])
def test_daily_insufficient_query_is_certain_with_reissue_guidance(period):
    months=[m for m in ["2025-10","2025-11","2025-12","2026-01","2026-02"] if period[0]<=m<=period[1]]
    result=assess(daily(months,period),category=WorkCategory.LOCAL)
    assert result.status=="NOT_MET"
    assert result.detail_codes==["WORK_DAILY_QUERY_PERIOD_TOO_SHORT"]
    assert "조회기간" in result.basis and "다시 발급" in result.basis


@pytest.mark.parametrize("defect",["missing-period","copies","bad-day-count","invalid-day","missing-table"])
def test_daily_uncertain_structure_is_review(defect):
    doc=daily();data=json.loads(doc["fields"]["일용근로내역자료"])
    if defect=="missing-period":data.pop("period")
    elif defect=="copies":data["copies_consistent"]=False
    elif defect=="bad-day-count":data["rows"][0]["days"]=5
    elif defect=="invalid-day":data["rows"][0]["work_dates"]=[99]
    else:data.pop("rows")
    doc["fields"]["일용근로내역자료"]=json.dumps(data)
    assert assess(doc,category=WorkCategory.LOCAL).status=="UNDETERMINED"


def test_daily_two_digit_birth_candidates_match_only_verified_birth():
    doc=daily();doc["fields"].pop("생년월일")
    doc["fields"]["생년월일후보"]=json.dumps(["1990-01-01","2090-01-01"])
    assert assess(doc,category=WorkCategory.LOCAL).status=="MET"
    assert assess(doc,category=WorkCategory.LOCAL,identity={**IDENTITY,"birth":"1991-01-01"}).status=="UNDETERMINED"


@pytest.mark.parametrize("opened,status,expected",[("2025-09-03",None,"MET"),("2025-09-04",None,"NOT_MET"),
                                                  ("2020-01-01","휴업","NOT_MET"),("2020-01-01","폐업","NOT_MET"),
                                                  ("FAKE",None,"UNDETERMINED")])
def test_business_opening_and_explicit_status(opened,status,expected):
    fields={"개업일":opened}
    if status:fields["사업자상태"]=status
    assert assess(proof(DocType.BIZ_REG_PROOF,fields),category=WorkCategory.BUSINESS).status==expected


def test_valid_looking_low_confidence_late_business_opening_requires_review():
    from engine_v2.extractors import business_registration
    from engine_v2.tests import p2_business_samples as sample
    from demo.backend.ocr.localocr import _from_business_proof
    cells,size=sample.business(noise=False)
    cells=[(*cell[:4],"2026년 01월 02일",.4) if cell[4]=="2018년 01월 02일" else cell for cell in cells]
    pages=[sample.page(cells,size=size)]
    extracted=business_registration.extract(pages,today=date(2026,3,4))
    assert extracted.structure_complete and extracted.fields["개업일"].confidence==.4
    converted=_from_business_proof(extracted,pages)
    doc={"doc_type":str(DocType.BIZ_REG_PROOF),"status":"NEEDS_REVIEW","confidence":converted.confidence,
         "image_quality":converted.image_quality,"issue_date":converted.issue_date,"fields":converted.fields}
    result=assess_work(PROGRAM,NOTICE,WorkCategory.BUSINESS,[doc],{"name":sample.NAME,"birth":"1990-01-01"})
    assert result.status=="UNDETERMINED" and converted.confidence==.4


def test_conflicting_documents_go_to_review_and_unknown_extra_cannot_erase_certain_result():
    negative=insurance("2026-01-01")
    result=assess(negative,history([("2020-01-01",None)]))
    assert result.status=="UNDETERMINED" and result.detail_codes==["WORK_DOCUMENTS_CONFLICT"]
    assert len(result.evidence)==2
    assert assess(negative,proof(DocType.LABOR_CONTRACT)).status=="NOT_MET"


def test_no_requirement_has_no_effect_and_policy_months_have_one_setting():
    result=assess(insurance("2026-01-01"),program=PROGRAMS[JOB_PACKAGE])
    assert result.status=="MET" and result.period_start is None and not result.provisional
    assert assess(program=replace(PROGRAM,work_continuity_months=6)).period_start==date(2025,9,3)
    value=assess_work(PROGRAM,date(2026,3,31),WorkCategory.EMPLOYEE,[],IDENTITY)
    assert value.period_start==date(2025,10,31)
    assert json.loads(json.dumps(value.as_dict()))["status"]=="UNDETERMINED"


def test_review_and_officer_share_work_failure_and_keep_score_points_independent(isolated_db):
    app=make_application(premium=0)
    with models.get_session() as session:
        doc=session.exec(select(models.Document).where(models.Document.application_id==app.id,
                         models.Document.doc_type==str(DocType.INSURANCE_4))).one()
        data={**doc.ocr_json,"fields":dict(doc.ocr_json["fields"])}
        data["fields"]["가입내역"]=data["fields"]["가입내역"].replace("2020-01-01","2026-01-01")
        doc.ocr_json=data;session.add(doc);session.commit()
    review=_run_review(app)
    work=review.review_payload_json["work_continuity"]
    assert review.final_status==review.stage2_status=="FAIL"
    assert work["status"]=="NOT_MET" and work["reason_code"]=="WORK_CONTINUITY_NOT_MET"
    assert next(item for item in review.score_json["items"] if item["key"]=="work")["score"]>0
    check=next(item for item in _eligibility(Entry(app,review),{}) if item["key"]=="work")
    assert check["ok"] is False and check["basis"]==work["basis"]

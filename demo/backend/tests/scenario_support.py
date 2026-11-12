"""Explicit synthetic evidence and historical seeds for legacy scenario coverage.

These helpers never alter production rules or turn a blocked API request into a
successful submission. Historical officer fixtures are stored only after the
scenario has observed the current submit rejection and absence of a Review.
"""
from datetime import datetime
import json

from sqlmodel import select

from .. import models
from ..rules.doc_types import DocType
from ..rules.facts import parse_ymd


def complete_synthetic_work(application_id: int) -> None:
    """Upgrade old authored PASS fixtures with verified identity and full rows."""
    with models.get_session() as session:
        application=session.get(models.Application,application_id)
        assert application is not None
        form=application.form1_json or {}
        birth=parse_ymd(form.get("birth"))
        assert birth is not None
        name=str(form["name"])
        application.identity_json={**(application.identity_json or {}),"name":name,"birth":birth.isoformat()}
        session.add(application)
        for document in session.exec(select(models.Document).where(models.Document.application_id==application_id)).all():
            if document.doc_type!=str(DocType.INSURANCE_4) or document.stage1_status!="PASS":
                continue
            rows=[{"보험":insurance,"성명":name,"가입자종별":category,"상태":"가입",
                   "자격취득일":"2020-01-01","자격취득일신뢰도":1,
                   "사업장관리번호":"00000000000","사업장명칭":"FAKE 합성사업장"}
                  for insurance,category in (("국민연금","사업장가입자"),("건강보험","직장가입자"),
                                              ("산재보험","근로자"),("고용보험","근로자"))]
            ocr=dict(document.ocr_json or {})
            fields={**(ocr.get("fields") or {}),"성명":name,"생년월일":birth.isoformat(),
                    "양식판독상태":"완전","가입내역":json.dumps(rows,ensure_ascii=False)}
            fields.pop("판독검증실패",None)
            document.ocr_json={**ocr,"fields":fields,"confidence":.97,"image_quality":.95}
            session.add(document)
        session.commit()


def seed_blocked_historical_review(application_id: int, blocked_response):
    """Store an explicitly historical officer fixture after proving API blocks."""
    assert blocked_response.status_code==400
    with models.get_session() as session:
        application=session.get(models.Application,application_id)
        assert application is not None and application.status==models.STATUS_DRAFT
        assert session.exec(select(models.Review).where(models.Review.application_id==application_id)).first() is None
    from ..api.review import _run_review
    review=_run_review(application)
    review.review_payload_json={**(review.review_payload_json or {}),"synthetic_historical_fixture":True}
    with models.get_session() as session:
        application=session.get(models.Application,application_id)
        assert application is not None
        application.status=models.STATUS_SUBMITTED
        application.submitted_at=datetime.now()
        application.updated_at=application.submitted_at
        session.add(application)
        session.add(review)
        session.commit()
        session.refresh(review)
    return review

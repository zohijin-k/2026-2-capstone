"""취업지원패키지 규칙팩 초안 시험. 모든 인물·상호·번호는 가상 값이다."""
from datetime import date

from ..engine import EXTRACTORS, evaluate_document, load_rulepack
from ..rules.registry import RULES
from ..schemas.models import (ApplicantInput, ApplicationInput, DocType, DocumentInput, ProgramId, Verdict)
from .test_exam_docs import admission_words
from .test_exam_docs import page as exam_page
from .test_receipt import card_slip_words
from .test_receipt import page as receipt_page

TODAY = date(2026, 11, 11)
CRITERIA = {"document_issue_fallback": {"mode": "after_date", "date": "2026-01-01"}}


def _app(doc_type: DocType) -> ApplicationInput:
    return ApplicationInput(
        application_id="job-test", program_id=ProgramId.JOB_PACKAGE, announcement_date=date(2026, 2, 2),
        applicant=ApplicantInput(name="김가상", birth_date=date(1999, 1, 1)),
        documents=[DocumentInput(doc_id="d1", declared_type=doc_type, file_path="synthetic")],
        criteria=CRITERIA,
    )


def _evaluate(doc_type: DocType, pages):
    app = _app(doc_type)
    return evaluate_document(app.documents[0], pages, app, load_rulepack("job_package"), TODAY)


def test_rulepack_uses_only_implemented_rules_and_known_documents():
    pack = load_rulepack("job_package")
    for doc_name, spec in pack["documents"].items():
        assert DocType(doc_name) in EXTRACTORS or DocType(doc_name) == DocType.RESIDENT_ABSTRACT
        for rule in spec["rules"]:
            assert rule["type"] in RULES, rule["id"]


def test_readable_receipt_paid_this_year_is_suitable():
    result = _evaluate(DocType.RECEIPT, [receipt_page(card_slip_words())])
    assert result.verdict == Verdict.SUITABLE, result.review_reasons


def test_receipt_paid_before_support_year_is_unsuitable():
    words = card_slip_words()
    next(word for word in words if word.text == "26/03/15").text = "25/12/30"
    result = _evaluate(DocType.RECEIPT, [receipt_page(words)])
    assert result.verdict == Verdict.UNSUITABLE


def test_unread_exam_date_goes_to_review_not_unsuitable():
    result = _evaluate(DocType.EXAM_ADMISSION, [exam_page(admission_words(exam_date=""))])
    assert result.verdict == Verdict.NEEDS_REVIEW


def test_score_report_in_admission_slot_is_accepted():
    words = admission_words()
    next(word for word in words if word.text == "응 시 확 인 서").text = "성 적 통 지 서"
    result = _evaluate(DocType.EXAM_ADMISSION, [exam_page(words)])
    assert result.verdict == Verdict.SUITABLE, result.review_reasons

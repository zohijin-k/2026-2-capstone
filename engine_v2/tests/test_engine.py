"""규칙 실행기 + 판정 테스트 (가짜 초본, 개인정보 없음).

  python -m tests.test_engine
"""

from __future__ import annotations

from datetime import date

from engine import combine, evaluate_document, load_rulepack
from schemas.models import (ApplicantInput, ApplicationInput, CheckStatus, DocType, DocumentInput,
                            Verdict)
from tests.test_resident_abstract import build

TODAY = date(2026, 11, 10)
RP = load_rulepack("doubling_savings")


def app(name="김전북", birth=date(1999, 1, 1), issue="2026-11-10", announce=date(2026, 11, 1)):
    doc = DocumentInput(doc_id="d1", declared_type=DocType.RESIDENT_ABSTRACT, file_path="-",
                        declared_values={"issue_date": issue})
    return ApplicationInput(application_id="A-001", program_id="doubling_savings", announcement_date=announce,
                            applicant=ApplicantInput(name=name, birth_date=birth), documents=[doc])


def evaluate(a, pages=None):
    d = evaluate_document(a.documents[0], pages or build(), a, RP, today=TODAY)
    return d, combine(a, [d], RP)


def statuses(d):
    return {c.rule_id: c.status for c in d.checks}


def test_all_pass():
    d, res = evaluate(app())
    assert all(s == CheckStatus.PASS for s in statuses(d).values()), statuses(d)
    assert d.verdict == Verdict.SUITABLE and res.status == Verdict.SUITABLE


def test_wrong_issue_date_input():
    d, res = evaluate(app(issue="2026-11-09"))
    assert statuses(d)["abstract.issue_date_matches_input"] == CheckStatus.FAIL
    assert res.status == Verdict.UNSUITABLE
    msgs = res.to_applicant_view().documents[0].messages
    assert msgs == ["입력하신 발급일과 서류의 발급일이 달라요. 발급일을 다시 확인해 주세요."]


def test_name_mismatch():
    d, _ = evaluate(app(name="이익산"))
    assert statuses(d)["abstract.name_matches"] == CheckStatus.FAIL


def test_too_old_for_program():
    d, _ = evaluate(app(birth=date(1980, 1, 1)))     # 입력도 서류와 다르게 → 두 규칙 모두 실패
    assert statuses(d)["abstract.birth_matches"] == CheckStatus.FAIL


def test_register_instead_of_abstract():
    d, res = evaluate(app(), build(title="등 본"))
    assert statuses(d)["abstract.doc_type"] == CheckStatus.FAIL
    assert d.verdict == Verdict.UNSUITABLE
    assert "초본" in res.to_applicant_view().documents[0].messages[0]


def test_low_confidence_fail_goes_to_review():
    """OCR이 한 쪽 발급일을 잘못 읽어 신뢰도가 낮은 상태 → 신청자에게 '틀렸다' 단정하지 않고 담당자에게."""
    pages = build()
    for w in pages[1][1].words:
        if "년" in w.text and "월" in w.text:
            w.text = "2026년 11월 18일"
    d, res = evaluate(app(issue="2026-11-18"), pages)   # 신청자는 11-18로 입력, 서류 다수결은 11-10
    assert statuses(d)["abstract.issue_date_matches_input"] == CheckStatus.FAIL
    assert d.verdict == Verdict.NEEDS_REVIEW
    assert res.to_applicant_view().documents[0].messages == ["담당자가 확인한 뒤 결과를 알려드릴게요."]


def test_applicant_view_has_no_internal_values():
    _, res = evaluate(app(issue="2026-11-09"))
    view = res.to_applicant_view().model_dump_json()
    for leak in ("confidence", "internal", "reviewer", "max_days", "30", "1999"):
        assert leak not in view, leak


def test_reviewer_message_filled():
    d, _ = evaluate(app())
    m = {c.rule_id: c.reviewer_message for c in d.checks}
    assert "38개월" in m["abstract.residence_period"] or "35개월" in m["abstract.residence_period"]
    assert "{" not in "".join(m.values())


def test_missing_document():
    a = app()
    a.documents = []
    res = combine(a, [], RP)
    assert res.status == Verdict.UNSUITABLE and res.missing_doc_types == [DocType.RESIDENT_ABSTRACT]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)

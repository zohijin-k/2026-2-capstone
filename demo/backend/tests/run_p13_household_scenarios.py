"""P13 — 자격확인서 가구원 수만 소득 판정에 쓰고 겹치는 가구는 재검토한다."""

from __future__ import annotations

import json
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from sqlmodel import select

from . import run_p4_scenarios as p4
from .. import models
from ..api.review import _link_overlapping_households
from ..models import Application, Document, Review, get_session
from ..ocr.pdftext import extract_household_size
from ..rules.doc_types import DocType
from ..rules.facts import build_facts
from ..rules.programs import DOUBLE_SAVINGS
from ..rules.scoring import income_percent, score_application

_passed = 0
_failed: list[str] = []


def check(name: str, actual: object, expected: object) -> None:
    global _passed
    if actual == expected:
        _passed += 1
        print(f"  [OK]   {name}: {actual}")
    else:
        _failed.append(name)
        print(f"  [FAIL] {name}: 기대={expected!r} 실제={actual!r}")


def check_true(name: str, value: object) -> None:
    check(name, bool(value), True)


def qualification(fields: dict) -> dict:
    return {"doc_type": str(DocType.NHIS_QUALIFICATION), "fields": fields}


def test_household_source_and_income_review() -> None:
    print("\n[1] 소득 가구원 수는 자격확인서만 사용")
    missing = build_facts(
        {"householdSize": "4인"},
        [{"doc_type": str(DocType.NHIS_PAYMENT), "fields": {"건강보험료": "100000", "월별고지금액": json.dumps({month: "100000" for month in ("2025-10", "2025-11", "2025-12")})}}],
    )
    check("자격확인서 없음 → 신청서 입력값 미사용", missing.household_size, None)
    check("미확인 사유", missing.household_size_issue,
          "건강보험 자격확인서에서 가구원 수를 확인하지 못했습니다.")
    missing_sheet = score_application(
        missing, announcement_date=datetime(2026, 3, 3).date(),
        age_basis_date=datetime(2025, 12, 31).date(),
    )
    check_true("미판독 소득 항목은 판정 불가", missing_sheet.items[0].incomplete)
    check_true("미판독 사유가 심사표에 기록", "건강보험 자격확인서에서 가구원 수를 확인하지 못했습니다." in missing_sheet.items[0].basis)

    members = [
        {"성명": "가상가구원1", "생년월일": "1990-01-01"},
        {"성명": "가상가구원2", "생년월일": "1992-02-02"},
        {"성명": "가상가구원3", "생년월일": "1994-03-03"},
    ]
    form_four = {"householdSize": "4인"}
    facts = build_facts(form_four, [qualification({"가구원목록": json.dumps(members), "가입구분": "직장"}),
                                    {"doc_type": str(DocType.NHIS_PAYMENT), "fields": {"건강보험료": "100000", "월별고지금액": json.dumps({month: "100000" for month in ("2025-10", "2025-11", "2025-12")})}}])
    check("신청서 4명, 자격확인서 목록 3명 → 판정은 3명", facts.household_size, 3)
    check("신청서 값 차이 참고 기록", facts.household_size_form_mismatch, (4, 3))
    check_true("담당자 근거에 신청서 입력과 인증서 출처", "신청서 입력 4명" in facts.source("income").origin)
    score = score_application(
        facts, announcement_date=datetime(2026, 3, 3).date(),
        age_basis_date=datetime(2025, 12, 31).date(),
    )
    check("중위소득 계산은 3인 기준", score.income_percent, round(income_percent(3, 100000, "직장")[0], 1))
    check_true("심사표에 신청서와 인증서 차이 기록", any("신청서 입력 가구원수 4명" in note for note in score.notes))

    conflict = build_facts({}, [qualification({"가구원수": "4", "가구원목록": json.dumps(members)})])
    check("목록 3명·표기 4명 → 소득 수 미확정", conflict.household_size, None)
    check_true("목록·표기 충돌 사유", bool(conflict.household_size_issue))
    check("등본 표현 세대원수는 미판독", extract_household_size("세대원수 4"), None)


def test_missing_household_forces_review() -> None:
    print("\n[1-2] 가구원 수 판독 실패 시 소득은 담당자 재검토")
    models.init_db()
    app = Application(
        application_no="P13-MISSING",
        program_code=DOUBLE_SAVINGS,
        status="draft",
        form1_json={"householdSize": "4인", "birth": "1999-01-01"},
        created_at=datetime(2026, 2, 1),
    )
    with get_session() as session:
        session.add(app)
        session.commit()
        session.refresh(app)

    from ..api import review as review_api
    from engine.models import Status

    old_runner = review_api.run_pipeline
    review_api.run_pipeline = lambda *_args, **_kwargs: SimpleNamespace(
        status=Status.PASS,
        stage1=SimpleNamespace(status=Status.PASS),
        stage2=SimpleNamespace(status=Status.PASS),
        review_payload=None,
    )
    try:
        result = review_api._run_review(app)
    finally:
        review_api.run_pipeline = old_runner

    check("소득 가구원 수 판독 실패 → 최종 재검토", result.final_status, "NEEDS_REVIEW")
    check("소득 단계 재검토", result.stage2_status, "NEEDS_REVIEW")
    reasons = result.review_payload_json.get("reasons", [])
    check_true("담당자 사유 문구", any(
        row.get("message") == "건강보험 자격확인서에서 가구원 수를 확인하지 못했습니다."
        for row in reasons
    ))


def test_scenario_package_creates_missing_samples(tmp: Path) -> None:
    print("\n[1-3] 시연 샘플이 없으면 테스트 시작 전에 생성")
    import demo.backend.tests as test_package
    import demo.fixtures.make_samples as sample_builder

    sample_dir = tmp / "auto-samples"
    old_samples_dir = test_package.SAMPLES_DIR
    old_generator = sample_builder.main
    calls = []

    def fake_make_samples() -> None:
        calls.append(True)
        sample_dir.mkdir(parents=True, exist_ok=True)
        (sample_dir / "synthetic.pdf").write_bytes(b"synthetic")

    test_package.SAMPLES_DIR = sample_dir
    sample_builder.main = fake_make_samples
    try:
        test_package.ensure_demo_samples()
        check("없는 샘플 경로에서 생성기를 호출", calls, [True])
        check_true("샘플 파일 생성", (sample_dir / "synthetic.pdf").is_file())
    finally:
        test_package.SAMPLES_DIR = old_samples_dir
        sample_builder.main = old_generator


def _add_app(
    app_no: str, *, year: int, status: str, members: list[dict[str, str]],
    program: str = DOUBLE_SAVINGS, address: str = "임의 주소 A",
) -> Application:
    app = Application(
        application_no=app_no,
        program_code=program,
        status=status,
        form1_json={"address": address, "householdSize": "4인"},
        created_at=datetime(year, 2, 1),
    )
    models.init_db()
    with get_session() as session:
        session.add(app)
        session.commit()
        session.refresh(app)
        session.add(Document(
            application_id=app.id or 0,
            slot_key="nhis_qualification",
            doc_type=str(DocType.NHIS_QUALIFICATION),
            expected_doc_type=str(DocType.NHIS_QUALIFICATION),
            file_path=f"/fake/{app_no}.pdf",
            file_format="pdf",
            ocr_json={"confidence": .95, "fields": {"가구원목록": json.dumps(members, ensure_ascii=False)}},
            stage1_status="PASS",
        ))
        session.add(Review(
            application_id=app.id or 0,
            final_status="PASS",
            stage1_status="PASS",
            stage2_status="PASS",
            review_payload_json={"reasons": [], "related_applications": []},
            officer_role="province",
            officer_decision="approve",
        ))
        session.commit()
        session.refresh(app)
    return app


def test_overlapping_households_link_both_applications(tmp: Path) -> None:
    print("\n[2] 같은 사업·연도 가구원 중복은 양쪽 재검토로 연결")
    first_members = [
        {"성명": "가상공통인물", "생년월일": "1980-01-02"},
        {"성명": "가상첫번째", "생년월일": "2000-02-03"},
    ]
    second_members = [
        {"성명": "가상공통인물", "생년월일": "1980-01-02"},
        {"성명": "가상두번째", "생년월일": "2002-04-05"},
    ]
    previous = _add_app("P13-A", year=2026, status="submitted", members=first_members, address="주소 A")
    _add_app("P13-B", year=2025, status="submitted", members=second_members)
    _add_app("P13-C", year=2026, status="submitted", members=second_members, program="job_package")
    _add_app("P13-E", year=2026, status="submitted", members=[
        {"성명": "가상공통인물", "생년월일": "1980-01-03"},
        {"성명": "가상다른사람", "생년월일": "2003-04-05"},
    ])
    current = _add_app("P13-D", year=2026, status="draft", members=second_members, address="주소 Z")
    current_review = Review(
        application_id=current.id or 0,
        final_status="PASS",
        stage1_status="PASS",
        stage2_status="PASS",
        review_payload_json={"reasons": [], "related_applications": []},
    )

    _link_overlapping_households(current, current_review)

    check("신청서 A가 재검토로 변경", _review_status(previous.id or 0), "NEEDS_REVIEW")
    check("새 신청서 재검토", current_review.final_status, "NEEDS_REVIEW")
    previous_payload = _review_payload(previous.id or 0)
    current_links = current_review.review_payload_json["related_applications"]
    check("성명만 같고 생년월일이 다르면 연결 안 함", [row["application_no"] for row in current_links], ["P13-A"])
    check("양쪽 신청서 링크 상호 참조", current_links[0]["application_no"], "P13-A")
    check("이전 신청서도 새 신청서 링크", previous_payload["related_applications"][0]["application_no"], "P13-D")
    check("겹친 가구원만 근거에 포함", current_review.review_payload_json["household_overlap_details"][0]["members"], [first_members[0]])
    check("주소는 비교 근거에 포함 안 됨", "주소" in json.dumps(current_review.review_payload_json, ensure_ascii=False), False)

    from ..api import review as review_api
    with get_session() as session:
        current_docs = list(session.exec(
            select(Document).where(Document.application_id == current.id)
        ).all())
    applicant_warnings = review_api._warnings(current, current_docs)
    check_true("신청자에게는 공통 안내만 표시", "가구원 수는 건강보험 자격확인서 기준으로 판정합니다." in applicant_warnings)
    check("신청자 안내에 가구원 이름 없음", any(member["성명"] in json.dumps(applicant_warnings, ensure_ascii=False) for member in second_members), False)


def _review_status(application_id: int) -> str | None:
    with get_session() as session:
        review = session.exec(select(Review).where(Review.application_id == application_id)).first()
        return review.final_status if review else None


def _review_payload(application_id: int) -> dict:
    with get_session() as session:
        review = session.exec(select(Review).where(Review.application_id == application_id)).first()
        return review.review_payload_json if review else {}


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="p13-household-"))
    p4._isolate(tmp)
    try:
        test_household_source_and_income_review()
        test_missing_household_forces_review()
        test_scenario_package_creates_missing_samples(tmp)
        test_overlapping_households_link_both_applications(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n통과 {_passed} / 실패 {len(_failed)}")
    if _failed:
        for name in _failed:
            print(f"  - {name}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

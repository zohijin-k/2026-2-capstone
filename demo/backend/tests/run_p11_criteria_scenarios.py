"""P11 — 심사 기준 버전과 신청서 연결 시나리오."""

import json
import shutil
import tempfile
from datetime import date
from pathlib import Path

from . import run_p4_scenarios as p4
from ..rules.criteria import CRITERIA_SCHEMA_VERSION, for_application, issue_bounds, read_criteria
from ..rules.facts import build_facts
from ..models import Application, ProgramCriteriaVersion, get_session
from sqlmodel import select
from engine.models import Document as EngineDocument, RequiredDocumentSpec, ReasonCode
from engine.stage1_document_check import check_single_document

_passed = 0
_failed: list[str] = []


def check(name: str, actual: object, expected: object) -> None:
    global _passed
    if actual == expected:
        _passed += 1
        print(f"  [OK]   {name}")
    else:
        _failed.append(name)
        print(f"  [FAIL] {name}: 기대={expected!r} 실제={actual!r}")


def run(client) -> None:
    code = p4.DOUBLE_SAVINGS
    public = client.get(f"/api/programs/{code}/criteria")
    check("신청자 기준 조회", public.status_code, 200)
    check("신청자 기준에 배점 없음", any(k in str(public.json()).lower() for k in ("score", "점수", "internal")), False)

    existing = client.post("/api/applications", json={"program_code": code}).json()
    initial_version = existing["criteria_version"]
    body = {
        "announcement_date": "2026-03-03",
        "application_period": ["2026-03-03", "2026-03-16"],
        "document_issue_rules": {
            "resident_abstract": {"mode": "after_date", "date": "2026-11-01"},
            "nhis_payment": {"mode": "after_notice"},
        },
        "document_issue_fallback": {"mode": "after_notice"},
        "nhis_payment_months": ["2026-01", "2026-02", "2026-03"],
        "nhis_acquisition_loss_years": 5,
    }
    path = f"/api/officer/programs/{code}/criteria"
    check("비도 담당자 PUT 403", client.put(path, params={"role": "city"}, json=body).status_code, 403)
    invalid = {**body, "nhis_payment_months": []}
    check("잘못된 고지월 400", client.put(path, params={"role": "province"}, json=invalid).status_code, 400)
    saved = client.put(path, params={"role": "province"}, json=body)
    check("새 버전 저장", saved.status_code, 200)
    new_version = saved.json()["version"]
    check("기존 신청서 버전 유지", p4.models.Application.model_validate(existing).criteria_version, initial_version)
    new_app = client.post("/api/applications", json={"program_code": code}).json()
    check("새 신청서 사용 최신 버전", new_app["criteria_version"], new_version)
    officer = client.get(path, params={"role": "province"}).json()
    check("버전 이력 보존", len(officer["history"]) >= 2, True)
    check("새 고지월 기준", officer["current"]["nhis_payment_months"], body["nhis_payment_months"])
    check("두배적금 기본 스캔본 제출 허용 서식", officer["current"]["paper_forms"], {
        "서식1": False, "서식2": False, "서식3": False, "서식4": False, "서식5": True,
    })
    old_snapshot = read_criteria(for_application(Application.model_validate(existing)))
    new_snapshot = read_criteria(for_application(Application.model_validate(new_app)))
    check("기존 신청서 기준 이력 고정", old_snapshot["nhis_payment_months"], ["2025-10", "2025-11", "2025-12"])
    old_cutoff = issue_bounds(old_snapshot, "resident_abstract", date(2026, 11, 10))[0]
    new_cutoff = issue_bounds(new_snapshot, "resident_abstract", date(2026, 11, 10))[0]
    check("기존 버전 발급일 하한", old_cutoff.isoformat(), "2026-03-03")
    check("새 버전 발급일 하한", new_cutoff.isoformat(), "2026-11-01")
    same_doc = EngineDocument(
        doc_type="주민등록초본", file_format="pdf", ocr_confidence=0.99,
        image_quality_score=0.99, has_signature=None, issue_date=date(2026, 6, 1),
    )
    old_findings = check_single_document(same_doc, RequiredDocumentSpec("주민등록초본", min_issue_date=old_cutoff))
    new_findings = check_single_document(same_doc, RequiredDocumentSpec("주민등록초본", min_issue_date=new_cutoff))
    check("같은 서류의 구버전 판정", len(old_findings), 0)
    check("같은 서류의 신버전 판정", new_findings[0].code, ReasonCode.DOCUMENT_ISSUED_TOO_EARLY)

    monthly = {"2025-10": "100", "2025-11": "200", "2025-12": "300",
               "2026-01": "1000", "2026-02": "2000", "2026-03": "3000"}
    fact = {"doc_type": "건강보험료납부확인서", "fields": {"월별고지금액": json.dumps(monthly)}}
    old_avg = build_facts({}, [fact], old_snapshot["nhis_payment_months"]).monthly_premium
    new_avg = build_facts({}, [fact], new_snapshot["nhis_payment_months"]).monthly_premium
    check("기본 기준의 평균", old_avg, 200)
    check("변경 기준의 평균", new_avg, 2000)

    # 구형 저장 형식을 DB에 직접 넣어도 공개/담당자 조회와 신청서 판정이 유지되는지 확인.
    legacy_version = new_version + 1
    legacy_raw = {"announcement_date": "2026-03-03"}
    with get_session() as session:
        session.add(ProgramCriteriaVersion(
            program_code=code, version=legacy_version, criteria_json=legacy_raw,
            changed_role="system",
        ))
        session.commit()

    legacy_public = client.get(f"/api/programs/{code}/criteria")
    check("구형 기준 신청자 조회", legacy_public.status_code, 200)
    check("구형 기준 신청 기간 기본값 보정", len(legacy_public.json().get("application_period", [])), 2)
    check("구형 기준 스키마 보정", legacy_public.json().get("schema_version"), CRITERIA_SCHEMA_VERSION)
    legacy_officer = client.get(path, params={"role": "province"})
    check("구형 기준 담당자 조회", legacy_officer.status_code, 200)
    check("구형 기준 이력도 보정", legacy_officer.json()["current"].get("nhis_payment_months"),
          ["2025-10", "2025-11", "2025-12"])
    check("구형 기준 스캔본 제출 허용 기본값", legacy_officer.json()["current"].get("paper_forms"), {
        "서식1": False, "서식2": False, "서식3": False, "서식4": False, "서식5": True,
    })

    legacy_app = client.post("/api/applications", json={"program_code": code}).json()
    check("구형 기준에 신청서 버전 고정", legacy_app["criteria_version"], legacy_version)
    legacy_snapshot = read_criteria(for_application(Application.model_validate(legacy_app)))
    legacy_cutoff = issue_bounds(legacy_snapshot, "resident_abstract", date(2026, 11, 10))[0]
    legacy_findings = check_single_document(
        same_doc, RequiredDocumentSpec("주민등록초본", min_issue_date=legacy_cutoff)
    )
    check("구형 기준 신청서 판정 정상", len(legacy_findings), 0)
    with get_session() as session:
        saved_legacy = session.exec(select(ProgramCriteriaVersion).where(
            ProgramCriteriaVersion.program_code == code,
            ProgramCriteriaVersion.version == legacy_version,
        )).first()
    check("읽기 보정 시 구형 기록 보존", saved_legacy.criteria_json, legacy_raw)

    paper_body = {key: value for key, value in officer["current"].items()
                  if key not in {"version", "schema_version", "changed_at", "changed_role"}}
    paper_body["paper_forms"] = {"서식1": False, "서식2": False, "서식3": False, "서식4": False, "서식5": False}
    paper_saved = client.put(path, params={"role": "province"}, json=paper_body)
    check("관리자 스캔본 제출 허용 설정 저장", paper_saved.status_code, 200)
    paper_app = client.post("/api/applications", json={"program_code": code}).json()
    check("새 신청서에 스캔본 제출 기준 버전 고정", paper_app["criteria_version"], paper_saved.json()["version"])
    check("새 기준에서 스캔본 제출 비허용 적용", read_criteria(for_application(Application.model_validate(paper_app)))["paper_forms"]["서식5"], False)
    check("이전 신청서는 스캔본 제출 기본값 유지", old_snapshot["paper_forms"]["서식5"], True)

    # 지원 항목 카탈로그 역시 신청서가 생성된 시점의 버전에 고정된다.
    job_old = client.post("/api/applications", json={"program_code": "job_package"}).json()
    identify_body = {"name": "김전북", "birth": "1999-01-01", "phone": "010-1234-5678",
                     "pledge": True, "signature_data_url": "data:image/png;base64,iVBORw0KGgo="}
    client.post(f"/api/applications/{job_old['id']}/identity", json=identify_body)
    client.post(f"/api/applications/{job_old['id']}/subsidy-items", json={"items": [
        {"item_type": "interview", "count": 1},
    ]})
    job_path = "/api/officer/programs/job_package/criteria"
    job_criteria = client.get(job_path, params={"role": "province"}).json()["current"]
    catalog = job_criteria["subsidy_catalog"]
    catalog[0]["unit_cap"] = 60000
    catalog[0]["count_scope"] = "year"
    catalog[0]["extra_docs"][0]["date_basis"] = "payment_date"
    job_body = {key: value for key, value in job_criteria.items()
                if key not in {"version", "schema_version", "changed_at", "changed_role"}}
    changed = client.put(job_path, params={"role": "province"}, json=job_body)
    check("취업패키지 카탈로그 기준 저장", changed.status_code, 200)
    job_new = client.post("/api/applications", json={"program_code": "job_package"}).json()
    client.post(f"/api/applications/{job_new['id']}/identity", json=identify_body)
    old_catalog = client.get(f"/api/applications/{job_old['id']}/subsidy-items").json()["catalog"]
    new_catalog = client.get(f"/api/applications/{job_new['id']}/subsidy-items").json()["catalog"]
    check("기존 신청서는 이전 항목 한도 유지", old_catalog[0]["unit_cap"], 50000)
    check("새 신청서는 새 항목 한도 적용", new_catalog[0]["unit_cap"], 60000)
    check("연간 범위에서 이전 신청 사용 횟수 반영", new_catalog[0]["remaining_count"], 1)
    over_scope = client.post(f"/api/applications/{job_new['id']}/subsidy-items", json={"items": [
        {"item_type": "interview", "count": 2},
    ]})
    check("연간 한도 초과 회차 거부", over_scope.status_code, 400)
    allowed_scope = client.post(f"/api/applications/{job_new['id']}/subsidy-items", json={"items": [
        {"item_type": "interview", "count": 1},
    ]})
    check("연간 남은 1회 신청 허용", allowed_scope.status_code, 200)
    client.post(f"/api/applications/{job_new['id']}/subsidy-items", json={"items": [
        {"item_type": "interview", "count": 1},
    ]})
    interview_doc = next(item for item in client.get(
        f"/api/applications/{job_new['id']}/required-documents"
    ).json()["items"] if item["slot_key"] == "interview_1_confirmation")
    check("새 날짜 종류가 서류 칸에 반영", interview_doc["date_basis"], "payment_date")
    check("날짜 입력 순서가 요구됨", interview_doc["check_declared_date"], True)


def main() -> int:
    from fastapi.testclient import TestClient
    from ..main import app

    tmp = Path(tempfile.mkdtemp(prefix="p11-criteria-"))
    p4._isolate(tmp)
    try:
        with TestClient(app) as client:
            run(client)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n통과 {_passed} / 실패 {len(_failed)}")
    return 1 if _failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

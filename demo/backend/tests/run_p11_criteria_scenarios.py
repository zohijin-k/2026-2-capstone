"""P11 — 심사 기준 버전과 신청서 연결 시나리오."""

import json
import shutil
import tempfile
from datetime import date
from pathlib import Path

from . import run_p4_scenarios as p4
from ..rules.criteria import for_application, issue_bounds
from ..rules.facts import build_facts
from ..models import Application
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
    old_snapshot = for_application(Application.model_validate(existing)).criteria_json
    new_snapshot = for_application(Application.model_validate(new_app)).criteria_json
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

"""P12 — 취업패키지 지원 기준 버전과 실제 적용 시나리오."""

import shutil
import tempfile
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

from sqlmodel import select

from . import run_p4_scenarios as p4
from . import run_p5_scenarios as p5
from .. import models
from ..models import Application, ProgramCriteriaVersion, get_session
from ..ocr.base import OcrResult
from ..rules.criteria import CRITERIA_SCHEMA_VERSION, default_criteria, read_criteria
from ..rules.doc_types import DocType

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


def _current_body(client) -> dict:
    current = client.get(
        "/api/officer/programs/job_package/criteria", params={"role": "province"}
    ).json()["current"]
    return {key: value for key, value in current.items()
            if key not in {"version", "schema_version", "changed_at", "changed_role"}}


def _save_criteria(client, body: dict) -> dict:
    return client.put(
        "/api/officer/programs/job_package/criteria",
        params={"role": "province"}, json=body,
    ).json()


def _set_item(client, app_id: int, item_type: str, count: int, *, receipts=None, links=None):
    row = {"item_type": item_type, "count": count, "receipts": receipts or []}
    if links is not None:
        row["linked_interview_indices"] = links
    return client.post(f"/api/applications/{app_id}/subsidy-items", json={"items": [row]})


def _create_identity(client, *, birth: str = "1999-01-01") -> int:
    app_id = client.post("/api/applications", json={"program_code": "job_package"}).json()["id"]
    response = client.post(f"/api/applications/{app_id}/identity", json={
        "name": "김전북", "birth": birth, "phone": "010-1234-5678",
        "pledge": True, "signature_data_url": "data:image/png;base64,iVBORw0KGgo=",
    })
    check("가상 신청자 본인인증", response.status_code, 200)
    return app_id


def _created_year(app_id: int, year: int) -> None:
    with get_session() as session:
        app = session.get(Application, app_id)
        assert app is not None
        app.created_at = datetime(year, 6, 1)
        session.add(app)
        session.commit()


def _set_scope(body: dict, item_type: str, scope: str) -> None:
    item = next(row for row in body["subsidy_catalog"] if row["item_type"] == item_type)
    item["count_scope"] = scope


def test_count_scopes(client) -> None:
    print("\n[1] 횟수 범위 — 신청서·연간·생애 누적")
    default_app = _create_identity(client)
    check("신청서 기본 범위는 최대 초과 거부", _set_item(client, default_app, "interview", 3).status_code, 400)

    body = _current_body(client)
    _set_scope(body, "interview", "year")
    _save_criteria(client, body)
    earlier_same_year = _create_identity(client)
    _created_year(earlier_same_year, 2026)
    check("연간 누적을 위한 이전 신청 항목 저장", _set_item(client, earlier_same_year, "interview", 1).status_code, 200)
    earlier_other_year = _create_identity(client)
    _created_year(earlier_other_year, 2025)
    check("다른 연도 신청 항목 저장", _set_item(client, earlier_other_year, "interview", 1).status_code, 200)
    same_year_current = _create_identity(client)
    _created_year(same_year_current, 2026)
    check("같은 해 이전 회차까지 더하면 초과", _set_item(client, same_year_current, "interview", 2).status_code, 400)
    other_year_current = _create_identity(client)
    _created_year(other_year_current, 2027)
    check("다른 해 신청은 연간 누적에서 제외", _set_item(client, other_year_current, "interview", 2).status_code, 200)

    body = _current_body(client)
    _set_scope(body, "interview", "lifetime")
    _save_criteria(client, body)
    lifetime_current = _create_identity(client)
    _created_year(lifetime_current, 2028)
    check("생애 누적은 다른 해 회차도 포함", _set_item(client, lifetime_current, "interview", 2).status_code, 400)


def test_interview_linking(client) -> None:
    print("\n[2] 정장비 회차와 면접 회차 연결")
    app_id = client.post("/api/applications", json={"program_code": "job_package"}).json()["id"]
    valid = client.post(f"/api/applications/{app_id}/subsidy-items", json={"items": [
        {"item_type": "interview", "count": 2},
        {"item_type": "suit", "count": 1, "receipts": [30000], "linked_interview_indices": [2]},
    ]})
    check("정장비가 면접 2회차에 정상 연결", valid.status_code, 200)
    duplicate = client.post(f"/api/applications/{app_id}/subsidy-items", json={"items": [
        {"item_type": "interview", "count": 2},
        {"item_type": "suit", "count": 2, "receipts": [30000, 32000], "linked_interview_indices": [1, 1]},
    ]})
    check("같은 면접확인서의 중복 연결 거부", duplicate.status_code, 400)


def test_receipt_amounts(client) -> None:
    print("\n[3] 영수증 판독 금액 — 일치·불일치·판독 실패")
    match_app = client.post("/api/applications", json={"program_code": "job_package"}).json()["id"]
    _set_item(client, match_app, "photo", 1, receipts=[18000])
    match = p5._upload(client, match_app, "photo_1_receipt", "S10_결제영수증_사진18000.pdf", "2026-03-25")
    check("입력 금액과 판독 금액이 같으면 통과", match["status"], "PASS")

    mismatch_app = client.post("/api/applications", json={"program_code": "job_package"}).json()["id"]
    _set_item(client, mismatch_app, "photo", 1, receipts=[17000])
    mismatch = p5._upload(client, mismatch_app, "photo_1_receipt", "S10_결제영수증_사진18000.pdf", "2026-03-25")
    check("입력 금액과 판독 금액이 다르면 담당자 확인", mismatch["status"], "NEEDS_REVIEW")

    missing_app = client.post("/api/applications", json={"program_code": "job_package"}).json()["id"]
    _set_item(client, missing_app, "photo", 1, receipts=[18000])
    unreadable_result = OcrResult(
        detected_doc_type=DocType.PAYMENT_RECEIPT,
        confidence=0.9, image_quality=0.9, fields={"결제일": "2026-03-25"}, tier="fixture",
    )
    with patch("demo.backend.api.documents.read_document", return_value=unreadable_result):
        unreadable = p5._upload(client, missing_app, "photo_1_receipt", "S10_결제영수증_사진18000.pdf", "2026-03-25")
    check("금액 판독 실패는 담당자 확인", unreadable["status"], "NEEDS_REVIEW")
    check("금액 판독 실패 사유", [f["code"] for f in unreadable["findings"]], ["RECEIPT_AMOUNT_UNREADABLE"])

    no_ocr_app = client.post("/api/applications", json={"program_code": "job_package"}).json()["id"]
    _set_item(client, no_ocr_app, "photo", 1, receipts=[18000])
    unavailable = OcrResult(detected_doc_type=None, confidence=0.0, image_quality=1.0, fields={}, tier="none")
    with patch("demo.backend.api.documents.read_document", return_value=unavailable):
        no_ocr = p5._upload(client, no_ocr_app, "photo_1_receipt", "S10_결제영수증_사진18000.pdf", "2026-03-25")
    check("OCR 엔진 결과가 없으면 담당자 확인", no_ocr["status"], "NEEDS_REVIEW")
    check("OCR 엔진 없음 사유", [f["code"] for f in no_ocr["findings"]], ["RECEIPT_OCR_UNAVAILABLE"])


def test_payment_date_basis(client) -> None:
    print("\n[4] 서류 기준 날짜 — 지원연도 이전 결제일")
    body = _current_body(client)
    body["document_issue_rules"]["receipt"] = {"mode": "after_date", "date": "2026-01-01"}
    photo = next(row for row in body["subsidy_catalog"] if row["item_type"] == "photo")
    receipt = next(doc for doc in photo["extra_docs"] if doc["suffix"] == "receipt")
    receipt["date_basis"] = "payment_date"
    saved = _save_criteria(client, body)
    check("지원 기준 날짜 설정 저장", saved["version"] is not None, True)
    app_id = client.post("/api/applications", json={"program_code": "job_package"}).json()["id"]
    _set_item(client, app_id, "photo", 1, receipts=[18000])
    ocr_result = OcrResult(
        detected_doc_type=DocType.PAYMENT_RECEIPT,
        confidence=0.91, image_quality=0.9,
        issue_date=date(2025, 12, 20),
        fields={"결제금액": "18000", "결제일": "2025-12-20", "발급일": "2025-12-20"},
        tier="fixture",
    )
    with patch("demo.backend.api.documents.read_document", return_value=ocr_result):
        result = p5._upload(client, app_id, "photo_1_receipt", "S10_결제영수증_사진18000.pdf", "2025-12-20")
    check("지원연도 이전 결제일은 기준 위반", result["status"], "FAIL")
    check("결제일 기준 위반 코드", any(f["code"] == "DOCUMENT_ISSUED_TOO_EARLY" for f in result["findings"]), True)


def test_legacy_and_frozen_criteria(client) -> None:
    print("\n[5] 구형 기준 읽기와 신청서 기준 버전 고정")
    print(f"       CRITERIA_SCHEMA_VERSION={CRITERIA_SCHEMA_VERSION}")
    old_app = client.post("/api/applications", json={"program_code": "job_package"}).json()
    raw = default_criteria("job_package")
    raw["schema_version"] = CRITERIA_SCHEMA_VERSION - 1
    raw.pop("subsidy_catalog", None)
    old_version = old_app["criteria_version"] + 1
    with get_session() as session:
        session.add(ProgramCriteriaVersion(
            program_code="job_package", version=old_version,
            criteria_json=raw, changed_role="system",
        ))
        app = session.get(Application, old_app["id"])
        assert app is not None
        app.criteria_version = old_version
        session.add(app)
        session.commit()

    check("구형 기준은 항목 기본값으로 보정되어 읽힘", client.get(f"/api/applications/{old_app['id']}/subsidy-items").status_code, 200)
    check("구형 기준에서 최대 면접 횟수 판정 가능", _set_item(client, old_app["id"], "interview", 2).status_code, 200)

    body = _current_body(client)
    interview = next(row for row in body["subsidy_catalog"] if row["item_type"] == "interview")
    interview["max_count"] = 1
    _save_criteria(client, body)
    new_app = client.post("/api/applications", json={"program_code": "job_package"}).json()
    check("기존 신청서 버전은 갱신 뒤에도 고정", client.get(f"/api/applications/{old_app['id']}/subsidy-items").json()["catalog"][0]["max_count"], 2)
    check("새 신청서는 변경한 기준 사용", client.get(f"/api/applications/{new_app['id']}/subsidy-items").json()["catalog"][0]["max_count"], 1)
    check("읽기 보정 후 DB 구형 JSON 보존", read_criteria(ProgramCriteriaVersion(
        program_code="job_package", version=old_version, criteria_json=raw,
    ))["schema_version"], CRITERIA_SCHEMA_VERSION)
    with get_session() as session:
        stored = session.exec(select(ProgramCriteriaVersion).where(
            ProgramCriteriaVersion.program_code == "job_package",
            ProgramCriteriaVersion.version == old_version,
        )).first()
    check("구형 기준 원본 보존", stored.criteria_json if stored else None, raw)


def main() -> int:
    from fastapi.testclient import TestClient
    from ..main import app

    tmp = Path(tempfile.mkdtemp(prefix="p12-subsidy-criteria-"))
    p4._isolate(tmp)
    try:
        with TestClient(app) as client:
            test_count_scopes(client)
            test_interview_linking(client)
            test_receipt_amounts(client)
            test_payment_date_basis(client)
            test_legacy_and_frozen_criteria(client)
    finally:
        models.engine.dispose()
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n통과 {_passed} / 실패 {len(_failed)}")
    return 1 if _failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

"""P6 게이트 검증 — **리셋 후 시연 시나리오 10종 무중단 재현**.

저장소 루트에서:

    PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python -m demo.backend.tests.run_p6_scenarios
    PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python -m demo.backend.tests.run_p6_scenarios --live

확인하는 것:

  1. `reset.py`가 실제로 DB와 업로드 저장소를 지운다 (남은 신청 건 0)
  2. 리셋 직후 상태에서 **S1~S10을 순서대로, 중단 없이** 통과한다
  3. 각 시나리오의 실제 결과가 `fixtures/expected/S*.json`의 기대값과 일치한다
  4. **리셋 → 재실행을 한 번 더 해도 결과가 글자 하나까지 같다** (멱등성).
     시연 중 리셋이 실제로 동작해야 하므로, 신청번호까지 같은 값으로 다시 매겨지는지
     본다. 이게 무너지면 두 번째 시연에서 화면이 달라진다.

기대값은 `demo/fixtures/expected/`에 시나리오별 JSON으로 따로 있다. 시나리오 정의를
여기에 또 쓰지 않기 위해서다 — 대본(`demo/docs/demo-script.md`)·기대값·검증이 같은
파일을 본다.

기본은 **임시 폴더**에서 돈다. `demo/demo.db`·`demo/storage`(시연용 데이터)를
건드리지 않기 위함이다. `--live`를 주면 진짜 `demo/`를 리셋하고 거기서 돌린다 —
시연 직전 최종 점검용이다.

업로드 파일은 `demo/fixtures/samples/`의 더미 PDF만 쓴다. 실제 개인정보·실물 서류는
일절 쓰지 않는다 (R7.1). 이름·계좌번호도 명백한 가짜다.
"""

import argparse
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from sqlmodel import create_engine, select

from .. import models
from ..reset import ResetReport, reset as reset_demo
from ..rules.programs import DOUBLE_SAVINGS, JOB_PACKAGE
from ..rules.roles import ROLE_CITY, ROLE_PROVINCE

DEMO_ROOT = Path(__file__).resolve().parents[2]
SAMPLES = DEMO_ROOT / "fixtures" / "samples"
EXPECTED_DIR = DEMO_ROOT / "fixtures" / "expected"

#: 시연 순서. 이 순서가 곧 대본의 순서이고, 신청번호가 매겨지는 순서다.
SCENARIOS = ["S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9", "S10"]

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


# ---------------------------------------------------------------- 기대값 대조


#: 기대값 JSON에서 쓰는 비교 연산자. 값이 실행마다 달라지는 항목(소요시간)과
#: 문구 전체를 적기엔 긴 항목(안내 문장)을 위해 둔다.
MATCHERS = ("$contains", "$not_empty", "$lt", "$len", "$each_contains")


def _is_matcher(value: object) -> bool:
    return isinstance(value, dict) and len(value) == 1 and next(iter(value)) in MATCHERS


def compare(expected: object, actual: object) -> tuple[bool, str]:
    """기대값 하나와 실제값 하나를 견준다. (일치 여부, 설명)"""
    if _is_matcher(expected):
        assert isinstance(expected, dict)
        op, operand = next(iter(expected.items()))
        if op == "$contains":
            ok = isinstance(actual, str) and str(operand) in actual
            return ok, f"'{operand}' 포함"
        if op == "$not_empty":
            return bool(actual) is bool(operand), "비어 있지 않음"
        if op == "$lt":
            ok = isinstance(actual, (int, float)) and actual < operand
            return ok, f"{operand} 미만"
        if op == "$len":
            ok = hasattr(actual, "__len__") and len(actual) == operand  # type: ignore[arg-type]
            return ok, f"길이 {operand}"
        if op == "$each_contains":
            ok = isinstance(actual, list) and all(
                isinstance(x, str) and str(operand) in x for x in actual
            )
            return ok, f"모든 항목에 '{operand}' 포함"
    return expected == actual, repr(expected)


def load_expected(scenario: str) -> dict[str, Any]:
    path = EXPECTED_DIR / f"{scenario}.json"
    if not path.exists():
        raise FileNotFoundError(f"기대 결과 JSON이 없습니다: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def verify(scenario: str, actual: dict[str, Any]) -> None:
    """시나리오 하나의 실제 결과를 기대값 JSON과 항목별로 대조한다."""
    spec = load_expected(scenario)
    print(f"\n[{scenario}] {spec['title']}")
    print(f"       증명: {spec['proves']}")

    expect = spec["expect"]
    unknown = sorted(set(actual) - set(expect))
    missing = sorted(set(expect) - set(actual))
    if unknown or missing:
        _failed.append(f"{scenario} 기대값 항목 불일치")
        print(f"  [FAIL] 기대값에 없는 실제 항목={unknown} / 실제에 없는 기대 항목={missing}")

    for key, want in expect.items():
        got = actual.get(key)
        ok, description = compare(want, got)
        global _passed
        if ok:
            _passed += 1
            print(f"  [OK]   {key}: {got!r}")
        else:
            _failed.append(f"{scenario}.{key}")
            print(f"  [FAIL] {key}: 기대={description} 실제={got!r}")


# ---------------------------------------------------------------- 시연 입력값


#: 시연용 더미 신청서. 이름·주소·연락처·계좌는 전부 가짜다 (R7.1).
BASE_FORM1: dict[str, Any] = {
    "savingPurpose": "주거자금",
    "priorJoined": "아니오",
    "name": "홍길동",
    "birth": {"y": "1998", "m": "6", "d": "15"},
    "gender": "남",
    "address": "전북특별자치도 전주시 완산구 효자동 123",
    "mobile": "010-0000-0000",
    "transferIn": {"y": "2020", "m": "11", "d": "20"},
    "householdType": "그 외 일반 가구",
    "householdSize": "4인",
    "workType": "상용직(노동계약기간 1년 이상)",
    "employedAt": {"y": "2023", "m": "1", "d": "2"},
    "workplaceRegion": "전북특별자치도 내 지역",
    "workplaceName": "(주)데모",
    "bankName": "농협은행",
    "accountNo": "302-0000-0000-00",
    "accountHolder": "홍길동",
    "referralPaths": ["홈페이지(도, 시군, 청년센터 등)"],
}

JOB_FORM1: dict[str, Any] = {
    "name": "최청년",
    "birth": {"y": "1999", "m": "4", "d": "10"},
    "gender": "여",
    "address": "전북특별자치도 전주시 완산구 효자동 123",
    "mobile": "010-1111-2222",
    "bankName": "전북은행",
    "accountNo": "1010-00-000000",
    "accountHolder": "최청년",
    "bankbookFileName": "통장사본_최청년.jpg",
}

#: 1×1 투명 PNG. 캔버스 전자서명 대신 넣는 더미 이미지다.
DUMMY_SIGNATURE = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

DS_CONSENTS = [
    {"consent_type": "privacy", "agreed": True},
    {"consent_type": "unique_id", "agreed": True},
    {"consent_type": "third_party", "agreed": True},
    {
        "consent_type": "admin_info",
        "agreed": True,
        "signature_kind": "electronic",
        "signature_data_url": DUMMY_SIGNATURE,
    },
]

JOB_CONSENTS = [
    {"consent_type": "privacy", "agreed": True},
    {"consent_type": "third_party", "agreed": True},
]

#: 서식2 8문항 전부 "예".
ALL_YES = {str(i): "예" for i in range(1, 9)}

S2_UPLOADS = {
    "resident_abstract": "S2_주민등록초본_적합.pdf",
    "nhis_payment": "S2_건강보험료납부확인서_적합.pdf",
    "nhis_qualification": "S2_건강보험자격확인서_적합.pdf",
    "nhis_acquisition_loss": "S2_건강보험자격득실확인서_적합.pdf",
    "work_proof": "S2_4대보험가입내역확인서_적합.pdf",
}

S10_SELECTION = [
    {"item_type": "interview", "count": 2, "receipts": []},
    {"item_type": "suit", "count": 1, "receipts": [70000]},
    {"item_type": "certificate", "count": 1, "receipts": [43000]},
]

S10_UPLOADS = {
    "resident_abstract": ("S10_주민등록초본_취업패키지.pdf", "2026-04-07"),
    "interview_1_confirmation": ("S10_면접확인서_1회차.pdf", ""),
    "interview_2_confirmation": ("S10_면접확인서_2회차.pdf", ""),
    "suit_1_confirmation": ("S10_면접확인서_정장.pdf", ""),
    "suit_1_receipt": ("S10_결제영수증_정장70000.pdf", ""),
    "certificate_1_exam": ("S10_응시확인서_적합.pdf", ""),
    "certificate_1_receipt": ("S10_결제영수증_응시료43000.pdf", ""),
}


# ---------------------------------------------------------------- 공통 동작


def _upload(client, app_id: int, slot: str, filename: str, declared: str = "") -> dict:
    with (SAMPLES / filename).open("rb") as fh:
        res = client.post(
            f"/api/applications/{app_id}/documents",
            files={"file": (filename, fh, "application/pdf")},
            data={"slot_key": slot, "declared_issue_date": declared},
        )
    return res.json()


def _codes(doc: dict) -> list[str]:
    return [f["code"] for f in doc.get("findings", [])]


def _finding(doc: dict, field: str) -> str:
    findings = doc.get("findings") or [{}]
    return str(findings[0].get(field) or "")


def _fill_ds(client, *, name: str) -> int:
    """두배적금 1건을 서식1~5까지 채운다. 서류는 아직 올리지 않는다."""
    app_id = client.post(
        "/api/applications", json={"program_code": DOUBLE_SAVINGS}
    ).json()["id"]
    client.patch(f"/api/applications/{app_id}", json={"form1": {**BASE_FORM1, "name": name}})
    client.post(f"/api/applications/{app_id}/self-check", json={"answers": ALL_YES})
    client.post(f"/api/applications/{app_id}/consents", json={"consents": DS_CONSENTS})
    client.put(
        f"/api/applications/{app_id}/doc-context",
        json={"work_category": "직장가입자", "workplace_count": 1},
    )
    return app_id


def _create_ds(client, *, name: str, uploads: dict[str, str]) -> int:
    """두배적금 1건을 신청서·동의·서류까지 채운다(제출 전)."""
    app_id = _fill_ds(client, name=name)
    for slot, filename in uploads.items():
        _upload(client, app_id, slot, filename, "2026-03-05")
    return app_id


#: 신청자 응답에 있으면 안 되는 키 (R5.3).
FORBIDDEN_KEYS = {
    "score",
    "total_score",
    "score_json",
    "score_sheet",
    "max_total",
    "band",
    "basis",
    "tiebreak",
    "income_percent",
    "review_payload",
    "review_payload_json",
    "rank",
}


def score_leak(value: object, path: str = "") -> list[str]:
    hits: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            here = f"{path}.{key}" if path else key
            if key in FORBIDDEN_KEYS:
                hits.append(here)
            hits.extend(score_leak(child, here))
    elif isinstance(value, list):
        for i, child in enumerate(value):
            hits.extend(score_leak(child, f"{path}[{i}]"))
    return hits


class Recorder:
    """담당자 심사 세션 동안 오간 응답 헤더를 전부 기록한다 (S9의 '다운로드 0회')."""

    def __init__(self, client) -> None:
        self.client = client
        self.log: list[dict[str, str]] = []

    def get(self, path: str, **kw):
        res = self.client.get(path, **kw)
        self.log.append(
            {
                "path": path,
                "status": str(res.status_code),
                "disposition": res.headers.get("content-disposition", ""),
            }
        )
        return res

    @property
    def file_calls(self) -> int:
        return sum(1 for e in self.log if e["path"].startswith("/api/files/"))

    @property
    def inline(self) -> int:
        return sum(1 for e in self.log if e["disposition"].lower().startswith("inline"))

    @property
    def attachments(self) -> int:
        return sum(1 for e in self.log if "attachment" in e["disposition"].lower())


# ---------------------------------------------------------------- 시나리오


def s1_self_check_blocks(client) -> dict[str, Any]:
    """자가진단에서 막힌다 — 신청서를 쓰기 전에."""
    app_id = client.post(
        "/api/applications", json={"program_code": DOUBLE_SAVINGS}
    ).json()["id"]
    answers = {**ALL_YES, "6": "아니오"}
    result = client.post(
        f"/api/applications/{app_id}/self-check", json={"answers": answers}
    ).json()
    blocked = client.post(f"/api/applications/{app_id}/submit")
    app = client.get(f"/api/applications/{app_id}").json()
    officer = client.get(
        "/api/officer/applications", params={"role": ROLE_PROVINCE}
    ).json()

    return {
        "application_no": app["application_no"],
        "eligible": result["eligible"],
        "completed": result["completed"],
        "failed_item": result["failed_item"],
        "total_items": result["total_items"],
        "reason": result["reason"],
        "alternative": result["alternative"],
        "submit_status_code": blocked.status_code,
        "status": app["status"],
        "officer_sees_draft": officer["total"],
    }


def s2_perfect(client, app_id: int) -> dict[str, Any]:
    """완전 적합 — 40+25+25+9 = 99점.

    S3~S6에서 같은 신청 건의 초본 슬롯에 잘못된 파일을 네 번 올려 본 뒤, 올바른
    서류로 교체해 제출한다. 시연 동선과 같다.
    """
    for slot, filename in S2_UPLOADS.items():
        _upload(client, app_id, slot, filename, "2026-03-05")
    documents = client.get(f"/api/applications/{app_id}/documents").json()

    final = client.get(f"/api/applications/{app_id}/final-check").json()
    body = client.post(f"/api/applications/{app_id}/submit").json()

    with models.get_session() as s:
        review = s.exec(
            select(models.Review).where(models.Review.application_id == app_id)
        ).first()
    assert review is not None
    items = {i["key"]: i for i in review.score_json["items"]}
    status = client.get(f"/api/applications/{app_id}/status").json()

    return {
        "application_no": body["application_no"],
        "document_statuses": [d["status"] for d in documents],
        "slowest_upload_ms": max(d["elapsed_ms"] for d in documents),
        "can_submit": final["can_submit"],
        "blockers": final["blockers"],
        "final_status": review.final_status,
        "stage1_status": review.stage1_status,
        "stage2_status": review.stage2_status,
        "total_score": review.total_score,
        "item_scores": {k: v["score"] for k, v in items.items()},
        "income_percent": review.score_json["income_percent"],
        "residence_basis": items["residence"]["basis"],
        "file_refs": sum(
            1
            for d in review.review_payload_json["documents"]
            if str(d.get("file_ref") or "").startswith("/api/files/")
        ),
        "mypage_progress": [p["label"] for p in status["progress"]],
        "mypage_score_leak": score_leak(status),
    }


def s3_wrong_document(client, app_id: int) -> dict[str, Any]:
    """초본 자리에 등본."""
    doc = _upload(client, app_id, "resident_abstract", "S3_주민등록등본_오제출.pdf", "2026-03-05")
    return {
        "status": doc["status"],
        "codes": _codes(doc),
        "detected_doc_type": doc["detected_doc_type"],
        "expected_doc_type": doc["expected_doc_type"],
        "message": _finding(doc, "message"),
        "how_to_fix": _finding(doc, "how_to_fix"),
        "link": _finding(doc, "link"),
    }


def s4_issued_too_early(client, app_id: int) -> dict[str, Any]:
    """공고일(2026-03-03) 이전 발급분."""
    doc = _upload(
        client, app_id, "resident_abstract", "S4_주민등록초본_발급일이전.pdf", "2026-02-28"
    )
    return {
        "status": doc["status"],
        "codes": _codes(doc),
        "detected_doc_type": doc["detected_doc_type"],
        "issue_date": doc["extracted"].get("발급일"),
        "message": _finding(doc, "message"),
        "how_to_fix": _finding(doc, "how_to_fix"),
    }


def s5_declared_mismatch(client, app_id: int) -> dict[str, Any]:
    """신청자가 입력한 발급일 ≠ 서류에 찍힌 발급일."""
    doc = _upload(
        client, app_id, "resident_abstract", "S5_주민등록초본_발급일불일치.pdf", "2026-03-05"
    )
    return {
        "status": doc["status"],
        "codes": _codes(doc),
        "declared_issue_date": doc["declared_issue_date"],
        "issue_date": doc["extracted"].get("발급일"),
        "message": _finding(doc, "message"),
        "how_to_fix": _finding(doc, "how_to_fix"),
    }


def s6_encrypted(client, app_id: int) -> dict[str, Any]:
    """암호가 걸린 PDF."""
    doc = _upload(client, app_id, "resident_abstract", "S6_주민등록초본_암호.pdf", "2026-03-05")
    return {
        "status": doc["status"],
        "codes": _codes(doc),
        "detected_doc_type": doc["detected_doc_type"],
        "ocr_confidence": doc["ocr_confidence"],
        "message": _finding(doc, "message"),
        "how_to_fix": _finding(doc, "how_to_fix"),
    }


def s7_income_over(client) -> dict[str, Any]:
    """4인 직장가입자 건보료 340,000원 → 중위소득 153%."""
    uploads = {**S2_UPLOADS, "nhis_payment": "S7_건강보험료납부확인서_소득초과.pdf"}
    app_id = _create_ds(client, name="김영희", uploads=uploads)

    final = client.get(f"/api/applications/{app_id}/final-check").json()
    client.post(f"/api/applications/{app_id}/submit")

    with models.get_session() as s:
        review = s.exec(
            select(models.Review).where(models.Review.application_id == app_id)
        ).first()
    assert review is not None
    status = client.get(f"/api/applications/{app_id}/status").json()

    return {
        "documents_all_pass": all(d["status"] == "PASS" for d in final["documents"]),
        "can_submit": final["can_submit"],
        "final_status": review.final_status,
        "stage1_status": review.stage1_status,
        "stage2_status": review.stage2_status,
        "reason_codes": [r["code"] for r in review.review_payload_json["reasons"]],
        "income_percent": review.score_json["income_percent"],
        "income_over_limit": review.score_json["income_over_limit"],
        "total_score": review.total_score,
        "mypage_score_leak": score_leak(status),
    }


def s8_needs_review(client) -> dict[str, Any]:
    """저해상도 초본(판독 신뢰도 0.6) → 담당자 큐 → 육안 확인 후 승인."""
    uploads = {**S2_UPLOADS, "resident_abstract": "S8_주민등록초본_저해상도.pdf"}
    app_id = _create_ds(client, name="박철수", uploads=uploads)
    documents = client.get(f"/api/applications/{app_id}/documents").json()
    abstract = next(d for d in documents if d["slot_key"] == "resident_abstract")

    final = client.get(f"/api/applications/{app_id}/final-check").json()
    client.post(f"/api/applications/{app_id}/submit")

    queue = client.get(
        "/api/officer/applications",
        params={"role": ROLE_PROVINCE, "ai_status": "NEEDS_REVIEW"},
    ).json()
    decision = client.post(
        f"/api/officer/applications/{app_id}/decision",
        json={
            "role": ROLE_PROVINCE,
            "decision": "approve",
            "memo": "판독 신뢰도 낮아 원본 육안 확인함. 초본 주소이력 포함 확인 — 승인.",
        },
    ).json()

    with models.get_session() as s:
        review = s.exec(
            select(models.Review).where(models.Review.application_id == app_id)
        ).first()
    assert review is not None

    return {
        "upload_status": abstract["status"],
        "upload_codes": _codes(abstract),
        "ocr_confidence": abstract["ocr_confidence"],
        "how_to_fix": _finding(abstract, "how_to_fix"),
        "can_submit": final["can_submit"],
        "final_status": review.final_status,
        "queue_total": queue["total"],
        "queue_name": queue["rows"][0]["name"],
        "queue_missing_count": queue["rows"][0]["missing_count"],
        "decision_label": decision["label"],
        "officer_decision": review.officer_decision,
        "officer_memo_saved": bool(review.officer_memo),
    }


def s9_officer_split_view(client, app_id: int) -> dict[str, Any]:
    """담당자 분할 심사 — 근거 클릭 → 하이라이트, 다운로드 0회."""
    rec = Recorder(client)
    rec.get("/api/officer/roles")
    listing = rec.get(
        "/api/officer/applications", params={"role": ROLE_CITY, "region": "전주시"}
    ).json()
    detail = rec.get(
        f"/api/officer/applications/{app_id}", params={"role": ROLE_CITY}
    ).json()

    # 좌측 뷰어 — 서류 탭을 전부 연다.
    for doc in detail["documents"]:
        rec.get(doc["file_url"])

    # 심사표 항목 클릭 → 근거 서류를 열고 그 좌표를 하이라이트한다.
    items = detail["score_sheet"]["items"]
    documents = {d["document_id"]: d for d in detail["documents"]}
    linked = [i for i in items if i["source_document_id"]]
    with_bbox = [i for i in linked if i["bbox"]]
    bbox_ok = True
    for item in with_bbox:
        res = rec.get(item["source_file_url"])
        doc = documents.get(item["source_document_id"])
        box = item["bbox"]
        bbox_ok = bbox_ok and (
            res.status_code == 200
            and doc is not None
            and item["source_slot_key"] == doc["slot_key"]
            and box["x0"] < box["x1"]
            and box["y0"] < box["y1"]
        )

    def total(**params) -> int:
        return client.get(
            "/api/officer/applications", params={"role": ROLE_PROVINCE, **params}
        ).json()["total"]

    return {
        "list_total": listing["total"],
        "top_name": listing["rows"][0]["name"],
        "top_score": listing["rows"][0]["total_score"],
        "pending": total(status="pending"),
        "approved": total(status="approve"),
        "documents": len(detail["documents"]),
        "score_total": detail["score_sheet"]["total"],
        "score_keys": [i["key"] for i in items],
        "score_max": [i["max_score"] for i in items],
        "basis_all_filled": all(i["basis"] for i in items),
        "estimate_label": " ".join(detail["score_sheet"]["notes"]),
        "linked_items": len(linked),
        "bbox_items": len(with_bbox),
        "bbox_resolves": bbox_ok,
        "eligibility_keys": [e["key"] for e in detail["eligibility"]],
        "exclusion_rows": len(detail["exclusions"]),
        "file_calls": rec.file_calls,
        "inline_responses": rec.inline,
        "attachment_responses": rec.attachments,
    }


def s10_job_package(client) -> dict[str, Any]:
    """취업패키지 — 면접비 2회 + 정장 1회 + 자격증 1회 복수 신청."""
    app_id = client.post(
        "/api/applications", json={"program_code": JOB_PACKAGE}
    ).json()["id"]
    client.patch(f"/api/applications/{app_id}", json={"form1": JOB_FORM1})
    self_check = client.post(
        f"/api/applications/{app_id}/self-check", json={"answers": {"1": "예", "2": "예"}}
    ).json()
    client.post(f"/api/applications/{app_id}/consents", json={"consents": JOB_CONSENTS})
    client.post(f"/api/applications/{app_id}/subsidy-items", json={"items": S10_SELECTION})

    checklist = client.get(f"/api/applications/{app_id}/required-documents").json()

    # 응시일이 빠진 응시확인서를 먼저 올려 본다 — 사업계획서 "(응시일 표기 필수)".
    bad_exam = _upload(
        client, app_id, "certificate_1_exam", "S10_응시확인서_응시일없음.pdf"
    )

    for slot, (filename, declared) in S10_UPLOADS.items():
        _upload(client, app_id, slot, filename, declared)

    saved = client.get(f"/api/applications/{app_id}/subsidy-items").json()
    suit = next(l for l in saved["estimate"]["lines"] if l["item_type"] == "suit")
    final = client.get(f"/api/applications/{app_id}/final-check").json()
    body = client.post(f"/api/applications/{app_id}/submit").json()

    with models.get_session() as s:
        review = s.exec(
            select(models.Review).where(models.Review.application_id == app_id)
        ).first()
    assert review is not None
    status = client.get(f"/api/applications/{app_id}/status").json()
    officer = client.get(
        "/api/officer/applications",
        params={"role": ROLE_PROVINCE, "program": JOB_PACKAGE},
    ).json()

    return {
        "application_no": body["application_no"],
        "self_check_items": self_check["total_items"],
        "upload_slots": checklist["upload_total"],
        "upload_slot_keys": [i["slot_key"] for i in checklist["items"] if i["upload"]],
        "exam_without_date_status": bad_exam["status"],
        "exam_without_date_codes": _codes(bad_exam),
        "granted_total": saved["estimate"]["total_granted"],
        "suit_receipt": suit["receipt_amount"],
        "suit_granted": suit["granted_amount"],
        "suit_calculation": suit["calculation"],
        "can_submit": final["can_submit"],
        "supplement_warning": next((w for w in final["warnings"] if "7일" in w), ""),
        "first_come_position": body["first_come"]["position"],
        "first_come_remaining": body["first_come"]["remaining"],
        "final_status": review.final_status,
        "total_score": review.total_score,
        "score_sheet": review.score_json,
        "officer_sort": officer["filters"]["applied"]["sort"],
        "officer_quota": officer["first_come"]["quota"],
        "mypage_score_leak": score_leak(status),
    }


# ---------------------------------------------------------------- 한 바퀴


def run_round(client) -> dict[str, dict[str, Any]]:
    """S1 → S10을 순서대로, 중단 없이 돈다."""
    results: dict[str, dict[str, Any]] = {}

    results["S1"] = s1_self_check_blocks(client)

    # S2의 신청서를 먼저 다 채운 뒤, 같은 건의 초본 슬롯에 잘못된 파일을 네 번
    # 올려 본다(S3~S6). 신청자가 실제로 겪는 "틀린 파일 → 사유 확인 → 다시 올리기"
    # 순서이고, 시연 대본의 동선도 이와 같다.
    s2_id = _fill_ds(client, name="홍길동")
    results["S3"] = s3_wrong_document(client, s2_id)
    results["S4"] = s4_issued_too_early(client, s2_id)
    results["S5"] = s5_declared_mismatch(client, s2_id)
    results["S6"] = s6_encrypted(client, s2_id)
    results["S2"] = s2_perfect(client, s2_id)

    results["S7"] = s7_income_over(client)
    results["S8"] = s8_needs_review(client)
    results["S9"] = s9_officer_split_view(client, s2_id)
    results["S10"] = s10_job_package(client)
    return results


def count_rows() -> dict[str, int]:
    with models.get_session() as s:
        return {
            "application": len(s.exec(select(models.Application)).all()),
            "document": len(s.exec(select(models.Document)).all()),
            "review": len(s.exec(select(models.Review)).all()),
            "consent": len(s.exec(select(models.Consent)).all()),
            "subsidy_item": len(s.exec(select(models.SubsidyItem)).all()),
        }


# ---------------------------------------------------------------- 진입점


def _isolate(root: Path) -> None:
    """DB와 업로드 저장소를 `root` 아래로 갈아끼운다.

    `--live`가 아니면 임시 폴더를 가리킨다. 리셋이 지우는 대상과 API가 쓰는 대상을
    같은 곳으로 맞춰야 "리셋 후 재현"이 진짜 검증이 된다.
    """
    from ..api import applications as applications_api
    from ..api import documents as documents_api
    from ..api import files as files_api

    models.engine = create_engine(
        f"sqlite:///{root / 'demo.db'}", connect_args={"check_same_thread": False}
    )
    storage = root / "storage"
    documents_api.STORAGE = storage
    documents_api.DOCUMENTS = storage / "documents"
    applications_api.STORAGE = storage
    applications_api.SIGNATURES = storage / "signatures"
    files_api.STORAGE = storage


def _reset(root: Path) -> ResetReport:
    """열려 있는 DB 연결을 닫고 리셋한 뒤, 빈 상태로 다시 연결한다."""
    models.engine.dispose()
    report = reset_demo(root)
    _isolate(root)
    return report


def _seed_noise(app) -> None:
    """리셋 전에 '이전 시연의 찌꺼기'를 만들어 둔다.

    리셋이 실제로 무언가를 지운다는 것을 보이려면, 지울 것이 먼저 있어야 한다.
    """
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        _create_ds(client, name="이전시연", uploads=S2_UPLOADS)
    models.engine.dispose()


def main(argv: list[str] | None = None) -> int:
    from fastapi.testclient import TestClient

    from ..main import app

    parser = argparse.ArgumentParser(prog="python -m demo.backend.tests.run_p6_scenarios")
    parser.add_argument(
        "--live",
        action="store_true",
        help="임시 폴더가 아니라 진짜 demo/ 를 리셋하고 거기서 돌린다 (시연 직전 점검용)",
    )
    args = parser.parse_args(argv)

    tmp: Path | None = None
    if args.live:
        root = DEMO_ROOT
        print(f"[live] 진짜 데모 폴더를 리셋한다: {root}")
    else:
        tmp = Path(tempfile.mkdtemp(prefix="p6-scenarios-"))
        root = tmp
        print(f"[격리] 임시 폴더에서 돈다: {root}")
    _isolate(root)

    try:
        print("\n[0] 리셋이 실제로 지우는가")
        _seed_noise(app)
        before = _measure_root(root)
        check_true("리셋 전에 지울 것이 있다", before["files"] > 0)
        report = _reset(root)
        after = _measure_root(root)
        check("지운 대상", sorted(report.removed), ["demo.db", "storage"])
        check_true("지운 파일이 있다", report.deleted_files > 0)
        check("리셋 후 남은 파일", after["files"], 0)

        rounds: list[dict[str, dict[str, Any]]] = []
        for index in (1, 2):
            print(f"\n{'=' * 62}\n  {index}회차 — 리셋 직후 상태에서 S1~S10 연속 실행\n{'=' * 62}")
            if index > 1:
                _reset(root)
            with TestClient(app) as client:
                check(f"{index}회차 시작 시 신청 건", count_rows()["application"], 0)
                results = run_round(client)
                rows = count_rows()
            models.engine.dispose()
            _isolate(root)

            for scenario in SCENARIOS:
                verify(scenario, results[scenario])

            print(f"\n[{index}회차 적재 결과]")
            check("신청 건", rows["application"], 5)
            check("업로드 서류", rows["document"], 22)
            check("심사 결과", rows["review"], 4)
            check("동의 기록", rows["consent"], 14)
            check("지원 항목 회차", rows["subsidy_item"], 4)
            rounds.append(results)

        print("\n[멱등성] 1회차와 2회차의 결과가 글자 하나까지 같은가")
        for scenario in SCENARIOS:
            same = rounds[0][scenario] == rounds[1][scenario]
            check(f"{scenario} 재현", same, True)
            if not same:
                for key in rounds[0][scenario]:
                    if rounds[0][scenario][key] != rounds[1][scenario].get(key):
                        print(
                            f"         {key}: 1회차={rounds[0][scenario][key]!r} "
                            f"2회차={rounds[1][scenario].get(key)!r}"
                        )

        print("\n[뒷정리] 시연은 리셋된 상태에서 시작한다")
        _reset(root)
        check("정리 후 남은 파일", _measure_root(root)["files"], 0)
    finally:
        models.engine.dispose()
        if tmp is not None:
            shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n통과 {_passed} / 실패 {len(_failed)}")
    if _failed:
        for name in _failed:
            print(f"  - {name}")
        return 1
    return 0


def _measure_root(root: Path) -> dict[str, int]:
    """리셋 대상(demo.db · storage/)에 남아 있는 파일 수."""
    files = 0
    for name in ("demo.db", "storage"):
        path = root / name
        if not path.exists():
            continue
        if path.is_dir():
            files += sum(1 for p in path.rglob("*") if p.is_file())
        else:
            files += 1
    return {"files": files}


if __name__ == "__main__":
    raise SystemExit(main())

"""제출 전 최종 확인 · 최종 제출 · 마이페이지 (P3).

여기서 세 가지가 이어진다.

  1. `GET  /final-check` — 아직 남은 부적합·누락을 한 화면에 모은다. 두배적금은
     **보완 요청이 없는 사업**이라, 제출 버튼을 누르기 전이 마지막 기회다.
  2. `POST /submit`       — 엔진 전체 파이프라인 + 심사표 100점 채점 → `review` 저장.
  3. `GET  /status`       — 마이페이지. **점수는 절대 싣지 않는다** (R5.3).

점수가 신청자에게 새어나가지 않게 하는 것이 이 파일의 유일한 금칙이다. 공고문
원문이 "평가결과는 공개하지 않음"이다. `/submit`과 `/status` 응답에는 점수·구간·
채점 근거가 들어가지 않는다 — 전부 `review` 테이블에만 남아 담당자 화면으로 간다.
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlmodel import select

from ..engine_adapter import (
    electronic_consent_row,
    inject_file_refs,
    run_pipeline,
    to_engine_applicant,
    to_engine_documents,
)
from ..models import (
    STATUS_DECIDED,
    STATUS_DRAFT,
    STATUS_REVIEWING,
    STATUS_SUBMITTED,
    UNASSIGNED_SLOT,
    Application,
    Review,
    get_session,
)
from ..rules.facts import build_facts, extract_region, parse_ymd
from ..rules.programs import DOUBLE_SAVINGS, get_program
from ..rules.required_docs import upload_slots
from ..rules.scoring import score_application
from .common import (
    checklist_for,
    document_dict,
    document_fact,
    list_consents,
    list_documents,
    load_application,
)

router = APIRouter(prefix="/api/applications", tags=["review"])

#: 마이페이지 진행 표시 5단계 (계획서 3.1절 [7]).
PROGRESS_STEPS = ["접수", "서류검토", "자격심사", "선정심사", "결과발표"]

#: 서식1에서 비어 있으면 제출할 수 없는 항목. 라벨은 서식 원문 표기를 쓴다.
REQUIRED_FORM1_FIELDS: list[tuple[str, str]] = [
    ("name", "신청자 이름"),
    ("birth", "생년월일"),
    ("address", "주소"),
    ("mobile", "연락처(휴대전화)"),
    ("transferIn", "전북특별자치도 최종 전입일"),
    ("householdSize", "가구원 수"),
    ("employedAt", "현 직장 취업일"),
    ("bankName", "입금 받을 계좌 — 은행명"),
    ("accountNo", "입금 받을 계좌 — 계좌번호"),
]

#: 동의 종류 → 서식 표기.
CONSENT_LABELS = {
    "privacy": "서식3 개인정보 수집·이용 동의",
    "unique_id": "서식3 고유식별정보 수집·이용 동의",
    "third_party": "서식4 개인(신용)정보 제3자 제공 동의",
    "admin_info": "서식5 행정정보 공동이용 사전동의",
}


def _has_value(value: Any) -> bool:
    if isinstance(value, dict):
        return all(str(v).strip() for v in value.values())
    if isinstance(value, list):
        return len(value) > 0
    return bool(str(value or "").strip())


def _blockers(app: Application) -> list[dict[str, Any]]:
    """제출을 막는 항목들. 각 항목에 '어디로 가면 고칠 수 있는지'를 같이 넣는다.

    사유만 나열하면 신청자는 화면을 처음부터 다시 훑는다. `goto`가 그걸 없앤다.
    """
    items: list[dict[str, Any]] = []
    form1 = app.form1_json or {}

    for key, label in REQUIRED_FORM1_FIELDS:
        if not _has_value(form1.get(key)):
            items.append(
                {
                    "kind": "form",
                    "target": key,
                    "label": label,
                    "message": f"{label}을(를) 입력해 주세요.",
                    "goto": "form1",
                }
            )

    agreed = {c.consent_type for c in list_consents(app.id or 0) if c.agreed}
    for consent_type, label in CONSENT_LABELS.items():
        if consent_type not in agreed:
            items.append(
                {
                    "kind": "consent",
                    "target": consent_type,
                    "label": label,
                    "message": f"{label}에 동의해야 제출할 수 있습니다.",
                    "goto": "consent",
                }
            )

    checklist = checklist_for(app)
    documents = list_documents(app.id or 0)
    by_slot = {d.slot_key: d for d in documents}

    for req in upload_slots(checklist):
        doc = by_slot.get(req.slot_key)
        if doc is None:
            if req.required:
                items.append(
                    {
                        "kind": "document",
                        "target": req.slot_key,
                        "label": req.label,
                        "message": f"'{req.label}'을(를) 아직 올리지 않았습니다.",
                        "goto": "upload",
                    }
                )
            continue
        if doc.stage1_status == "FAIL":
            reason = (doc.findings_json or [{}])[0].get("message", "부적합 판정입니다.")
            items.append(
                {
                    "kind": "document",
                    "target": req.slot_key,
                    "label": req.label,
                    "message": reason,
                    "goto": "upload",
                }
            )

    if not (app.doc_context_json or {}).get("work_category"):
        items.append(
            {
                "kind": "context",
                "target": "work_category",
                "label": "근로유형",
                "message": "근로유형을 선택해야 근로확인서류가 확정됩니다.",
                "goto": "upload",
            }
        )

    return items


def _warnings(app: Application, documents: list[Any]) -> list[str]:
    """제출을 막지는 않지만 반드시 읽혀야 하는 경고."""
    program = get_program(app.program_code)
    notes: list[str] = []
    if not program.allows_supplement:
        notes.append(
            "이 사업은 서류 미비 시 별도의 보완(추가서류) 요청 없이 선발에서 제외됩니다. "
            "제출 전에 아래 내용을 반드시 확인해 주세요."
        )
    else:
        notes.append(
            f"서류 미비 시 {program.supplement_days}일 내 보완 안내가 발송됩니다."
        )
    review_count = sum(1 for d in documents if d.stage1_status == "NEEDS_REVIEW")
    if review_count:
        notes.append(
            f"확인필요 서류가 {review_count}건 있습니다. 제출은 가능하지만 담당자가 원본을 "
            "직접 확인합니다. 더 선명한 파일이 있다면 교체하는 편이 안전합니다."
        )
    unassigned = sum(1 for d in documents if d.slot_key == UNASSIGNED_SLOT)
    if unassigned:
        notes.append(
            f"어느 서류인지 판별하지 못한 페이지가 {unassigned}건 있습니다. 필요 없는 "
            "페이지라면 삭제해 주세요."
        )
    return notes


def _form_summary(app: Application) -> list[dict[str, str]]:
    """최종 확인 화면에 그대로 뿌리는 입력값 요약. 점수와 무관한 값만 담는다."""
    form1 = app.form1_json or {}

    def ymd(key: str) -> str:
        parsed = parse_ymd(form1.get(key))
        return parsed.isoformat() if parsed else ""

    return [
        {"label": "신청자 이름", "value": str(form1.get("name") or "")},
        {"label": "생년월일", "value": ymd("birth")},
        {"label": "성별", "value": str(form1.get("gender") or "")},
        {"label": "주소", "value": str(form1.get("address") or "")},
        {"label": "연락처", "value": str(form1.get("mobile") or "")},
        {"label": "최종 전입일", "value": ymd("transferIn")},
        {"label": "가구 특성", "value": str(form1.get("householdType") or "")},
        {"label": "가구원 수", "value": str(form1.get("householdSize") or "")},
        {"label": "근로유형", "value": str(form1.get("workType") or "")},
        {"label": "현 직장 취업일", "value": ymd("employedAt")},
        {"label": "근무처", "value": str(form1.get("workplaceName") or "")},
        {"label": "저축목적", "value": str(form1.get("savingPurpose") or "")},
        {
            "label": "입금 받을 계좌",
            "value": " ".join(
                str(form1.get(k) or "") for k in ("bankName", "accountNo", "accountHolder")
            ).strip(),
        },
    ]


@router.get("/{application_id}/final-check")
def final_check(application_id: int) -> dict[str, Any]:
    """제출 전 최종 확인 (계획서 3.1절 [5])."""
    app = load_application(application_id)
    program = get_program(app.program_code)
    documents = list_documents(application_id)
    blockers = _blockers(app)
    return {
        "application_no": app.application_no,
        "program_name": program.name,
        "allows_supplement": program.allows_supplement,
        "supplement_days": program.supplement_days,
        "status": app.status,
        "can_submit": not blockers and app.status == STATUS_DRAFT,
        "already_submitted": app.status != STATUS_DRAFT,
        "blockers": blockers,
        "warnings": _warnings(app, documents),
        "form_summary": _form_summary(app),
        "documents": [document_dict(d) for d in documents],
    }


def _run_review(app: Application) -> Review:
    """엔진 파이프라인 + 심사표 채점을 한 번에 돌리고 `Review` 행을 만든다."""
    program = get_program(app.program_code)
    form1 = app.form1_json or {}
    documents = list_documents(app.id or 0)

    # 병합 PDF의 미배정 페이지는 심사 대상이 아니다. 담당자 확인용으로만 남는다.
    rows = [document_fact(d) for d in documents if d.slot_key != UNASSIGNED_SLOT]

    # 서식5는 파일이 아니라 전자서명 + 동의 로그로 갈음한다 (R1.2 / E4).
    consents = list_consents(app.id or 0)
    admin_consent = next(
        (c for c in consents if c.consent_type == "admin_info" and c.agreed), None
    )
    if admin_consent and not any(r["slot_key"] == "admin_info_consent" for r in rows):
        rows.append(
            electronic_consent_row(
                admin_consent.agreed_at.date(), admin_consent.signature_path
            )
        )

    # --- 심사표 채점 (엔진에 점수 기능이 없다 — E9) ---
    facts = build_facts(form1, rows)
    sheet = score_application(
        facts,
        announcement_date=program.announcement_date,
        age_basis_date=program.age_basis_date,
    )

    # --- 엔진 파이프라인 ---
    applicant = to_engine_applicant(
        application_no=app.application_no,
        name=str(form1.get("name") or ""),
        birth_date=facts.birth_date,
        residence_region=extract_region(
            str(form1.get("address") or ""), list(program.quota_by_region or {})
        ),
        program=program,
        income_percent=sheet.income_percent,
    )
    result = run_pipeline(applicant, to_engine_documents(rows))
    payload = inject_file_refs(result.review_payload, rows)

    if payload is None:
        # PASS면 엔진이 payload를 만들지 않는다. 담당자 화면은 항상 같은 모양을
        # 기대하므로 최소 형태로 채워 둔다.
        payload = {
            "applicant_id": app.application_no,
            "name": applicant.name,
            "program": applicant.program,
            "submitted_at": datetime.now().isoformat(timespec="seconds"),
            "final_status": result.status.value,
            "documents": [
                {
                    "doc_type": r.get("doc_type"),
                    "file_format": r.get("file_format"),
                    "ocr_confidence": round(float(r.get("confidence") or 0.0), 3),
                    "file_ref": None,
                }
                for r in rows
            ],
            "reasons": [],
            "recommended_action": "자동 승인",
        }
        inject_file_refs(payload, rows)

    return Review(
        application_id=app.id or 0,
        final_status=result.status.value,
        stage1_status=result.stage1.status.value,
        stage2_status=result.stage2.status.value if result.stage2 else None,
        score_json=sheet.as_dict(),
        total_score=sheet.total,
        tiebreak_json=sheet.tiebreak,
        review_payload_json=payload,
    )


@router.post("/{application_id}/submit")
def submit(application_id: int) -> dict[str, Any]:
    """최종 제출 → 전체 파이프라인 + 채점 → `review` 저장.

    응답에는 **점수를 넣지 않는다**. 접수됐다는 사실과 다음 절차만 돌려준다.
    """
    app = load_application(application_id)
    if app.status != STATUS_DRAFT:
        raise HTTPException(400, "이미 제출된 신청입니다.")

    blockers = _blockers(app)
    if blockers:
        raise HTTPException(
            400,
            f"아직 제출할 수 없습니다. 확인이 필요한 항목이 {len(blockers)}건 있습니다.",
        )

    review = _run_review(app)

    with get_session() as s:
        row = s.get(Application, application_id)
        if row is None:
            raise HTTPException(404, "신청 건을 찾을 수 없습니다.")
        row.status = STATUS_SUBMITTED
        row.submitted_at = datetime.now()
        row.updated_at = row.submitted_at
        s.add(row)
        # 데모는 재제출 시나리오를 다루지 않는다. 기존 심사 결과는 지우고 다시 쓴다.
        for old in s.exec(
            select(Review).where(Review.application_id == application_id)
        ).all():
            s.delete(old)
        s.add(review)
        s.commit()
        submitted_at = row.submitted_at

    program = get_program(app.program_code)
    return {
        "application_no": app.application_no,
        "submitted_at": submitted_at.isoformat(timespec="seconds") if submitted_at else None,
        "status": STATUS_SUBMITTED,
        "message": "신청이 접수되었습니다.",
        "next_steps": [
            "읍·면·동에서 구비서류 완비 여부를 확인합니다.",
            "자격요건(소득·거주·근로·연령)과 제외대상을 확인합니다.",
            "시군이 심사표를 취합해 도에 제출하고, 도·청년허브센터가 최종 선정합니다.",
        ],
        "notice": (
            "평가결과(심사 점수)는 공개하지 않습니다. 최종 선정 여부만 결과발표 시 안내됩니다."
            if program.code == DOUBLE_SAVINGS
            else "접수 순서대로 심사합니다."
        ),
    }


@router.get("/{application_id}/status")
def status(application_id: int) -> dict[str, Any]:
    """마이페이지 (R5.3).

    ⚠️ 이 응답에는 점수·구간·채점 근거가 **절대** 들어가지 않는다. `review` 테이블을
    읽더라도 진행 단계를 정하는 데만 쓴다.
    """
    app = load_application(application_id)
    program = get_program(app.program_code)
    documents = list_documents(application_id)

    with get_session() as s:
        review = s.exec(
            select(Review).where(Review.application_id == application_id)
        ).first()

    if app.status == STATUS_DRAFT:
        current = -1
    elif app.status == STATUS_DECIDED:
        current = 4
    elif app.status == STATUS_REVIEWING or (review and review.officer_decision):
        current = 2
    else:
        current = 1  # 제출 완료 → 서류검토 진행 중

    consents = [
        {
            "consent_type": c.consent_type,
            "label": CONSENT_LABELS.get(c.consent_type, c.consent_type),
            "agreed": c.agreed,
            "agreed_at": c.agreed_at.isoformat(timespec="seconds"),
            "signature_kind": c.signature_kind,
        }
        for c in list_consents(application_id)
    ]

    return {
        "application_no": app.application_no,
        "program_name": program.name,
        "status": app.status,
        "submitted_at": (
            app.submitted_at.isoformat(timespec="seconds") if app.submitted_at else None
        ),
        "progress": [
            {"label": label, "state": _step_state(i, current)}
            for i, label in enumerate(PROGRESS_STEPS)
        ],
        "result_notice": (
            "평가결과는 공개하지 않습니다. 심사 점수는 안내되지 않으며, "
            "최종 선정 여부만 결과발표 시 확인할 수 있습니다."
        ),
        "documents": [document_dict(d) for d in documents],
        "consents": consents,
        "call_center": program.call_center,
    }


def _step_state(index: int, current: int) -> str:
    if current < 0:
        return "todo"
    if index < current:
        return "done"
    if index == current:
        return "current"
    return "todo"

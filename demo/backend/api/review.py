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

import math
from datetime import datetime, timedelta
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
from ..forms import values as form_values
from ..forms.email import is_valid_email, normalize_email
from ..models import (
    STATUS_DECIDED,
    STATUS_DRAFT,
    STATUS_REVIEWING,
    STATUS_SUBMITTED,
    UNASSIGNED_SLOT,
    Application,
    Document,
    Review,
    get_session,
)
from ..rules.facts import build_facts, extract_region, parse_ymd
from ..rules.household import overlap_members, qualification_members
from ..rules.doc_types import DocType
from ..rules.criteria import for_application, read_criteria, supplement_for_application
from ..rules.programs import DOUBLE_SAVINGS, JOB_PACKAGE, ProgramConfig, get_program
from ..rules.required_docs import upload_slots
from ..rules.scoring import ScoreSheet, score_application
from ..rules.subsidy import get_limit
from .common import (
    checklist_for,
    document_dict,
    document_fact,
    list_consents,
    list_documents,
    load_application,
    subsidy_estimate,
    subsidy_rows,
)

router = APIRouter(prefix="/api/applications", tags=["review"])

#: 마이페이지 진행 표시 5단계 (계획서 3.1절 [7]). 두배적금의 선발절차다.
PROGRESS_STEPS = ["접수", "서류검토", "자격심사", "선정심사", "결과발표"]

#: 사업별 진행 단계. 취업패키지는 사업계획서 「3. 추진체계」를 그대로 따른다
#: (접수 → 서류검토 → 지원대상자 및 보완 안내(1차) → 보완서류 검토 → 지원금 지급).
PROGRESS_STEPS_BY_PROGRAM: dict[str, list[str]] = {
    DOUBLE_SAVINGS: PROGRESS_STEPS,
    JOB_PACKAGE: ["접수", "서류검토", "지원대상자·보완 안내", "보완서류 검토", "지원금 지급"],
}

NEXT_STEPS_DEFAULT = [
    "읍·면·동에서 구비서류 완비 여부를 확인합니다.",
    "자격요건(소득·거주·근로·연령)과 제외대상을 확인합니다.",
    "시군이 심사표를 취합해 도에 제출하고, 도·청년허브센터가 최종 선정합니다.",
]

#: 제출 직후 안내하는 다음 절차. 사업의 추진체계가 그대로 들어간다.
NEXT_STEPS: dict[str, list[str]] = {
    DOUBLE_SAVINGS: NEXT_STEPS_DEFAULT,
    JOB_PACKAGE: [
        "전북청년허브센터가 항목별 제출서류를 검토합니다.",
        "선착순에 따라 지원대상자를 안내하고, 서류가 미비하면 7일 내 보완을 안내합니다.",
        "미보완 시 지원대상에서 제외되고 후순위자가 선정됩니다.",
        "보완서류 검토 후 최종 지원대상자를 안내하고, 월별 취합해 10일 내 본인 명의 계좌로 지급합니다.",
    ],
}

#: 동의 종류 → 서식 표기. 어느 동의를 받아야 하는지는 사업이 정한다
#: (`ProgramConfig.consent_types`) — 취업패키지에는 서식5가 없다.
CONSENT_LABELS = {
    "privacy": "서식3 개인정보 수집·이용 동의",
    "unique_id": "서식3 고유식별정보 수집·이용 동의",
    "third_party": "서식4 개인(신용)정보 제3자 제공 동의",
    "admin_info": "서식5 행정정보 공동이용 사전동의",
}

#: 년·월·일 3분할로 받는 입력값. 요약에서 ISO 날짜로 합쳐 보여준다.
DATE_FIELDS = {"birth", "transferIn", "employedAt"}


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
    program = get_program(app.program_code)
    form1 = app.form1_json or {}
    email = form1.get("email")
    normalized_email = normalize_email(email) if isinstance(email, str) else ""
    invalid_email = bool(normalized_email) and not is_valid_email(normalized_email)

    for key, label in program.required_form_fields:
        value = form1.get(key)
        if key == "email" and invalid_email:
            items.append({
                "kind": "form",
                "target": key,
                "label": label,
                "message": "이메일 형식을 확인해 주세요.",
                "goto": "form1",
            })
        elif not _has_value(value):
            # 서식 안에서 첨부하는 서류(통장 사본 등)는 '입력'이 아니라 '첨부'다.
            verb = "첨부" if key.endswith("FileName") else "입력"
            items.append(
                {
                    "kind": "form",
                    "target": key,
                    "label": label,
                    "message": f"{label}을(를) {verb}해 주세요.",
                    "goto": "form1",
                }
            )

    if invalid_email and not any(key == "email" for key, _ in program.required_form_fields):
        items.append({
            "kind": "form",
            "target": "email",
            "label": "이메일",
            "message": "이메일 형식을 확인해 주세요.",
            "goto": "form1",
        })

    # 지원 항목을 고르는 사업은 항목 선택이 곧 신청 내용이다. 하나도 고르지
    # 않았으면 제출할 것이 없다.
    if program.has_subsidy_items:
        rows = subsidy_rows(app.id or 0)
        if not rows:
            items.append(
                {
                    "kind": "subsidy",
                    "target": "subsidy_items",
                    "label": "지원 항목",
                    "message": "지원받을 항목을 최소 1개 이상 선택해 주세요.",
                    "goto": "subsidy",
                }
            )
        for row in rows:
            criteria = read_criteria(for_application(app))
            limit = get_limit(row.item_type, criteria["subsidy_catalog"])
            if limit.actual_cost and not row.receipt_amount:
                items.append(
                    {
                        "kind": "subsidy",
                        "target": row.item_type,
                        "label": f"{limit.label} {row.count_index}회차",
                        "message": (
                            f"{limit.label} {row.count_index}회차의 결제영수증 금액을 "
                            "입력해야 지급액이 확정됩니다."
                        ),
                        "goto": "subsidy",
                    }
                )

    agreed = {c.consent_type for c in list_consents(app.id or 0) if c.agreed}
    for consent_type in program.consent_types:
        label = CONSENT_LABELS.get(consent_type, consent_type)
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
    criteria_version = for_application(app)
    criteria = read_criteria(criteria_version)
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

    # 근로확인서류가 있는 사업에서만 근로유형을 묻는다. 취업패키지는 근로요건이
    # 없으므로 이 항목 자체가 없다.
    if program.has_work_requirement and not (app.doc_context_json or {}).get(
        "work_category"
    ):
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
    supplement = supplement_for_application(app)
    notes: list[str] = []
    if not supplement["allowed"]:
        notes.append(
            "이 사업은 서류 미비 시 별도의 보완(추가서류) 요청 없이 선발에서 제외됩니다. "
            "제출 전에 아래 내용을 반드시 확인해 주세요."
        )
    else:
        notes.append(
            f"서류 미비 시 {supplement['days']}일 내 보완 안내가 발송됩니다."
        )
    if get_program(app.program_code).selection == "scored":
        facts = build_facts(app.form1_json or {}, [document_fact(d) for d in documents])
        if facts.household_size_form_mismatch:
            notes.append("가구원 수는 건강보험 자격확인서 기준으로 판정합니다.")
        elif facts.household_size_issue:
            notes.append(facts.household_size_issue)
    review_count = sum(1 for d in documents if d.stage1_status == "NEEDS_REVIEW")
    if review_count:
        notes.append(
            f"담당자 확인 예정 서류가 {review_count}건 있습니다. 제출은 가능하지만 담당자가 원본을 "
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
    """최종 확인 화면에 그대로 뿌리는 입력값 요약. 점수와 무관한 값만 담는다.

    항목과 순서는 사업 설정(`summary_fields`)에서 나온다. 취업패키지는 거주기간·
    가구원수·근로사항을 아예 묻지 않으므로 요약에도 뜨지 않는다.
    """
    program = get_program(app.program_code)
    form1 = app.form1_json or {}

    def value_of(key: str) -> str:
        if key == "account":
            return " ".join(
                str(form1.get(k) or "")
                for k in ("bankName", "accountNo", "accountHolder")
            ).strip()
        if key in DATE_FIELDS:
            parsed = parse_ymd(form1.get(key))
            return parsed.isoformat() if parsed else ""
        return str(form1.get(key) or "")

    return [
        {"label": label, "value": value_of(key)}
        for key, label in program.summary_fields
    ]


def _queue_position(app: Application) -> int:
    """선착순 접수 순번.

    같은 사업에서 이 건보다 먼저(또는 같은 시각에) 제출된 건의 수다. 아직 제출
    전이면 '지금 내면 몇 번째인가'를 보여주기 위해 다음 순번을 돌려준다.
    """
    with get_session() as s:
        rows = list(
            s.exec(
                select(Application)
                .where(Application.program_code == app.program_code)
                .where(Application.status != STATUS_DRAFT)
            ).all()
        )
    submitted = [r for r in rows if r.submitted_at is not None]
    if app.submitted_at is None:
        return len(submitted) + 1
    return sum(
        1
        for r in submitted
        if r.submitted_at is not None and r.submitted_at <= app.submitted_at
    )


def _first_come(app: Application, program: ProgramConfig) -> dict[str, Any] | None:
    """선착순 안내 (R6).

    두배적금은 선착순이 아니므로 None이다. 취업패키지는 "예산 소진 시 조기 마감,
    총 900건"이라 접수 순번이 곧 선정 순서다.
    """
    if not program.is_first_come:
        return None
    position = _queue_position(app)
    quota = program.quota_total
    remaining = max(0, quota - position) if quota is not None else None
    return {
        "enabled": True,
        "position": position,
        "quota": quota,
        "remaining": remaining,
        "submitted": app.submitted_at is not None,
        "notice": (
            f"이 사업은 선착순입니다. 접수 순번 {position}번 / 총 지원규모 "
            f"{quota:,}건 (예산 소진 시 조기 마감)"
            if quota is not None
            else "이 사업은 선착순입니다. 예산 소진 시 조기 마감됩니다."
        ),
    }


def _supplement(
    app: Application, program: ProgramConfig, review: Review | None
) -> dict[str, Any] | None:
    """서류 보완 안내와 기한 카운트다운 (E12).

    두배적금은 보완 자체가 없어 None이다. 취업패키지는 "7일 내 서류 보완안내 /
    미보완시 지원대상자 제외 및 후순위자 선정"이므로, 남은 일수를 숫자로 보여줘야
    한다. 기한이 지나면 후순위자에게 자리가 넘어간다는 사실도 같이 적는다.
    """
    policy = supplement_for_application(app)
    if not policy["allowed"]:
        return None
    deadline = review.supplement_deadline if review else None
    if deadline is None:
        return None

    seconds = (deadline - datetime.now()).total_seconds()
    expired = seconds <= 0
    days_left = max(0, math.ceil(seconds / 86400))
    hours_left = max(0, int(seconds // 3600))

    documents = list_documents(app.id or 0)
    by_slot = {d.slot_key: d for d in documents}
    targets: list[dict[str, str]] = []
    for req in upload_slots(checklist_for(app)):
        doc = by_slot.get(req.slot_key)
        if doc is None and req.required:
            targets.append({"label": req.label, "reason": "아직 올리지 않았습니다."})
        elif doc is not None and doc.stage1_status != "PASS":
            reason = (doc.findings_json or [{}])[0].get("message", "확인이 필요합니다.")
            targets.append({"label": req.label, "reason": reason})

    return {
        "days": policy["days"],
        "deadline": deadline.isoformat(timespec="seconds"),
        "days_left": days_left,
        "hours_left": hours_left,
        "expired": expired,
        "targets": targets,
        "notice": (
            "보완 기한이 지났습니다. 미보완 시 후순위자가 선정됩니다."
            if expired
            else f"{policy['days']}일 내에 보완하지 않으면 지원대상에서 제외되고 "
            "후순위자가 선정됩니다."
        ),
    }


def _load_review(application_id: int) -> Review | None:
    with get_session() as s:
        return s.exec(
            select(Review).where(Review.application_id == application_id)
        ).first()


@router.get("/{application_id}/final-check")
def final_check(application_id: int) -> dict[str, Any]:
    """제출 전 최종 확인 (계획서 3.1절 [5])."""
    app = load_application(application_id)
    program = get_program(app.program_code)
    supplement = supplement_for_application(app)
    documents = list_documents(application_id)
    blockers = _blockers(app)
    return {
        "application_no": app.application_no,
        "program_code": program.code,
        "program_name": program.name,
        "allows_supplement": supplement["allowed"],
        "supplement_days": supplement["days"],
        "selection": program.selection,
        "first_come": _first_come(app, program),
        "subsidy": (
            subsidy_estimate(application_id) if program.has_subsidy_items else None
        ),
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
    criteria_version = for_application(app)
    criteria = read_criteria(criteria_version)

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
    #
    # 점수제 사업만 채점한다. 취업패키지는 **선착순**이라 심사표 자체가 없고,
    # 억지로 0점짜리 심사표를 만들면 담당자 목록에서 최하위로 줄을 서게 된다.
    facts = build_facts(form1, rows, criteria.get("nhis_payment_months"))
    sheet: ScoreSheet | None = None
    if program.selection == "scored":
        sheet = score_application(
            facts,
            announcement_date=datetime.fromisoformat(criteria["announcement_date"]).date(),
            age_basis_date=program.age_basis_date,
        )

    # --- 엔진 파이프라인 ---
    applicant = to_engine_applicant(
        application_no=app.application_no,
        name=str(form1.get("name") or ""),
        birth_date=facts.birth_date,
        residence_region=extract_region(
            str(form1.get("address") or ""), program.target_regions
        ),
        program=program,
        # 소득요건이 없는 사업은 소득값을 넘기지 않는다. 엔진 2단계가 소득분위
        # 검사를 건너뛴다.
        income_percent=sheet.income_percent if sheet else None,
    )
    result = run_pipeline(applicant, to_engine_documents(rows), checklist_for(app))
    payload = inject_file_refs(result.review_payload, rows)

    household_needs_review = bool(
        program.selection == "scored" and facts.household_size_issue
    )
    if household_needs_review:
        if payload is None:
            payload = {
                "applicant_id": app.application_no,
                "name": applicant.name,
                "program": applicant.program,
                "submitted_at": datetime.now().isoformat(timespec="seconds"),
                "final_status": "NEEDS_REVIEW",
                "documents": [],
                "reasons": [],
                "recommended_action": "담당자 재검토 필요",
            }
        payload["final_status"] = "NEEDS_REVIEW"
        payload["recommended_action"] = "담당자 재검토 필요"
        reasons = payload.setdefault("reasons", [])
        reasons.append({
            "stage": "stage2_eligibility",
            "code": "HEALTH_INSURANCE_HOUSEHOLD_SIZE_UNCONFIRMED",
            "message": facts.household_size_issue,
            "doc_type": str(DocType.NHIS_QUALIFICATION),
        })
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

    if facts.household_size_form_mismatch:
        form_count, certificate_count = facts.household_size_form_mismatch
        reference_note = {
            "code": "APPLICATION_HOUSEHOLD_SIZE_DIFFERS",
            "message": "신청서 입력 가구원 수와 건강보험 자격확인서 값이 다릅니다. 자격확인서 값으로 판정했습니다.",
            "application_count": form_count,
            "certificate_count": certificate_count,
        }
        payload["household_reference_note"] = reference_note
        payload.setdefault("reasons", []).append({
            "stage": "stage2_eligibility",
            **reference_note,
            "doc_type": str(DocType.NHIS_QUALIFICATION),
        })

    # 보완이 허용되는 사업에서 미비가 남은 채로 접수되면, 그 순간부터 기한이 돈다.
    # (추진체계: 지원대상자 및 서류보완 안내(1차) → 7일 내 서류 보완안내)
    supplement_deadline: datetime | None = None
    supplement = supplement_for_application(app)
    if supplement["allowed"] and result.status.value != "PASS":
        supplement_deadline = datetime.now() + timedelta(days=supplement["days"] or 0)

    return Review(
        application_id=app.id or 0,
        final_status="NEEDS_REVIEW" if household_needs_review else result.status.value,
        stage1_status=result.stage1.status.value,
        stage2_status=(
            "NEEDS_REVIEW" if household_needs_review
            else result.stage2.status.value if result.stage2 else None
        ),
        score_json=sheet.as_dict() if sheet else {},
        total_score=sheet.total if sheet else None,
        tiebreak_json=sheet.tiebreak if sheet else [],
        supplement_deadline=supplement_deadline,
        review_payload_json=payload,
    )


def _append_household_link(
    review: Review,
    other: Application,
    shared: list[dict[str, str]],
) -> None:
    payload = dict(review.review_payload_json or {})
    related = list(payload.get("related_applications") or [])
    link = {"application_id": other.id, "application_no": other.application_no}
    if link not in related:
        related.append(link)
    payload["related_applications"] = related

    matches = list(payload.get("household_overlap_details") or [])
    detail = {
        "application_id": other.id,
        "application_no": other.application_no,
        "members": shared,
        "basis": "같은 사업·같은 연도 신청서의 건강보험 자격확인서 가구원 목록에서 성명과 생년월일이 일치했습니다.",
    }
    if not any(row.get("application_id") == other.id for row in matches):
        matches.append(detail)
    payload["household_overlap_details"] = matches

    reasons = list(payload.get("reasons") or [])
    if not any(
        row.get("code") == "HEALTH_INSURANCE_HOUSEHOLD_OVERLAP"
        and row.get("related_application_id") == other.id
        for row in reasons
    ):
        reasons.append({
            "stage": "stage2_eligibility",
            "code": "HEALTH_INSURANCE_HOUSEHOLD_OVERLAP",
            "message": "같은 사업·같은 연도 신청서의 건강보험 자격확인서 가구원 정보가 일부 겹쳐 담당자 재검토가 필요합니다.",
            "doc_type": str(DocType.NHIS_QUALIFICATION),
            "related_application_id": other.id,
            "related_application_no": other.application_no,
            "matched_members": shared,
        })
    payload["reasons"] = reasons
    payload["final_status"] = "NEEDS_REVIEW"
    payload["recommended_action"] = "담당자 재검토 필요"
    review.review_payload_json = payload
    review.final_status = "NEEDS_REVIEW"
    review.stage2_status = "NEEDS_REVIEW"


def _link_overlapping_households(app: Application, current_review: Review) -> None:
    """같은 사업·신청연도 자격확인서의 겹치는 가구원을 양쪽 담당자 기록에 링크한다."""
    if get_program(app.program_code).selection != "scored":
        return
    with get_session() as s:
        current_docs = list(s.exec(
            select(Document).where(Document.application_id == app.id)
        ).all())
        current_members = qualification_members([document_fact(d) for d in current_docs])
        if not current_members:
            return
        candidates = list(s.exec(
            select(Application).where(Application.program_code == app.program_code)
        ).all())
        candidates = [
            candidate for candidate in candidates
            if candidate.id != app.id and candidate.created_at.year == app.created_at.year
            and candidate.status != STATUS_DRAFT
        ]
        if not candidates:
            return
        candidate_ids = [candidate.id for candidate in candidates if candidate.id is not None]
        docs = list(s.exec(
            select(Document).where(Document.application_id.in_(candidate_ids))
        ).all())
        docs_by_app: dict[int, list[Any]] = {}
        for document in docs:
            docs_by_app.setdefault(document.application_id, []).append(document)

        current_changed = False
        for candidate in candidates:
            candidate_docs = docs_by_app.get(candidate.id or 0, [])
            candidate_members = qualification_members([document_fact(d) for d in candidate_docs])
            shared = overlap_members(current_members, candidate_members)
            if not shared:
                continue
            previous = s.exec(
                select(Review).where(Review.application_id == candidate.id)
            ).first()
            if previous is None:
                continue
            _append_household_link(current_review, candidate, shared)
            _append_household_link(previous, app, shared)
            candidate.status = STATUS_REVIEWING
            candidate.updated_at = datetime.now()
            # 기존 담당자 결정은 새 근거가 발견되었으므로 다시 확인받는다.
            previous.officer_role = None
            previous.officer_decision = None
            previous.officer_memo = None
            previous.decided_at = None
            s.add(previous)
            s.add(candidate)
            current_changed = True
        if current_changed:
            current_review.final_status = "NEEDS_REVIEW"
            current_review.stage2_status = "NEEDS_REVIEW"
            s.commit()


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
    _link_overlapping_households(app, review)

    with get_session() as s:
        row = s.get(Application, application_id)
        if row is None:
            raise HTTPException(404, "신청 건을 찾을 수 없습니다.")
        row.status = STATUS_SUBMITTED
        row.submitted_at = form_values.submission_timestamp()
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
    app = load_application(application_id)
    saved = _load_review(application_id)
    return {
        "application_no": app.application_no,
        "submitted_at": submitted_at.isoformat(timespec="seconds") if submitted_at else None,
        "status": STATUS_SUBMITTED,
        "message": "신청이 접수되었습니다.",
        "next_steps": list(NEXT_STEPS.get(program.code, NEXT_STEPS_DEFAULT)),
        "first_come": _first_come(app, program),
        "supplement": _supplement(app, program, saved),
        "subsidy": (
            subsidy_estimate(application_id) if program.has_subsidy_items else None
        ),
        "notice": (
            "선착순 사업입니다. 접수 순서대로 심사하며 예산 소진 시 조기 마감됩니다."
            if program.is_first_come
            else "평가결과(심사 점수)는 공개하지 않습니다. 최종 선정 여부만 결과발표 시 안내됩니다."
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

    steps = PROGRESS_STEPS_BY_PROGRAM.get(program.code, PROGRESS_STEPS)
    return {
        "application_no": app.application_no,
        "program_code": program.code,
        "program_name": program.name,
        "status": app.status,
        "submitted_at": (
            app.submitted_at.isoformat(timespec="seconds") if app.submitted_at else None
        ),
        "progress": [
            {"label": label, "state": _step_state(i, current)}
            for i, label in enumerate(steps)
        ],
        "result_notice": (
            "선착순 사업입니다. 접수 순서대로 심사하며 예산 소진 시 조기 마감되고, "
            "선정 결과는 문자·전화로 개별 안내됩니다."
            if program.is_first_come
            else "평가결과는 공개하지 않습니다. 심사 점수는 안내되지 않으며, "
            "최종 선정 여부만 결과발표 시 확인할 수 있습니다."
        ),
        # 선착순 순번과 보완 기한. 두배적금은 둘 다 None이다(점수제·보완 불가).
        "first_come": _first_come(app, program),
        "supplement": _supplement(app, program, review),
        "subsidy": (
            subsidy_estimate(application_id) if program.has_subsidy_items else None
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

"""라우터들이 같이 쓰는 조회·직렬화 도우미.

업로드(`documents.py`)와 제출·마이페이지(`review.py`)가 같은 체크리스트와 같은
서류 표현을 봐야 한다. 두 곳에 각각 두면 화면마다 판정이 달라 보이는 사고가 난다.
"""

from datetime import date
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlmodel import select

from ..models import Application, Consent, Document, SubsidyItem, get_session
from ..rules.criteria import for_application, issue_bounds, issue_rule_label, read_criteria
from ..rules.months import format_month_ranges
from ..rules.programs import get_program
from ..rules.required_docs import (
    ApplicantDocInput,
    DocRequirement,
    WorkCategory,
    build_checklist,
)
from ..rules.subsidy import ITEM_ORDER, Selection, estimate as estimate_subsidy

STORAGE = Path(__file__).resolve().parents[2] / "storage"


def load_application(application_id: int) -> Application:
    with get_session() as s:
        app = s.get(Application, application_id)
        if app is None:
            raise HTTPException(404, "신청 건을 찾을 수 없습니다.")
        return app


def subsidy_rows(application_id: int) -> list[SubsidyItem]:
    """고른 지원 항목 전부. 회차 순서를 보장한다."""
    with get_session() as s:
        rows = list(
            s.exec(
                select(SubsidyItem).where(SubsidyItem.application_id == application_id)
            ).all()
        )
    return sorted(rows, key=lambda r: (r.item_type, r.count_index))


def subsidy_selections(application_id: int) -> list[Selection]:
    """DB 행 → `rules/subsidy.Selection`. 체크리스트와 실비 계산이 같은 값을 본다."""
    grouped: dict[str, list[SubsidyItem]] = {}
    for row in subsidy_rows(application_id):
        grouped.setdefault(row.item_type, []).append(row)

    selections: list[Selection] = []
    # 사업계획서 지원내용 표의 순서(면접비 → 정장비 → 사진비 → 자격증)를 따른다.
    # DB 조회 순서를 그대로 쓰면 체크리스트 순서가 알파벳순으로 뒤바뀐다.
    for key in ITEM_ORDER:
        rows = grouped.get(str(key))
        if not rows:
            continue
        ordered = sorted(rows, key=lambda r: r.count_index)
        selections.append(
            Selection(
                item_type=key,
                count=len(ordered),
                receipts=[r.receipt_amount for r in ordered],
                linked_interview_indices=[r.linked_interview_index for r in ordered],
            )
        )
    return selections


def subsidy_estimate(application_id: int) -> dict[str, Any]:
    """예상 지원금. 신청자 화면·최종 확인·담당자 화면이 같은 계산을 쓴다."""
    app = load_application(application_id)
    criteria = read_criteria(for_application(app))
    return estimate_subsidy(subsidy_selections(application_id), criteria["subsidy_catalog"]).as_dict()


def doc_context(app: Application) -> ApplicantDocInput:
    raw = app.doc_context_json or {}
    category = raw.get("work_category")
    try:
        work_category = WorkCategory(category) if category else None
    except ValueError:
        work_category = None
    return ApplicantDocInput(
        work_category=work_category,
        admin_fixed_term=bool(raw.get("admin_fixed_term")),
        workplace_count=int(raw.get("workplace_count") or 1),
        handwritten_admin_consent=bool(raw.get("handwritten_admin_consent")),
        paper_admin_consent=bool((raw.get("paper_forms") or {}).get("서식5")),
        subsidy_selections=subsidy_selections(app.id or 0),
    )


def checklist_for(app: Application) -> list[DocRequirement]:
    criteria = read_criteria(for_application(app))
    rows = build_checklist(
        get_program(app.program_code), doc_context(app), criteria["subsidy_catalog"]
    )
    application_date = (app.submitted_at or app.created_at).date()
    for req in rows:
        basis = criteria["document_date_bases"].get(req.slot_key, req.date_basis)
        if req.slot_key not in {"resident_abstract"} and not any(
            req.slot_key.startswith(f"{item}_") for item in ("interview", "suit", "photo", "certificate")
        ):
            for key, value in criteria["document_date_bases"].items():
                if req.slot_key == key or req.slot_key.endswith(f"_{key}"):
                    basis = value
                    break
        req.date_basis = basis
        req.check_declared_date = req.upload and basis != "none"
        req.min_issue_date, req.max_issue_date = (
            issue_bounds(criteria, req.slot_key, application_date) if basis != "none" else (None, None)
        )
        if req.slot_key == "admin_info_consent" and ((app.doc_context_json or {}).get("paper_forms") or {}).get("서식5"):
            req.check_declared_date = False
            req.min_issue_date = req.max_issue_date = None
            req.date_basis = "none"
        if req.slot_key == "nhis_payment":
            req.premium_months = list(criteria["nhis_payment_months"])
        if req.slot_key == "nhis_acquisition_loss":
            req.recent_years = int(criteria["nhis_acquisition_loss_years"])
        req.notes = [n for n in req.notes if not n.startswith(("최근 ", "조회기간에 "))]
        req.notes.insert(0, issue_rule_label(criteria, req.slot_key, basis))
        if req.slot_key == "nhis_payment":
            months = criteria["nhis_payment_months"]
            years = sorted({month[:4] for month in months})
            prefix = f"{years[0]}년 " if len(years) == 1 else ""
            req.label = f"{prefix}건강보험료 납부확인서"
            req.notes.extend([
                f"조회기간에 {format_month_ranges(months)}이 포함되어야 합니다.",
                "실납부액이 아니라 고지금액 기준으로 심사합니다.",
            ])
        elif req.slot_key == "nhis_acquisition_loss":
            req.notes.append(f"최근 {criteria['nhis_acquisition_loss_years']}년 변동내역이 포함되어야 합니다.")
    return rows


def list_documents(application_id: int) -> list[Document]:
    with get_session() as s:
        return list(
            s.exec(select(Document).where(Document.application_id == application_id)).all()
        )


def list_documents_bulk(application_ids: list[int]) -> dict[int, list[Document]]:
    """여러 신청 건의 서류를 한 번에.

    담당자 목록은 행마다 서류 상태를 보여준다. 행마다 `list_documents`를 부르면
    한 페이지(20행)에 쿼리가 20번 나간다. 목록은 행 수가 정해진 자리이므로
    `IN` 하나로 읽고 신청 건별로 묶는다.
    """
    ids = [i for i in application_ids if i]
    if not ids:
        return {}
    with get_session() as s:
        rows = list(
            s.exec(select(Document).where(Document.application_id.in_(ids))).all()  # type: ignore[attr-defined]
        )
    grouped: dict[int, list[Document]] = {i: [] for i in ids}
    for d in rows:
        grouped.setdefault(d.application_id, []).append(d)
    return grouped


def list_consents(application_id: int) -> list[Consent]:
    with get_session() as s:
        return list(
            s.exec(select(Consent).where(Consent.application_id == application_id)).all()
        )


#: 신청자 화면에 보여줄 판독값. "내 서류를 제대로 읽었구나"를 확인하는 데 필요한 것만 둔다.
#: 전입일·가구원수·건강보험료(배점·소득 판정 근거), 판독 검증 결과 같은 담당자용 값은
#: 신청자 응답에 아예 싣지 않는다 — 화면에서 숨기는 것만으로는 개발자 도구에 그대로 보인다.
#: 담당자 화면은 officer.py가 따로 만들므로 전부 보인다.
APPLICANT_VISIBLE_FIELDS = ("발급일", "성명", "응시일", "결제금액", "동의여부", "서명잉크확인")


def document_dict(d: Document) -> dict[str, Any]:
    """업로드 서류 한 건의 신청자 화면 표현. 점수와 담당자용 판독값은 들어가지 않는다."""
    findings = [
        {
            key: finding[key]
            for key in ("code", "message", "how_to_fix", "link", "severity")
            if key in finding
        }
        for finding in (d.findings_json or [])
        if isinstance(finding, dict)
    ]
    nhis_subscriber_document = d.doc_type in {
        "건강보험료납부확인서", "건강보험자격확인서",
    } or d.expected_doc_type in {
        "건강보험료납부확인서", "건강보험자격확인서",
    }
    return {
        "document_id": d.id,
        "slot_key": d.slot_key,
        "file_name": Path(d.file_path).name,
        "file_format": d.file_format,
        # 신청자가 자기 서류를 다시 열어 보는 주소. 담당자 뷰어와 같은 인라인 스트리밍이다.
        "file_url": f"/api/files/{d.id}",
        "expected_doc_type": d.expected_doc_type,
        "detected_doc_type": d.doc_type,
        "declared_issue_date": (
            d.declared_issue_date.isoformat() if d.declared_issue_date else None
        ),
        "status": d.stage1_status,
        "findings": findings,
        "extracted": {
            k: v
            for k, v in ((d.ocr_json or {}).get("fields") or {}).items()
            if k in APPLICANT_VISIBLE_FIELDS and not (nhis_subscriber_document and k == "성명")
        },
        "ocr_confidence": (d.ocr_json or {}).get("confidence"),
        # 판독 계층·엔진·대체 사유는 담당자 화면에만 싣는다 (계층 이름이 곧 외부 엔진 이름이다).
        "elapsed_ms": (d.ocr_json or {}).get("elapsed_ms"),
        "page_index": d.page_index,
        "uploaded_at": d.uploaded_at.isoformat(timespec="seconds"),
    }


def document_fact(d: Document) -> dict[str, Any]:
    """채점·엔진 변환에 쓰는 표현. 판독 원값(fields·bboxes·신뢰도)을 그대로 싣는다."""
    ocr = d.ocr_json or {}
    issue_date = ocr.get("issue_date")
    parsed_issue = None
    if isinstance(issue_date, str):
        try:
            parsed_issue = date.fromisoformat(issue_date)
        except ValueError:
            parsed_issue = None
    return {
        "document_id": d.id,
        "slot_key": d.slot_key,
        "file_name": Path(d.file_path).name,
        "file_format": d.file_format,
        "doc_type": d.doc_type,
        "expected_doc_type": d.expected_doc_type,
        "confidence": ocr.get("confidence"),
        "image_quality": ocr.get("image_quality"),
        "has_signature": ocr.get("has_signature"),
        "issue_date": parsed_issue,
        "declared_issue_date": d.declared_issue_date,
        "fields": ocr.get("fields") or {},
        "bboxes": ocr.get("bboxes") or {},
        "is_encrypted": bool(ocr.get("is_encrypted")),
        "status": d.stage1_status,
    }

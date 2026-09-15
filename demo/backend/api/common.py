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
            )
        )
    return selections


def subsidy_estimate(application_id: int) -> dict[str, Any]:
    """예상 지원금. 신청자 화면·최종 확인·담당자 화면이 같은 계산을 쓴다."""
    return estimate_subsidy(subsidy_selections(application_id)).as_dict()


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
        subsidy_selections=subsidy_selections(app.id or 0),
    )


def checklist_for(app: Application) -> list[DocRequirement]:
    return build_checklist(get_program(app.program_code), doc_context(app))


def list_documents(application_id: int) -> list[Document]:
    with get_session() as s:
        return list(
            s.exec(select(Document).where(Document.application_id == application_id)).all()
        )


def list_consents(application_id: int) -> list[Consent]:
    with get_session() as s:
        return list(
            s.exec(select(Consent).where(Consent.application_id == application_id)).all()
        )


def document_dict(d: Document) -> dict[str, Any]:
    """업로드 서류 한 건의 화면 표현. 점수는 들어가지 않는다."""
    return {
        "document_id": d.id,
        "slot_key": d.slot_key,
        "file_name": Path(d.file_path).name,
        "file_format": d.file_format,
        "expected_doc_type": d.expected_doc_type,
        "detected_doc_type": d.doc_type,
        "declared_issue_date": (
            d.declared_issue_date.isoformat() if d.declared_issue_date else None
        ),
        "status": d.stage1_status,
        "findings": d.findings_json or [],
        "extracted": (d.ocr_json or {}).get("fields", {}),
        "ocr_confidence": (d.ocr_json or {}).get("confidence"),
        "ocr_tier": (d.ocr_json or {}).get("tier"),
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

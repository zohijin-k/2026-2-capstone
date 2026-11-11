"""서류 체크리스트 · 업로드 즉시 판정 (P2).

두배적금은 **보완 요청이 없는 사업**이다. 제출 후에 미비를 알려주면 이미 늦다.
그래서 업로드하는 순간 적합/부적합/확인필요를 돌려주는 것이 이 모듈의 존재 이유다.

판정 로직은 `rules/doc_check.py`(엔진 단건 검사 재사용)에, 판독은 `ocr/`의 3계층
폴백 체인에 맡긴다. 여기서는 파일을 받아 저장하고 둘을 이어붙이는 일만 한다.
"""

import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlmodel import select

from ..models import UNASSIGNED_SLOT, Application, Document, SubsidyItem, get_session
from ..ocr import read_document, split_pdf_pages
from ..rules.identity import identity_of
from ..ocr.base import BBox, OcrResult
from ..rules.doc_check import CheckFinding, THRESHOLD_NOTES, check_document
from ..rules.doc_types import DocType
from ..rules.criteria import for_application, read_criteria
from ..rules.programs import get_program
from ..rules.required_docs import (
    ACCEPTED_FORMATS,
    WORK_CATEGORIES,
    DocRequirement,
    WorkCategory,
    find_slot,
)
from .common import (
    STORAGE,
    checklist_for,
    document_dict,
    list_documents as load_documents,
    load_application,
)

router = APIRouter(prefix="/api/applications", tags=["documents"])

DOCUMENTS = STORAGE / "documents"

#: 병합 PDF 자동 분리를 요청하는 슬롯 키.
AUTO_SLOT = "auto"

#: 파일명에서 경로 구분자와 제어문자를 제거한다. fixture 매칭을 위해 원래 이름은 유지한다.
_UNSAFE = re.compile(r"[\\/:*?\"<>|\x00-\x1f]")


class DocContextRequest(BaseModel):
    """체크리스트를 결정하는 입력. 근로유형이 바뀌면 목록이 실제로 바뀐다."""

    work_category: str | None = None
    admin_fixed_term: bool = False
    workplace_count: int = 1
    handwritten_admin_consent: bool = False
    paper_forms: dict[str, bool] = Field(default_factory=dict)


#: 다른 라우터와 같은 조회·직렬화를 쓴다 (`api/common.py` 참고).
_load = load_application
_checklist = checklist_for
_document_dict = document_dict
_list_documents = load_documents


def _requirement_dict(req: DocRequirement, uploaded: list[Document]) -> dict[str, Any]:
    mine = [d for d in uploaded if d.slot_key == req.slot_key]
    return {
        "slot_key": req.slot_key,
        "doc_type": str(req.doc_type),
        "doc_type_choices": [str(d) for d in req.doc_type_choices],
        "required_fields": req.required_fields,
        "label": req.label,
        "required": req.required,
        "upload": req.upload,
        "fulfilled_by": req.fulfilled_by,
        "requires_signature": req.requires_signature,
        "check_declared_date": req.check_declared_date,
        "date_basis": req.date_basis,
        "date_basis_label": {"issue_date": "발급일", "payment_date": "결제일", "interview_date": "면접일", "exam_date": "응시일", "none": "없음"}.get(req.date_basis, "발급일"),
        "min_issue_date": req.min_issue_date.isoformat() if req.min_issue_date else None,
        "max_issue_date": req.max_issue_date.isoformat() if req.max_issue_date else None,
        "issue_rule_label": req.notes[0] if req.notes else "날짜 기준 없음",
        "issuer": req.issuer,
        "issuer_url": req.issuer_url,
        "notes": req.notes,
        "warnings": req.warnings,
        "alternatives": req.alternatives,
        "accept": req.accept,
        "documents": [_document_dict(d) for d in mine],
    }


def _checklist_response(app: Application) -> dict[str, Any]:
    checklist = _checklist(app)
    program = get_program(app.program_code)
    criteria_version = for_application(app)
    criteria = read_criteria(criteria_version)
    uploaded = _list_documents(app.id or 0)
    items = [_requirement_dict(r, uploaded) for r in checklist]
    upload_items = [i for i in items if i["upload"]]
    done = [i for i in upload_items if i["documents"]]
    unassigned = [d for d in uploaded if d.slot_key == UNASSIGNED_SLOT]
    return {
        "context": app.doc_context_json or {},
        "work_categories": [str(c) for c in WORK_CATEGORIES],
        "accepted_formats": ACCEPTED_FORMATS,
        # 화면이 사업 코드로 분기하지 않도록, 무엇을 물어야 하는지를 여기서 알려준다.
        "program": {
            "code": program.code,
            "name": program.name,
            "selection": program.selection,
            "allows_supplement": criteria["supplement"]["allowed"],
            "supplement_days": criteria["supplement"]["days"],
            "announcement_date": criteria["announcement_date"],
            "application_period": criteria["application_period"],
            "application_period_2": criteria.get("application_period_2"),
            "criteria_version": criteria_version.version,
            "paper_forms": criteria["paper_forms"],
            "nhis_payment_months": criteria["nhis_payment_months"],
            "nhis_acquisition_loss_years": criteria["nhis_acquisition_loss_years"],
            #: 근로확인서류가 있는 사업에서만 근로유형을 묻는다.
            "asks_work_category": program.has_work_requirement,
            #: 지원 항목을 먼저 골라야 추가서류가 생기는 사업인가.
            "has_subsidy_items": program.has_subsidy_items,
        },
        "items": items,
        "upload_total": len(upload_items),
        "upload_done": len(done),
        "unassigned": [_document_dict(d) for d in unassigned],
        # 판정 컷라인은 TF 미확정 가정값이다. 화면에도 같은 라벨로 노출한다.
        "assumption_notes": list(THRESHOLD_NOTES),
    }


@router.get("/{application_id}/required-documents")
def required_documents(application_id: int) -> dict[str, Any]:
    """저장된 근로유형 기준의 맞춤 체크리스트 (R3.2)."""
    return _checklist_response(_load(application_id))


@router.put("/{application_id}/doc-context")
def set_doc_context(application_id: int, body: DocContextRequest) -> dict[str, Any]:
    """근로유형 등을 저장하고, 바뀐 체크리스트를 바로 돌려준다."""
    if body.work_category:
        try:
            WorkCategory(body.work_category)
        except ValueError:
            raise HTTPException(400, f"알 수 없는 근로유형: {body.work_category}") from None

    with get_session() as s:
        app = s.get(Application, application_id)
        if app is None:
            raise HTTPException(404, "신청 건을 찾을 수 없습니다.")
        from ..models import STATUS_DRAFT
        if app.status != STATUS_DRAFT:
            raise HTTPException(409, "제출한 신청서는 수정할 수 없습니다.")
        criteria = read_criteria(for_application(app))
        for form_no, enabled in body.paper_forms.items():
            if form_no not in criteria["paper_forms"] or not isinstance(enabled, bool):
                raise HTTPException(400, "스캔본 제출 서식 설정이 올바르지 않습니다.")
            if enabled and not criteria["paper_forms"][form_no]:
                raise HTTPException(400, "이 서식은 스캔본 제출을 허용하지 않습니다.")
        old = app.doc_context_json or {}
        new_context = body.model_dump()
        # Partial client updates preserve other independent choices.
        if not body.paper_forms:
            new_context["paper_forms"] = old.get("paper_forms", {})
        app.doc_context_json = new_context
        app.updated_at = datetime.now()
        s.add(app)
        s.commit()
        s.refresh(app)
        return _checklist_response(app)


def _safe_name(name: str) -> str:
    cleaned = _UNSAFE.sub("_", Path(name).name).strip()
    return cleaned or "upload"


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise HTTPException(400, "발급일은 YYYY-MM-DD 형식으로 입력해 주세요.") from None


def _ocr_json(ocr: OcrResult) -> dict[str, Any]:
    return {
        "detected_doc_type": str(ocr.detected_doc_type) if ocr.detected_doc_type else None,
        "confidence": ocr.confidence,
        "image_quality": ocr.image_quality,
        "issue_date": ocr.issue_date.isoformat() if ocr.issue_date else None,
        "fields": dict(ocr.fields),
        "bboxes": ocr.bboxes_as_dict(),
        "is_encrypted": ocr.is_encrypted,
        "is_screen_capture": ocr.is_screen_capture,
        "page_count": ocr.page_count,
        "tier": ocr.tier,
        # 판독 엔진·대체 사유는 담당자 화면(officer.py)만 읽는다. 신청자 응답(document_dict)에는 없다.
        "engine": ocr.engine,
        "fallback_reason": ocr.fallback_reason,
        "quality_note": ocr.quality_note,
        "classification_evidence": ocr.classification_evidence,
        "classification_confidence": ocr.classification_confidence,
        "elapsed_ms": ocr.elapsed_ms,
    }


def _save_row(
    app: Application,
    req: DocRequirement | None,
    slot_key: str,
    path: Path,
    ocr: OcrResult,
    declared: date | None,
    findings: list[dict[str, str]],
    status: str,
    *,
    page_index: int | None = None,
    source_file_path: str | None = None,
) -> Document:
    row = Document(
        application_id=app.id or 0,
        slot_key=slot_key,
        doc_type=str(ocr.detected_doc_type) if ocr.detected_doc_type else None,
        expected_doc_type=str(req.doc_type) if req else None,
        file_path=str(path.relative_to(STORAGE.parent)),
        file_format=path.suffix.lstrip(".").lower(),
        declared_issue_date=declared,
        ocr_json=_ocr_json(ocr),
        stage1_status=status,
        findings_json=findings,
        page_index=page_index,
        source_file_path=source_file_path,
    )
    with get_session() as s:
        s.add(row)
        s.commit()
        s.refresh(row)
        return row


def _refresh_nhis_identity(application_id: int, app: Application, checklist: list[DocRequirement]) -> None:
    """건강보험 납부·자격확인서는 짝 서류가 도착할 때마다 함께 다시 대조한다."""
    nhis_types = {str(DocType.NHIS_PAYMENT), str(DocType.NHIS_QUALIFICATION)}
    all_rows = _list_documents(application_id)
    rows = [d for d in all_rows if d.doc_type in nhis_types]
    if not rows:
        return
    identity = identity_of(app.identity_json)
    related = [(d.doc_type or "", (d.ocr_json or {}).get("fields") or {}) for d in rows]
    for row in rows:
        req = find_slot(checklist, row.slot_key)
        if req is None:
            continue
        raw = row.ocr_json or {}
        issue_text = raw.get("issue_date")
        try:
            issue_date = date.fromisoformat(issue_text) if issue_text else None
        except ValueError:
            issue_date = None
        bbox_values = raw.get("bboxes") or {}
        bboxes = {
            key: BBox(**value)
            for key, value in bbox_values.items()
            if isinstance(value, dict) and {"page", "x0", "y0", "x1", "y1"} <= value.keys()
        }
        try:
            detected = DocType(row.doc_type or "")
        except ValueError:
            detected = None
        ocr = OcrResult(
            detected_doc_type=detected,
            confidence=float(raw.get("confidence") or 0.0),
            image_quality=float(raw.get("image_quality") or 0.0),
            issue_date=issue_date,
            fields=dict(raw.get("fields") or {}),
            bboxes=bboxes,
            is_encrypted=bool(raw.get("is_encrypted")),
            is_screen_capture=bool(raw.get("is_screen_capture")),
            page_count=int(raw.get("page_count") or 1),
            tier=str(raw.get("tier") or "none"),
            classification_evidence=str(raw.get("classification_evidence") or ""),
            classification_confidence=float(raw.get("classification_confidence") or 0.0),
        )
        result = check_document(
            req, ocr, row.declared_issue_date, row.file_format, identity,
            related_nhis_docs=related,
            suggested_slot_label=_suggested_other_slot_label(
                req, checklist, all_rows, detected,
            ),
        )
        with get_session() as session:
            saved = session.get(Document, row.id)
            if saved is not None:
                saved.stage1_status = result.status
                saved.findings_json = [finding.as_dict() for finding in result.findings]
                session.add(saved)
                session.commit()


def _suggested_other_slot_label(
    req: DocRequirement,
    checklist: list[DocRequirement],
    uploaded: list[Document],
    detected: DocType | None,
) -> str | None:
    if detected is None:
        return None
    occupied = {row.slot_key for row in uploaded if row.slot_key != req.slot_key}
    for candidate in checklist:
        if (
            candidate.upload
            and candidate.slot_key != req.slot_key
            and candidate.slot_key not in occupied
            and candidate.accepts(detected)
        ):
            return candidate.label
    return None


def _replace_existing(application_id: int, slot_key: str) -> None:
    """같은 슬롯에 다시 올리면 이전 것을 지운다. 재업로드가 기본 동선이다."""
    with get_session() as s:
        for old in s.exec(
            select(Document)
            .where(Document.application_id == application_id)
            .where(Document.slot_key == slot_key)
        ).all():
            s.delete(old)
        s.commit()


@router.post("/{application_id}/documents")
async def upload_document(
    application_id: int,
    file: UploadFile = File(...),
    slot_key: str = Form(AUTO_SLOT),
    declared_issue_date: str | None = Form(None),
) -> dict[str, Any]:
    """파일 1개를 받아 즉시 1단계 판정을 돌려준다 (R2.1).

    `slot_key`를 비우거나 `auto`로 주면 병합 PDF로 보고 페이지별로 쪼개
    슬롯에 자동 배정한다 (R3.5).
    """
    app = _load(application_id)
    checklist = _checklist(app)

    suffix = Path(file.filename or "").suffix.lstrip(".").lower()
    if suffix not in ACCEPTED_FORMATS:
        raise HTTPException(
            400,
            f"pdf, jpg, png 파일만 올릴 수 있습니다. (올리신 형식: {suffix or '알 수 없음'})",
        )

    target_slot = slot_key or AUTO_SLOT
    if target_slot == AUTO_SLOT:
        return await _upload_merged(app, checklist, file)

    req = find_slot(checklist, target_slot)
    if req is None or not req.upload:
        raise HTTPException(400, f"업로드 대상이 아닌 슬롯입니다: {target_slot}")

    declared = _parse_date(declared_issue_date)
    dest_dir = DOCUMENTS / app.application_no / req.slot_key
    dest_dir.mkdir(parents=True, exist_ok=True)
    path = dest_dir / _safe_name(file.filename or "upload")
    path.write_bytes(await file.read())

    ocr = read_document(str(path), req.doc_type)
    paper_admin_consent = bool(((app.doc_context_json or {}).get("paper_forms") or {}).get("서식5"))
    if req.slot_key == "admin_info_consent" and paper_admin_consent and ocr.detected_doc_type is DocType.ADMIN_INFO_CONSENT:
        from ..ocr.admin_consent_scan import inspect_admin_consent_scan

        observations = inspect_admin_consent_scan(str(path))
        ocr.fields.update(observations)
        ocr.has_signature = True if observations["서명잉크확인"] == "있음" else None
    suggested_slot_label = _suggested_other_slot_label(
        req, checklist, _list_documents(application_id), ocr.detected_doc_type,
    )
    result = check_document(
        req, ocr, declared, path.suffix.lstrip(".").lower(), identity_of(app.identity_json),
        suggested_slot_label=suggested_slot_label,
    )
    if req.slot_key == "admin_info_consent" and paper_admin_consent and ocr.detected_doc_type is DocType.ADMIN_INFO_CONSENT:
        consent_value = ocr.fields.get("동의여부")
        if consent_value == "동의하지 않음":
            result.findings.append(CheckFinding(
                "ADMIN_CONSENT_NOT_GIVEN", "행정정보 공동이용에 동의하지 않은 것으로 확인됩니다. 서류를 확인해 주세요.", severity="FAIL"
            ))
            result.status = "FAIL"
        elif consent_value != "동의함":
            result.findings.append(CheckFinding(
                "ADMIN_CONSENT_MARK_UNREADABLE", "동의 표시를 자동 판독하지 못했습니다. 담당자가 원본을 확인합니다.", severity="NEEDS_REVIEW"
            ))
            if result.status == "PASS":
                result.status = "NEEDS_REVIEW"
        if ocr.fields.get("서명잉크확인") != "있음":
            result.findings.append(CheckFinding(
                "ADMIN_CONSENT_SIGNATURE_UNREADABLE", "서명란을 자동 확인하지 못했습니다. 담당자가 원본을 확인합니다.", severity="NEEDS_REVIEW"
            ))
            if result.status == "PASS":
                result.status = "NEEDS_REVIEW"
    if req.slot_key.endswith("_receipt") and ocr.tier == "none" and not ocr.is_encrypted:
        # 판독 계층이 하나도 결과를 내지 못했을 때 낮은 기본 화질 점수로
        # 실비 영수증을 자동 부적합 처리하지 않고 담당자 확인으로 보낸다.
        result.findings[:] = [CheckFinding(
            code="RECEIPT_OCR_UNAVAILABLE",
            message="영수증을 자동 판독하지 못했습니다. 담당자가 원본을 확인합니다.",
            how_to_fix="영수증 원본을 확인할 수 있도록 담당자에게 제출해 주세요.",
            severity="NEEDS_REVIEW",
        )]
        result.status = "NEEDS_REVIEW"
    if req.slot_key.endswith("_receipt") and req.accepts(ocr.detected_doc_type):
        parts = req.slot_key.split("_")
        try:
            item_type, index = parts[0], int(parts[1])
        except (IndexError, ValueError):
            item_type, index = "", 0
        with get_session() as session:
            item = session.exec(select(SubsidyItem)
                                .where(SubsidyItem.application_id == application_id)
                                .where(SubsidyItem.item_type == item_type)
                                .where(SubsidyItem.count_index == index)).first()
        raw_amount = str(ocr.fields.get("결제금액") or "")
        digits = re.sub(r"[^0-9]", "", raw_amount)
        read_amount = int(digits) if digits else None
        if read_amount is None and not any(f.code == "RECEIPT_AMOUNT_UNREADABLE" for f in result.findings):
            result.findings.append(CheckFinding(
                code="RECEIPT_AMOUNT_UNREADABLE",
                message="영수증 결제금액을 자동으로 확인하지 못했습니다. 담당자가 원본을 확인합니다.",
                how_to_fix="영수증에 표시된 결제금액을 확인할 수 있도록 담당자에게 원본을 제출해 주세요.",
                severity="NEEDS_REVIEW",
            ))
            if result.status == "PASS":
                result.status = "NEEDS_REVIEW"
        elif item is not None and item.receipt_amount is not None and item.receipt_amount != read_amount:
            result.findings.append(CheckFinding(
                code="RECEIPT_AMOUNT_MISMATCH",
                message=(f"입력한 금액은 {item.receipt_amount:,}원이고, 영수증 판독 금액은 "
                         f"{read_amount:,}원입니다. 금액을 확인해 주세요."),
                how_to_fix="입력 금액을 영수증에 적힌 결제금액과 맞춰 주세요.",
                severity="NEEDS_REVIEW",
            ))
            if result.status == "PASS":
                result.status = "NEEDS_REVIEW"

    _replace_existing(application_id, req.slot_key)
    row = _save_row(
        app,
        req,
        req.slot_key,
        path,
        ocr,
        declared,
        [f.as_dict() for f in result.findings],
        result.status,
    )
    if req.doc_type in (DocType.NHIS_PAYMENT, DocType.NHIS_QUALIFICATION) or ocr.detected_doc_type in (
        DocType.NHIS_PAYMENT, DocType.NHIS_QUALIFICATION,
    ):
        _refresh_nhis_identity(application_id, app, checklist)
        row = next((d for d in _list_documents(application_id) if d.id == row.id), row)
    return _document_dict(row)


async def _upload_merged(
    app: Application, checklist: list[DocRequirement], file: UploadFile
) -> dict[str, Any]:
    """병합 PDF를 페이지 단위로 쪼개 슬롯에 자동 배정한다 (R3.5).

    공고문은 "1개의 파일로 압축하여 올려야 함"을 요구한다. 기존 방식대로 합쳐
    올린 신청자도 그대로 받되, 페이지별 판별 결과로 슬롯을 채운다. 배정되지 않은
    페이지만 신청자에게 되묻는다.
    """
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(400, "여러 서류를 한 파일로 올리는 기능은 pdf만 지원합니다.")

    base = DOCUMENTS / app.application_no / "_merged"
    base.mkdir(parents=True, exist_ok=True)
    source = base / _safe_name(file.filename or "merged.pdf")
    source.write_bytes(await file.read())

    pages = split_pdf_pages(str(source), base, source.stem)
    if not pages:
        # 암호 PDF 등으로 쪼개지 못한 경우. 판독을 돌려 사유를 그대로 보여준다.
        ocr = read_document(str(source), None)
        placeholder = DocRequirement(
            slot_key=UNASSIGNED_SLOT,
            doc_type=DocType.RESIDENT_ABSTRACT,
            label="병합 업로드 파일",
            check_declared_date=False,
        )
        result = check_document(placeholder, ocr, None, "pdf")
        row = _save_row(
            app,
            None,
            UNASSIGNED_SLOT,
            source,
            ocr,
            None,
            [f.as_dict() for f in result.findings],
            result.status,
        )
        return {
            "mode": "merged",
            "source_file": source.name,
            "page_count": 0,
            "assigned": [],
            "unassigned": [_document_dict(row)],
        }

    taken = {d.slot_key for d in _list_documents(app.id or 0)}
    assigned: list[dict[str, Any]] = []
    unassigned: list[dict[str, Any]] = []
    rel_source = str(source.relative_to(STORAGE.parent))

    for index, page_path, ocr in pages:
        req = None
        if ocr.detected_doc_type is not None:
            for candidate in checklist:
                if (
                    candidate.upload
                    and candidate.accepts(ocr.detected_doc_type)
                    and candidate.slot_key not in taken
                ):
                    req = candidate
                    break

        if req is None:
            row = _save_row(
                app,
                None,
                UNASSIGNED_SLOT,
                page_path,
                ocr,
                None,
                [],
                "NEEDS_REVIEW",
                page_index=index,
                source_file_path=rel_source,
            )
            unassigned.append(_document_dict(row))
            continue

        taken.add(req.slot_key)
        result = check_document(req, ocr, None, "pdf", identity_of(app.identity_json))
        _replace_existing(app.id or 0, req.slot_key)
        row = _save_row(
            app,
            req,
            req.slot_key,
            page_path,
            ocr,
            None,
            [f.as_dict() for f in result.findings],
            result.status,
            page_index=index,
            source_file_path=rel_source,
        )
        assigned.append(_document_dict(row))

    if any(doc["slot_key"] in {"nhis_payment", "nhis_qualification"} for doc in assigned):
        _refresh_nhis_identity(app.id or 0, app, checklist)
        refreshed = {d.id: d for d in _list_documents(app.id or 0)}
        assigned = [
            _document_dict(refreshed[doc["document_id"]])
            if doc["document_id"] in refreshed else doc
            for doc in assigned
        ]

    return {
        "mode": "merged",
        "source_file": source.name,
        "page_count": len(pages),
        "assigned": assigned,
        "unassigned": unassigned,
    }


@router.get("/{application_id}/documents")
def list_documents(application_id: int) -> list[dict[str, Any]]:
    _load(application_id)
    return [_document_dict(d) for d in _list_documents(application_id)]


@router.delete("/{application_id}/documents/{document_id}")
def delete_document(application_id: int, document_id: int) -> dict[str, str]:
    """재업로드를 위한 삭제. 파일도 같이 지운다."""
    app = _load(application_id)
    checklist = _checklist(app)
    nhis_types = {str(DocType.NHIS_PAYMENT), str(DocType.NHIS_QUALIFICATION)}
    refresh_nhis = False
    with get_session() as s:
        row = s.get(Document, document_id)
        if row is None or row.application_id != application_id:
            raise HTTPException(404, "서류를 찾을 수 없습니다.")
        refresh_nhis = row.doc_type in nhis_types or row.expected_doc_type in nhis_types
        target = STORAGE.parent / row.file_path
        target.unlink(missing_ok=True)
        s.delete(row)
        s.commit()
    if refresh_nhis:
        _refresh_nhis_identity(application_id, app, checklist)
    return {"deleted": str(document_id)}

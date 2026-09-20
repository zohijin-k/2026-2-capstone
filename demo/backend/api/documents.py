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
from pydantic import BaseModel
from sqlmodel import select

from ..models import UNASSIGNED_SLOT, Application, Document, get_session
from ..ocr import read_document, split_pdf_pages
from ..ocr.base import OcrResult
from ..rules.doc_check import THRESHOLD_NOTES, check_document
from ..rules.doc_types import DocType
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
        "min_issue_date": req.min_issue_date.isoformat() if req.min_issue_date else None,
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
            "allows_supplement": program.allows_supplement,
            "supplement_days": program.supplement_days,
            "document_cutoff": program.document_cutoff.isoformat(),
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
        app.doc_context_json = body.model_dump()
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
    result = check_document(req, ocr, declared, path.suffix.lstrip(".").lower())

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
        result = check_document(req, ocr, None, "pdf")
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
    with get_session() as s:
        row = s.get(Document, document_id)
        if row is None or row.application_id != application_id:
            raise HTTPException(404, "서류를 찾을 수 없습니다.")
        target = STORAGE.parent / row.file_path
        target.unlink(missing_ok=True)
        s.delete(row)
        s.commit()
    return {"deleted": str(document_id)}

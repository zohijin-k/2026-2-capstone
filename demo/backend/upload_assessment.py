"""Upload assessment shared by the API and the read-only verification tool.

Persistence and application lookups belong to callers. Decision ordering here is
extracted from the explicit-slot upload API without changing document rules.
"""

import re
from collections.abc import Callable, Sequence
from datetime import date
from pathlib import Path
from typing import Any

from .ocr import read_document
from .models import Document
from .ocr.base import BBox, OcrResult
from .rules.doc_check import CheckFinding, CheckResult, check_document
from .rules.doc_types import DocType
from .rules.identity import Identity
from .rules.required_docs import DocRequirement, find_slot


def suggested_other_slot_label(
    req: DocRequirement,
    checklist: Sequence[DocRequirement],
    uploaded: Sequence[Any],
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


def assess_upload(
    path: Path,
    req: DocRequirement,
    *,
    identity: Identity | None = None,
    identity_from_ocr: Callable[[OcrResult], Identity | None] | None = None,
    declared: date | None = None,
    checklist: Sequence[DocRequirement] = (),
    uploaded: Sequence[Any] = (),
    uploaded_loader: Callable[[], Sequence[Any]] | None = None,
    paper_admin_consent: bool = False,
    receipt_amount: int | None = None,
    receipt_amount_loader: Callable[[], int | None] | None = None,
    reader: Callable[[str, DocType | None], OcrResult] = read_document,
) -> tuple[OcrResult, CheckResult]:
    """Read the original path and run the same explicit-slot upload assessment."""
    ocr = reader(str(path), req.doc_type)
    if identity_from_ocr is not None:
        identity = identity_from_ocr(ocr)
    if req.slot_key == "admin_info_consent" and paper_admin_consent and ocr.detected_doc_type is DocType.ADMIN_INFO_CONSENT:
        from .ocr.admin_consent_scan import inspect_admin_consent_scan

        observations = inspect_admin_consent_scan(str(path))
        ocr.fields.update(observations)
        ocr.has_signature = True if observations["서명잉크확인"] == "있음" else None
    suggested_slot_label = suggested_other_slot_label(
        req, checklist, uploaded_loader() if uploaded_loader else uploaded, ocr.detected_doc_type,
    )
    result = check_document(
        req, ocr, declared, path.suffix.lstrip(".").lower(), identity,
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
        if receipt_amount_loader is not None:
            receipt_amount = receipt_amount_loader()
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
        elif receipt_amount is not None and receipt_amount != read_amount:
            result.findings.append(CheckFinding(
                code="RECEIPT_AMOUNT_MISMATCH",
                message=(f"입력한 금액은 {receipt_amount:,}원이고, 영수증 판독 금액은 "
                         f"{read_amount:,}원입니다. 금액을 확인해 주세요."),
                how_to_fix="입력 금액을 영수증에 적힌 결제금액과 맞춰 주세요.",
                severity="NEEDS_REVIEW",
            ))
            if result.status == "PASS":
                result.status = "NEEDS_REVIEW"

    return ocr, result



def assess_nhis_identity(
    identity: Identity | None,
    checklist: Sequence[DocRequirement],
    all_rows: Sequence[Document],
) -> list[tuple[Document, CheckResult]]:
    """Rehydrate and reassess paired NHIS uploads without persisting results."""
    nhis_types = {str(DocType.NHIS_PAYMENT), str(DocType.NHIS_QUALIFICATION)}
    rows = [d for d in all_rows if d.doc_type in nhis_types]
    assessments: list[tuple[Document, CheckResult]] = []
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
            suggested_slot_label=suggested_other_slot_label(
                req, checklist, all_rows, detected,
            ),
        )
        assessments.append((row, result))
    return assessments

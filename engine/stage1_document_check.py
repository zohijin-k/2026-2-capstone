"""
1단계: 서류 적합/부적합 판단

사용자 플로우(Notion) 기준:
"업로드시 적합부적합 판단 (등본인데 초본을 올린다) / (사진의 화질 알아볼수있나)"
여기서 끝내는 게 목표. 자격(소득/횟수)은 건드리지 않는다 -> 2단계 몫.
"""

from __future__ import annotations

from . import config
from .models import (
    Applicant, Document, Finding, ReasonCode, Status, StageResult,
)
from .reason_messages import render


def _find_confusion_group(doc_type: str) -> set[str] | None:
    for group in config.DOCUMENT_TYPE_CONFUSION_GROUPS:
        if doc_type in group:
            return group
    return None


def check_single_document(doc: Document, spec) -> list[Finding]:
    findings: list[Finding] = []

    if doc.is_encrypted_or_corrupted:
        findings.append(Finding(ReasonCode.UNREADABLE_FILE,
                                 render(ReasonCode.UNREADABLE_FILE, doc_type=spec.doc_type),
                                 doc_type=spec.doc_type))
        return findings  # 파일을 못 열면 이후 검사는 의미 없음

    if doc.image_quality_score < config.IMAGE_QUALITY_THRESHOLD:
        findings.append(Finding(ReasonCode.LOW_IMAGE_QUALITY,
                                 render(ReasonCode.LOW_IMAGE_QUALITY, doc_type=spec.doc_type),
                                 doc_type=spec.doc_type))

    if spec.requires_signature and doc.has_signature is False:
        findings.append(Finding(ReasonCode.MISSING_SIGNATURE,
                                 render(ReasonCode.MISSING_SIGNATURE, doc_type=spec.doc_type),
                                 doc_type=spec.doc_type))

    if spec.min_issue_date is not None and doc.issue_date is not None:
        if doc.issue_date < spec.min_issue_date:
            findings.append(Finding(
                ReasonCode.DOCUMENT_ISSUED_TOO_EARLY,
                render(ReasonCode.DOCUMENT_ISSUED_TOO_EARLY, doc_type=spec.doc_type,
                       issue_date=doc.issue_date.isoformat(), cutoff=spec.min_issue_date.isoformat()),
                doc_type=spec.doc_type))

    if spec.check_declared_date and doc.declared_issue_date is not None and doc.issue_date is not None:
        if doc.declared_issue_date != doc.issue_date:
            findings.append(Finding(
                ReasonCode.DECLARED_DATE_MISMATCH,
                render(ReasonCode.DECLARED_DATE_MISMATCH, doc_type=spec.doc_type,
                       declared=doc.declared_issue_date.isoformat(), actual=doc.issue_date.isoformat()),
                doc_type=spec.doc_type))

    if doc.ocr_confidence < config.OCR_CONFIDENCE_THRESHOLD:
        findings.append(Finding(ReasonCode.LOW_OCR_CONFIDENCE,
                                 render(ReasonCode.LOW_OCR_CONFIDENCE, doc_type=spec.doc_type),
                                 doc_type=spec.doc_type))

    return findings


def run_stage1(applicant: Applicant, documents: list[Document]) -> StageResult:
    specs = config.REQUIRED_DOCUMENTS.get(applicant.program, [])
    submitted_by_type = {d.doc_type: d for d in documents}

    findings: list[Finding] = []
    hard_fail = False       # 확정 부적합 (서류 누락, 오분류 등)
    needs_review = False    # 애매함 (OCR 신뢰도 낮음)

    for spec in specs:
        doc = submitted_by_type.get(spec.doc_type)

        if doc is None:
            # 정확히 일치하는 서류가 없을 때, 혼동군 내 다른 서류가 잘못 올라왔는지 확인
            confusion_group = _find_confusion_group(spec.doc_type)
            wrong_doc = None
            if confusion_group:
                for other_type in confusion_group - {spec.doc_type}:
                    if other_type in submitted_by_type:
                        wrong_doc = other_type
                        break
            if wrong_doc:
                findings.append(Finding(ReasonCode.WRONG_DOCUMENT_TYPE,
                                         render(ReasonCode.WRONG_DOCUMENT_TYPE, doc_type=spec.doc_type),
                                         doc_type=spec.doc_type))
            else:
                findings.append(Finding(ReasonCode.MISSING_REQUIRED_DOC,
                                         render(ReasonCode.MISSING_REQUIRED_DOC, doc_type=spec.doc_type),
                                         doc_type=spec.doc_type))
            hard_fail = True
            continue

        doc_findings = check_single_document(doc, spec)
        for f in doc_findings:
            findings.append(f)
            if f.code == ReasonCode.LOW_OCR_CONFIDENCE:
                needs_review = True
            else:
                hard_fail = True

    if hard_fail:
        status = Status.FAIL
    elif needs_review:
        status = Status.NEEDS_REVIEW
    else:
        status = Status.PASS
        findings.append(Finding(ReasonCode.ALL_CLEAR, render(ReasonCode.ALL_CLEAR)))

    return StageResult(stage="stage1_document", status=status, findings=findings)

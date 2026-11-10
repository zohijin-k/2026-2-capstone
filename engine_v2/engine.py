"""엔진 진입점.

    from engine import run
    result = run(application_input)          # ApplicationResult (담당자용 전체)
    result.to_applicant_view()                # 신청자용 (배점·신뢰도·기준값 없음)

흐름: 서류마다 전처리 → OCR → 추출기 → 규칙팩 실행 → 서류 판정 → 신청 판정
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable

import yaml

from .extractors import nhis_acquisition_loss, nhis_payment, resident_abstract
from .extractors.resident_abstract import kst_today
from .pipeline.ocr import OcrResult, OcrWord, run_ocr
from .pipeline.preprocess import PageImage, PageSource, preprocess
from .rules.registry import RULES, RuleContext
from .schemas.models import (ApplicationInput, ApplicationResult, CheckResult, CheckStatus,
                            DocType, DocumentInput, DocumentResult, Evidence, ExtractedField,
                            InternalAssessment, Verdict)

RULEPACK_DIR = Path(__file__).parent / "rulepacks"
LOW_CONFIDENCE = 0.7   # README 6단계. 이보다 낮은 필드로 내린 fail은 오독일 수 있어 담당자에게
REVIEW_MSG = "담당자가 확인한 뒤 결과를 알려드릴게요."

# 서류 종류 → 추출기. 채운·지빈의 추출기도 여기에 한 줄씩 등록한다.
# 추출기 계약: fn(pages, today) -> 객체(detected_type, type_confidence, fields, validations, warnings)
EXTRACTORS: dict[DocType, Callable] = {
    DocType.RESIDENT_ABSTRACT: resident_abstract.extract,
    DocType.RESIDENT_REGISTER: resident_abstract.extract,  # 등본을 올려도 같은 부품이 판별
    DocType.NHIS_PAYMENT: nhis_payment.extract,
    DocType.NHIS_ACQUISITION_LOSS: nhis_acquisition_loss.extract,
}

# 규칙 params 중 '필드 이름'을 담는 키 → 신뢰도 판단에 쓸 관련 필드
_FIELD_KEYS = ("field", "before", "after", "other")
_IMPLICIT_FIELDS = {"current_sido_is": ["current_address"], "residence_months_at_least": ["address_history"]}


def load_rulepack(program_id: str) -> dict:
    return yaml.safe_load((RULEPACK_DIR / f"{program_id}.yaml").read_text(encoding="utf-8"))


class _SafeDict(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def _fmt(template: str, vars: dict) -> str:
    clean = {k: ("-" if v is None else v.isoformat() if isinstance(v, date) else v) for k, v in vars.items()}
    return template.format_map(_SafeDict(clean))


@dataclass
class _Extraction:
    detected_type: DocType
    type_confidence: float
    fields: dict[str, ExtractedField]
    validations: list
    warnings: list[str]


def evaluate_document(doc: DocumentInput, pages: list[tuple[PageImage, OcrResult]],
                      app: ApplicationInput, rulepack: dict, today: date | None = None) -> DocumentResult:
    """OCR까지 끝난 페이지로 한 서류를 판정한다 (입출력 없음 → 테스트하기 쉬움)."""
    today = today or kst_today()
    extractor = EXTRACTORS.get(doc.declared_type)
    if extractor is None:
        return DocumentResult(doc_id=doc.doc_id, declared_type=doc.declared_type, detected_type=DocType.UNKNOWN,
                              type_confidence=0.0, verdict=Verdict.NEEDS_REVIEW,
                              review_reasons=["이 서류 종류의 판독 부품이 아직 없음 (수동 심사)"])

    ex: _Extraction = extractor(pages, today=today)
    ctx = RuleContext(
        reference_date=app.announcement_date, applicant=app.applicant,
        declared_values=doc.declared_values, detected_type=ex.detected_type, fields=ex.fields,
        validations={v.name: (v.passed, v.detail) for v in ex.validations},
        application_date=app.application_date,
        criteria=app.criteria,
    )

    rules = rulepack.get("documents", {}).get(doc.declared_type.value, {}).get("rules", [])
    checks: list[CheckResult] = []
    review: list[str] = list(ex.warnings)
    confident_fail = type_fail = False

    for r in rules:
        fn = RULES.get(r["type"])
        if fn is None:
            status, vars = CheckStatus.UNKNOWN, {}
            review.append(f"{r['id']}: 미구현 규칙 유형 '{r['type']}'")
        else:
            status, vars = fn(ctx, r.get("params", {}))

        related = [r["params"][k] for k in _FIELD_KEYS if k in r.get("params", {})]
        related += _IMPLICIT_FIELDS.get(r["type"], [])
        confs = [ex.fields[f].confidence for f in related if f in ex.fields]
        min_conf = min(confs) if confs else 1.0

        applicant_msg = ""
        if status == CheckStatus.FAIL:
            if r["type"] == "doc_type_is":
                type_fail = True
                applicant_msg = r["applicant"]
            elif min_conf >= LOW_CONFIDENCE:
                confident_fail = True
                applicant_msg = r["applicant"]
            else:  # 판독이 불확실한 상태의 fail → 신청자에게 단정하지 않는다
                applicant_msg = REVIEW_MSG
                review.append(f"{r['id']}: 불일치이나 판독 신뢰도 낮음({min_conf:.2f})")
        elif status == CheckStatus.UNKNOWN:
            applicant_msg = REVIEW_MSG
            review.append(f"{r['id']}: 판단 불가 (필드 없음)")

        if status == CheckStatus.FAIL and r["type"] == "settings_issue_date":
            policy = (app.criteria.get("document_issue_rules") or {}).get(
                ex.detected_type.value,
                app.criteria.get("document_issue_fallback", {"mode": "none"}),
            )
            mode = policy.get("mode", "none")
            if mode == "after_notice":
                cutoff = app.announcement_date
                applicant_msg = f"{cutoff.isoformat().replace('-', '.')} 이후 발급 서류만 인정됩니다. 새로 발급받아 올려 주세요."
            elif mode == "after_date":
                try:
                    cutoff = date.fromisoformat(str(policy.get("date", "")))
                    applicant_msg = f"{cutoff.isoformat().replace('-', '.')} 이후 발급 서류만 인정됩니다. 새로 발급받아 올려 주세요."
                except ValueError:
                    applicant_msg = REVIEW_MSG
            elif mode == "within_days":
                applicant_msg = f"신청일 기준 {policy.get('days')}일 이내 발급 서류만 인정됩니다. 새로 발급받아 올려 주세요."

        evidence = [Evidence(field=f, value=ex.fields[f].value if f != "address_history" else f"{len(ex.fields[f].value)}건",
                             bbox=ex.fields[f].bbox) for f in related if f in ex.fields]
        checks.append(CheckResult(
            rule_id=r["id"], rule_type=r["type"], status=status, applicant_message=applicant_msg,
            reviewer_message=_fmt(r.get("reviewer", ""), {**r.get("params", {}), **vars}), evidence=evidence))  # 계산값이 기준값보다 우선

    if type_fail or confident_fail:
        verdict = Verdict.UNSUITABLE
    elif review:
        verdict = Verdict.NEEDS_REVIEW
    else:
        verdict = Verdict.SUITABLE

    return DocumentResult(doc_id=doc.doc_id, declared_type=doc.declared_type, detected_type=ex.detected_type,
                          type_confidence=ex.type_confidence, fields=ex.fields, checks=checks,
                          verdict=verdict, review_reasons=review)


def _load_pages(doc: DocumentInput, ocr_engine: str) -> list[tuple[PageImage, OcrResult]] | str:
    try:
        pages = []
        pdf = None
        try:
            for p in preprocess(doc.file_path):
                if p.source == PageSource.TEXT_LAYER:
                    if pdf is None:
                        import pymupdf

                        pdf = pymupdf.open(doc.file_path)
                    page = pdf[p.page]
                    scale = 300 / 72
                    p.pixel_size = (round(p.page_size_pt[0] * scale), round(p.page_size_pt[1] * scale))
                    words = []
                    for item in page.get_text("words", sort=True):
                        x0, y0, x1, y1, text = item[:5]
                        if text.strip():
                            words.append(OcrWord(text, 1.0,
                                (x0 * scale, y0 * scale, x1 * scale, y1 * scale)))
                    pages.append((p, OcrResult("text_layer", words)))
                    continue
                r = run_ocr(ocr_engine, p.png, p.pixel_size)
                if r.error:
                    return f"OCR 실패: {r.error}"
                pages.append((p, r))
            return pages
        finally:
            if pdf is not None:
                pdf.close()
    except ValueError as e:
        return str(e)


def run(app: ApplicationInput, ocr_engine: str = "applevision", today: date | None = None) -> ApplicationResult:
    rulepack = load_rulepack(app.program_id.value)
    docs: list[DocumentResult] = []
    for d in app.documents:
        pages = _load_pages(d, ocr_engine)
        if isinstance(pages, str):
            docs.append(DocumentResult(doc_id=d.doc_id, declared_type=d.declared_type, detected_type=DocType.UNKNOWN,
                                       type_confidence=0.0, verdict=Verdict.UNSUITABLE,
                                       checks=[CheckResult(rule_id="file.readable", rule_type="file",
                                                           status=CheckStatus.FAIL,
                                                           applicant_message="파일을 열 수 없어요. PDF나 사진 파일로 다시 올려주세요.",
                                                           reviewer_message=pages)],
                                       review_reasons=[pages]))
            continue
        docs.append(evaluate_document(d, pages, app, rulepack, today))
    return combine(app, docs, rulepack)


def combine(app: ApplicationInput, docs: list[DocumentResult], rulepack: dict) -> ApplicationResult:
    submitted = {d.declared_type.value for d in app.documents}
    missing = [DocType(t) for t in rulepack.get("required_documents", []) if t not in submitted]
    if missing or any(d.verdict == Verdict.UNSUITABLE for d in docs):
        status = Verdict.UNSUITABLE
    elif any(d.verdict == Verdict.NEEDS_REVIEW for d in docs):
        status = Verdict.NEEDS_REVIEW
    else:
        status = Verdict.SUITABLE
    # 배점은 rulepack['scoring']이 확정되면 여기서 계산해 internal에만 넣는다 (대외비)
    return ApplicationResult(application_id=app.application_id, program_id=app.program_id,
                             documents=docs, missing_doc_types=missing, status=status,
                             internal=InternalAssessment())

"""Tier1.5 — 로컬 OCR 판독 (engine_v2).

Tier2(pdftext)는 텍스트 레이어가 있는 PDF만 읽는다. 그런데 실측(2026-11-10)해 보니
신청자가 정부24에서 받아 올리는 초본은 **브라우저 "PDF로 저장" 본이라 글자가 전부
이미지**다. Tier2는 이걸 못 읽고 신뢰도 0 → 전부 담당자 큐로 갔다.

이 계층은 그 공백을 메운다.
  - 서류 이미지를 **외부로 보내지 않고** 이 서버 안에서 OCR한다 (개인정보).
  - 초본/등본은 engine_v2 추출기로 구조를 읽는다: 성명·생년월일·발급일·주소이력,
    그리고 쪽 간 일치·순번 연속 같은 **서류 내부 검증**으로 신뢰도를 매긴다.
  - 건강보험료 납부·자격득실확인서는 텍스트 PDF와 이미지 PDF 모두 engine_v2 추출기를 쓴다.
  - 취업지원패키지 추가서류(결제영수증·응시확인서·성적표·면접확인서)도 텍스트 PDF와 이미지 모두
    engine_v2 추출기(receipt·exam_docs·interview_confirmation)를 쓴다.
  - 그 밖의 서류는 OCR 텍스트에 Tier2의 정규식 추출을 그대로 적용한다.

처리하지 않는 파일(→ None, 다음 계층으로):
  - 지원 전용 추출기 밖의 텍스트 PDF: Tier2가 판독한다. 키워드 미판별 주민등록표는 좌표 제목을 확인한다.
  - 암호 PDF·없는 파일: Tier2가 공고문 문구로 '미비'를 낸다
  - OCR 엔진이 설치돼 있지 않은 서버: 조용히 건너뛴다 (데모가 멈추지 않는 원칙)

OCR 엔진 선택: 환경변수 ENGINE_V2_OCR = own | applevision | easyocr | paddle | off
  명시한 값이 우선이며, 기본값은 macOS를 포함해 own.
  기본 선택에서 own 모델 파일이 없을 때에만 easyocr로 대체한다.
  명시한 own의 모델 누락이나 추론 오류는 다른 OCR 엔진으로 대체하지 않는다.
  대체 사유는 engine_decision() 반환값과 경고 로그에만 남긴다.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from datetime import date
from pathlib import Path

from ..rules.doc_types import DocType
from .base import BBox, OcrResult
from engine_v2.pipeline.privacy import mask_rrn

NAME = "localocr"
ENGINE_ENV = "ENGINE_V2_OCR"

#: Tier2 신뢰도 공식은 '정확한 텍스트'를 전제로 한다. OCR 텍스트에는 그 근거가 없으므로,
#: 서류 내부 검증이 없는 서류는 엔진 임계값(0.85) 아래로 묶어 담당자 확인으로 보낸다.
GENERIC_CONFIDENCE_CAP = 0.8

_REPO_ROOT = Path(__file__).resolve().parents[3]
_logger = logging.getLogger(__name__)


def engine_decision() -> tuple[str, str]:
    """선택한 엔진과 대체 사유(대체 없으면 빈 문자열). 모델 로드·검증·로그 없음."""
    configured = os.environ.get(ENGINE_ENV)
    if configured:
        return configured, ""

    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    from engine_v2.pipeline.ocr import own
    from engine_v2.tools.fetch_own_models import ASSETS

    # 실제 own 로더의 디렉터리와 고정 자산 목록을 따른다. 해시/추론 오류는 대체하지 않는다.
    if all((own.MODEL_DIR / name).is_file() for name in ASSETS):
        return "own", ""
    return "easyocr", "own 모델 파일 없음: easyocr로 대체"


def _engine_name() -> str:
    return engine_decision()[0]


def _import_v2():
    """engine_v2는 지연 import 한다 — OCR을 안 쓰는 경로에서 의존성을 요구하지 않도록."""
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    from engine_v2.extractors import resident_abstract
    from engine_v2.extractors import nhis_acquisition_loss, nhis_payment
    from engine_v2.extractors import insurance_4
    from engine_v2.engine import _load_pages
    from engine_v2.pipeline.ocr import run_ocr
    from engine_v2.pipeline.preprocess import PageSource, preprocess
    from engine_v2.schemas.models import DocType as V2DocType, DocumentInput

    return resident_abstract, nhis_payment, nhis_acquisition_loss, run_ocr, PageSource, preprocess, V2DocType, DocumentInput, _load_pages, insurance_4


def _quality(pages) -> float:
    """해상도로 화질을 근사한다 (엔진 IMAGE_QUALITY_THRESHOLD 0.6과 비교)."""
    dpis = [p.dpi for p in pages if p.dpi]
    if not dpis:
        return 0.75  # 사진 업로드: 물리 크기를 몰라 중간값
    low = min(dpis)
    return 0.9 if low >= 200 else 0.7 if low >= 150 else 0.5


def _demo_bbox(v2_bbox) -> BBox | None:
    if v2_bbox is None:
        return None
    return BBox(v2_bbox.page, v2_bbox.x0, v2_bbox.y0, v2_bbox.x1, v2_bbox.y1)


def _entry_bbox(entry, pages) -> BBox | None:
    """주소이력 한 건의 위치 (전입일 하이라이트용)."""
    if not entry.words:
        return None
    page = next(p for p, _ in pages if p.page == entry.page)
    ws = [w for w in entry.words if w.page == entry.page]
    x0, y0 = page.px_to_pt(min(w.px[0] for w in ws), min(w.px[1] for w in ws))
    x1, y1 = page.px_to_pt(max(w.px[2] for w in ws), max(w.px[3] for w in ws))
    return BBox(entry.page, round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1))


def _from_resident(ex, pages, ra, v2types) -> OcrResult:
    """engine_v2 초본 추출 결과 → 데모 OcrResult (필드 이름은 데모 규칙이 쓰는 그대로)."""
    detected = (DocType.RESIDENT_ABSTRACT if ex.detected_type == v2types.RESIDENT_ABSTRACT
                else DocType.RESIDENT_CERTIFICATE)
    f = ex.fields
    fields: dict[str, str] = {}
    bboxes: dict[str, BBox] = {}

    fields["쪽표기자료"] = json.dumps({
        "markers": ex.page_markers, "confidence": ex.page_marker_confidence,
    })
    from engine_v2.extractors.address_dates import assess
    if ex.detected_type == v2types.RESIDENT_ABSTRACT:
        fields["주소날짜검증자료"] = json.dumps(assess(pages, type_confidence=ex.type_confidence), ensure_ascii=False)

    for v2key, label in (
        ("issue_date", "발급일"), ("name", "성명"), ("birth_date", "생년월일"),
        ("applicant_name", "초본신청인성명"),
        ("applicant_birth_date", "초본신청인생년월일"),
        ("address_history_count", "주소이력건수"),
    ):
        if v2key in f:
            v = f[v2key].value
            fields[label] = v.isoformat() if isinstance(v, date) else str(v)
            if (b := _demo_bbox(f[v2key].bbox)) is not None:
                bboxes[label] = b

    # 데모 배점의 '도 거주기간'은 "전북 최종 전입일 → 공고일 역산"이다.
    # engine_v2는 주소이력 전체에서 전북 연속 거주가 시작된 건을 찾는다
    # (전라북도 → 전북특별자치도 명칭 변경, 세대주 변경 등으로 끊기지 않음).
    start = ra.trailing_residence_start(ex.history, "전북")
    if start:
        fields["전입일"] = start.isoformat()
        entry = next((e for e in ex.history if e.effective == start), None)
        if entry and (b := _entry_bbox(entry, pages)):
            bboxes["전입일"] = b

    if ex.history:
        fields["현주소시도"] = ra.resolved_sido(ex.history, len(ex.history) - 1) or "판별불가"
        fields["주소이력건수"] = str(len(ex.history))
        if len(ex.history) == 1:
            fields["과거주소미포함의심"] = "true"
        # 이력이 2건 이상이면 '주소변동내역 포함'으로 본다. 1건 이하는 단정하지 않는다
        # (미포함으로 단정하면 doc_check가 부적합을 낸다 — 오독일 때 신청자가 억울해진다).
        if len(ex.history) >= 2:
            fields["주소변동내역"] = "포함"

    passed = sum(v.passed for v in ex.validations)
    fields["판독검증"] = f"{passed}/{len(ex.validations)} 통과"
    failed = [v.name for v in ex.validations if not v.passed]
    if failed:
        fields["판독검증실패"] = ", ".join(failed)

    # 신뢰도 = 핵심 필드 신뢰도의 최솟값. 필드 신뢰도는 OCR 점수가 아니라 검증 통과율이다.
    key = [f[k].confidence for k in ("issue_date", "name", "birth_date") if k in f]
    confidence = min([ex.type_confidence, *key]) if "issue_date" in f else 0.5
    if any(not validation.passed and validation.name.startswith(("history", "occurred"))
           for validation in ex.validations):
        confidence = min(confidence, .4)
        fields["판독경고"] = "주소 이력의 순번 또는 날짜를 완전히 확인하지 못했습니다."

    return OcrResult(
        detected_doc_type=detected,
        confidence=round(confidence, 2),
        image_quality=_quality([p for p, _ in pages]),
        issue_date=f["issue_date"].value if "issue_date" in f else None,
        fields=fields,
        bboxes=bboxes,
        page_count=len(pages),
        tier=NAME,
        classification_confidence=ex.type_confidence,
        classification_evidence=ex.classification_evidence,
    )


def ensure_nhis_required_fields(result: OcrResult) -> OcrResult:
    """Keep supported NHIS forms complete after final header-value safety."""
    if (result.tier == "fixture" or not (
            result.detected_doc_type == DocType.NHIS_ACQUISITION_LOSS or
            (result.detected_doc_type in {DocType.NHIS_QUALIFICATION, DocType.NHIS_PAYMENT} and
             "양식판독상태" in result.fields))):
        return result
    from engine_v2.pipeline.field_safety import remove_header_only_fields

    for key in remove_header_only_fields(result.fields):
        result.bboxes.pop(key, None)
    missing = []
    required = ("성명", "생년월일", "발급일")
    if result.detected_doc_type == DocType.NHIS_PAYMENT:
        required += ("사업장명칭", "납부자번호", "문서확인번호", "조회기간", "납부총액", "용도구분")
    for label in required:
        value = str(result.fields.get(label) or "").strip()
        valid = label in result.fields if label == "사업장명칭" else bool(value)
        if label in {"생년월일", "발급일"}:
            try:
                date.fromisoformat(value[:10])
            except ValueError:
                valid = False
        if not valid:
            missing.append(label)
    if not missing:
        return result
    failed = [value.strip() for value in result.fields.get("판독검증실패", "").split(",") if value.strip()]
    added = [f"{label}_required" for label in missing if f"{label}_required" not in failed]
    counts = re.fullmatch(r"(\d+)/(\d+) 통과", result.fields.get("판독검증", ""))
    passed, total = (int(counts[1]), int(counts[2])) if counts else (0, 0)
    result.fields["판독검증"] = f"{passed}/{total + len(added)} 통과"
    result.fields["판독검증실패"] = ", ".join([*failed, *added])
    result.confidence = min(result.confidence, 0.4)
    if "양식판독상태" in result.fields:
        result.fields["양식판독상태"] = "불완전"
    if "발급일" in missing:
        result.issue_date = None
    return result


def ensure_business_required_fields(result: OcrResult) -> OcrResult:
    """Retain the proof completeness gate after shared field safety filtering."""
    if result.detected_doc_type != DocType.BIZ_REG_PROOF or result.tier == "fixture":
        return result
    from engine_v2.extractors.business_registration import (
        REQUIRED_FIELDS, BUSINESS_NUMBER_RE, representative_name, LABEL_VALUES,
    )
    from engine_v2.extractors.job_common import brn_is_valid
    from engine_v2.pipeline.field_safety import remove_header_only_fields

    for key in remove_header_only_fields(result.fields):
        result.bboxes.pop(key, None)
    number = result.fields.get("사업자등록번호", "")
    valid_number = bool(BUSINESS_NUMBER_RE.fullmatch(number)) and brn_is_valid(number)
    code = int(number[4:6]) if valid_number else 0
    if not valid_number or not (1 <= code <= 79 or 90 <= code <= 99) or "법인" in result.fields.get("과세유형", ""):
        result.fields.pop("생년월일", None)
        result.bboxes.pop("생년월일", None)
    missing = []
    for key in REQUIRED_FIELDS:
        value = result.fields.get(key, "")
        valid = bool(value.strip()) and re.sub(r"\s+", "", value) not in LABEL_VALUES
        if key in {"생년월일", "개업일", "사업자등록일", "발급일"}:
            try:
                date.fromisoformat(value)
            except ValueError:
                valid = False
        elif key == "성명":
            valid = representative_name(value) is not None
        elif key == "사업자등록번호":
            valid = valid_number
        elif key in {"업태", "종목"}:
            try:
                items = json.loads(value)
                valid = isinstance(items, list) and bool(items) and all(
                    isinstance(item, str) and item.strip() and re.sub(r"\s+", "", item) not in LABEL_VALUES
                    for item in items)
            except (ValueError, TypeError):
                valid = False
        elif key == "공동사업자유무":
            valid = value in {"있음", "없음"}
        if not valid:
            missing.append(key)
    if not missing:
        return result
    failed = [value.strip() for value in result.fields.get("판독검증실패", "").split(",") if value.strip()]
    added = [f"{key}_required" for key in missing if f"{key}_required" not in failed]
    counts = re.fullmatch(r"(\d+)/(\d+) 통과", result.fields.get("판독검증", ""))
    passed, total = (int(counts[1]), int(counts[2])) if counts else (0, 0)
    result.fields["판독검증"] = f"{passed}/{total + len(added)} 통과"
    result.fields["판독검증실패"] = ", ".join([*failed, *added])
    result.fields["양식판독상태"] = "불완전"
    result.confidence = min(result.confidence, .4)
    if "발급일" in missing:
        result.issue_date = None
    return result


def _from_business_proof(ex, pages, classification_evidence="") -> OcrResult:
    fields = {}
    bboxes = {}
    for key, extracted in ex.fields.items():
        value = extracted.value
        if isinstance(value, date):
            fields[key] = value.isoformat()
        elif isinstance(value, list):
            fields[key] = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        elif isinstance(value, bool):
            fields[key] = "있음" if value else "없음"
        else:
            fields[key] = str(value)
        if (box := _demo_bbox(extracted.bbox)) is not None:
            bboxes[key] = box
    fields["판독검증"] = f"{sum(check.passed for check in ex.validations)}/{len(ex.validations)} 통과"
    failed = [check.name for check in ex.validations if not check.passed]
    if failed:
        fields["판독검증실패"] = ", ".join(failed)
    if ex.warnings:
        fields["판독경고"] = " ".join(ex.warnings)
    fields["양식판독상태"] = "완전" if ex.structure_complete else "불완전"
    issue = ex.fields.get("발급일")
    confidence = min((value.confidence for value in ex.fields.values()), default=.4)
    return ensure_business_required_fields(OcrResult(
        detected_doc_type=DocType.BIZ_REG_PROOF if ex.detected_type.value == "biz_reg_proof" else None,
        confidence=min(confidence, ex.type_confidence, 1 if ex.structure_complete else .4),
        image_quality=_quality([page for page, _ in pages]),
        issue_date=issue.value if issue else None, fields=fields, bboxes=bboxes,
        page_count=len(pages), tier=NAME, engine=_pages_engine(pages),
        classification_evidence=classification_evidence,
        classification_confidence=ex.type_confidence,
    ))


def _from_nhis(ex, pages, v2types, classification_evidence: str = "",
               detected_override: DocType | None = None) -> OcrResult:
    """engine_v2 건강보험 판독 결과를 신청자·담당자 화면 계약으로 옮긴다."""
    fields: dict[str, str] = {}
    bboxes: dict[str, BBox] = {}
    for key, value in ex.fields.items():
        rendered = value.value.isoformat() if isinstance(value.value, date) else str(value.value)
        fields[key] = rendered
        if (box := _demo_bbox(value.bbox)) is not None:
            bboxes[key] = box
    validations = ex.validations
    fields["판독검증"] = f"{sum(v.passed for v in validations)}/{len(validations)} 통과"
    failed = [v.name for v in validations if not v.passed]
    if failed:
        fields["판독검증실패"] = ", ".join(failed)
    if ex.warnings:
        fields["판독경고"] = " ".join(ex.warnings)
    confidence = min((field.confidence for field in ex.fields.values()), default=0.5)
    structure_complete = getattr(ex, "structure_complete", None)
    if structure_complete is not None:
        fields["양식판독상태"] = "완전" if structure_complete else "불완전"
        if not structure_complete:
            confidence = min(confidence, 0.4)
    detected_map = {
        v2types.NHIS_PAYMENT: DocType.NHIS_PAYMENT,
        v2types.NHIS_QUALIFICATION: DocType.NHIS_QUALIFICATION,
        v2types.NHIS_ACQUISITION_LOSS: DocType.NHIS_ACQUISITION_LOSS,
    }
    detected = detected_override or detected_map.get(ex.detected_type)
    if detected == DocType.NHIS_PAYMENT:
        from engine_v2.extractors.nhis_payment import has_failed_payment_validation
        from engine_v2.extractors.payment_period import FIELD, collect

        fields[FIELD] = json.dumps(collect(pages, ex), ensure_ascii=False, separators=(",", ":"))

        if has_failed_payment_validation(fields):
            confidence = min(confidence, .4)
    if (detected == DocType.NHIS_ACQUISITION_LOSS and
            any(v.name == "document_confirmation_number_consistent" and not v.passed
                for v in validations)):
        # Keep the confirmation value internal; only the acquisition-loss
        # extractor's boolean cross-page comparison affects review confidence.
        confidence = min(confidence, 0.4)
    if detected == DocType.NHIS_ACQUISITION_LOSS and "변동내역" in fields:
        covered = next((validation.passed for validation in validations
                        if validation.name == "recent_five_years_covered"), None)
        history_text = fields.get("자격이력자료")
        if type(covered) is bool and history_text:
            try:
                history = json.loads(history_text)
                # Preserve the extractor's tri-state; legacy readers only
                # supplied a boolean validation and still need this fallback.
                history.setdefault("recent_five_years_covered", covered)
                fields["자격이력자료"] = json.dumps(history, ensure_ascii=False, separators=(",", ":"))
            except (TypeError, ValueError):
                pass
    issue = ex.fields.get("발급일")
    issue_date = None
    if issue:
        try:
            issue_date = date.fromisoformat(str(issue.value)[:10])
        except ValueError:
            pass
    return ensure_nhis_required_fields(OcrResult(
        detected_doc_type=detected,
        confidence=round(min(confidence, ex.type_confidence), 2),
        image_quality=_quality([page for page, _ in pages]),
        issue_date=issue_date,
        fields=fields,
        bboxes=bboxes,
        page_count=len(pages),
        tier=NAME,
        classification_evidence=classification_evidence,
        classification_confidence=0.95 if detected else 0.0,
    ))


def _from_insurance4(ex, pages, classification_evidence: str = "") -> OcrResult:
    """4대보험 결과를 데모 필드 계약으로 변환한다."""
    fields: dict[str, str] = {}
    bboxes: dict[str, BBox] = {}
    for key in ("성명", "생년월일", "발급일", "문서확인번호", "발급번호",
                "가입내역", "보험별가입여부", "보험별가입자종별", "근로관련가입여부",
                "근로관련최초취득일", "근로관련최근취득일", "사업장명칭목록", "추가첨부쪽"):
        extracted = ex.fields.get(key)
        if extracted is None:
            continue
        value = extracted.value
        fields[key] = value.isoformat() if isinstance(value, date) else str(value)
        if (box := _demo_bbox(extracted.bbox)) is not None:
            bboxes[key] = box
    for row in ex.rows:
        prefix = row.insurance_type
        row_values = {
            f"{prefix} 가입자종별": row.subscriber_category,
            f"{prefix} 사업장관리번호": row.management_number,
            f"{prefix} 사업장명칭": row.workplace_name,
            f"{prefix} 자격취득일": row.acquired.isoformat() if row.acquired else "",
            f"{prefix} 신고접수일": row.received.isoformat() if row.received else "",
            f"{prefix} 상태": row.status,
        }
        row_box = _demo_bbox(row.bbox)
        for key, value in row_values.items():
            fields[key] = value
            if row_box is not None:
                bboxes[key] = row_box
    validations = list(ex.validations)
    structure_complete = getattr(ex, "structure_complete", None)
    if getattr(ex, "form_kind", None) == "portal":
        from engine_v2.pipeline.field_safety import remove_header_only_fields
        from engine_v2.extractors.nhis_common import Validation

        for key in remove_header_only_fields(fields):
            bboxes.pop(key, None)
        missing = [label for label in ("성명", "생년월일", "발급일") if not fields.get(label)]
        validations.extend(Validation(f"{label}_required", False) for label in missing)
        if missing:
            structure_complete = False
    if structure_complete is not None:
        fields["양식판독상태"] = "완전" if structure_complete else "불완전"
    fields["판독검증"] = f"{sum(item.passed for item in validations)}/{len(validations)} 통과"
    failed = [item.name for item in validations if not item.passed]
    if failed:
        fields["판독검증실패"] = ", ".join(failed)
    if ex.warnings:
        fields["판독경고"] = " ".join(ex.warnings)
    issue = ex.fields.get("발급일")
    issue_date = date.fromisoformat(str(issue.value)) if issue else None
    confidence = min((field.confidence for field in ex.fields.values()), default=0.5)
    if structure_complete is False:
        confidence = min(confidence, 0.4)
    detected = DocType.INSURANCE_4 if ex.detected_type.value == "insurance_4" else None
    return OcrResult(
        detected_doc_type=detected,
        confidence=round(min(confidence, ex.type_confidence), 2),
        image_quality=_quality([page for page, _ in pages]),
        issue_date=issue_date,
        fields=fields,
        bboxes=bboxes,
        page_count=len(pages),
        tier=NAME,
        classification_evidence=classification_evidence,
        classification_confidence=0.97 if detected else 0.0,
    )


def _from_supported_form(extractor, pages, v2types, evidence, detected):
    from engine_v2.extractors.attached_pages import extract_form
    ex, scoped = extract_form(extractor.extract, pages)
    result = (_from_insurance4(ex, scoped, evidence) if detected == DocType.INSURANCE_4
              else _from_nhis(ex, scoped, v2types, evidence, detected))
    result.page_count = len(pages)
    result.engine = _pages_engine(scoped)
    return result


#: 취업지원패키지 추가서류 → (engine_v2 추출기 모듈, engine_v2 서류 종류 값)
_JOB_DOCS: dict[DocType, tuple[str, str]] = {
    DocType.PAYMENT_RECEIPT: ("receipt", "receipt"),
    DocType.EXAM_CONFIRMATION: ("exam_docs", "exam_admission"),
    DocType.EXAM_TRANSCRIPT: ("exam_docs", "exam_score"),
    DocType.INTERVIEW_CONFIRMATION: ("interview_confirmation", "interview_confirm"),
}
#: OCR에서 이 필드가 하나라도 없으면 신뢰도 0.5; 글자층의 확정된 부재는 0.9로 둔다.
_JOB_REQUIRED = {
    "receipt": ("결제금액", "결제일"),
    "exam_admission": ("성명", "응시일"),
    "exam_score": ("성명", "응시일"),
    "interview_confirm": ("성명", "회사명", "면접일"),
}
#: 데모 발급일(issue_date)로 넘길 날짜: 서류에 적힌 발급일이 없으면 그 서류의 기준 날짜
_JOB_ISSUE_FIELDS = {
    "receipt": ("발급일", "결제일"),
    "exam_admission": ("발급일", "응시일"),
    "exam_score": ("발급일", "응시일"),
    "interview_confirm": ("확인일", "면접일"),
}


def _job_extractor(detected: DocType):
    """패키지 서류 추출기도 지연 import 한다."""
    import importlib

    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    return importlib.import_module(f"engine_v2.extractors.{_JOB_DOCS[detected][0]}").extract


def _pages_engine(pages) -> str:
    """모든 쪽이 글자층일 때만 pdftext, 그 밖에는 실제 OCR 결과의 엔진."""
    return next((result.engine for page, result in pages
                 if page.source.value != "text_layer"), "pdftext")


def _from_job_doc(ex, pages, classification_evidence: str = "",
                  detected_override: DocType | None = None) -> OcrResult:
    """engine_v2 패키지 서류 판독 결과를 데모 필드 계약으로 옮긴다 (필드 이름은 데모 규칙이 쓰는 그대로)."""
    fields: dict[str, str] = {}
    bboxes: dict[str, BBox] = {}
    for key, value in ex.fields.items():
        fields[key] = value.value.isoformat() if isinstance(value.value, date) else str(value.value)
        if (box := _demo_bbox(value.bbox)) is not None:
            bboxes[key] = box
    validations = ex.validations
    fields["판독검증"] = f"{sum(v.passed for v in validations)}/{len(validations)} 통과"
    failed = [v.name for v in validations if not v.passed]
    if failed:
        fields["판독검증실패"] = ", ".join(failed)
    if ex.warnings:
        fields["판독경고"] = " ".join(ex.warnings)
    v2type = ex.detected_type.value
    required = _JOB_REQUIRED.get(v2type, ())
    text_only = all(page.source.value == "text_layer" for page, _ in pages)
    if required and all(name in ex.fields for name in required):
        confidence = min(ex.fields[name].confidence for name in required)
    else:
        # 글자층의 빈 항목은 확정된 부재이며, OCR의 빈 항목은 미판독일 수 있다.
        confidence = 0.9 if text_only else 0.5
    issue = next((ex.fields[name] for name in _JOB_ISSUE_FIELDS.get(v2type, ()) if name in ex.fields), None)
    detected = detected_override or next((demo for demo, (_, value) in _JOB_DOCS.items() if value == v2type), None)
    return OcrResult(
        detected_doc_type=detected,
        confidence=round(min(confidence, ex.type_confidence), 2),
        image_quality=1.0 if text_only else _quality([page for page, _ in pages]),
        issue_date=issue.value if issue is not None and isinstance(issue.value, date) else None,
        fields=fields,
        bboxes=bboxes,
        page_count=len(pages),
        tier=NAME,
        engine=_pages_engine(pages),
        classification_evidence=classification_evidence,
        classification_confidence=0.95 if detected else 0.0,
    )


def _generic(pages, path: Path) -> OcrResult | None:
    """초본·등본이 아닌 서류: OCR 텍스트에 Tier2 정규식을 적용한다.

    서류 종류를 알아보지 못했으면 None — 이 계층이 확신 없는 결과로 Tier2의 화면 캡처·화질
    판정을 덮어쓰지 않게 한다.
    """
    from . import pdftext

    text = "\n".join(r.text for _, r in pages)
    if pdftext.classify(text) is None:
        return None
    result = pdftext.read_page_text(text, None, 0)
    result.confidence = min(result.confidence, GENERIC_CONFIDENCE_CAP)
    result.image_quality = _quality([p for p, _ in pages])
    result.page_count = len(pages)
    result.tier = NAME
    if path.suffix.lower() != ".pdf":
        _merge_image_heuristics(result, path)
    return result


def _merge_image_heuristics(result: OcrResult, path: Path) -> None:
    """사진 업로드는 Tier2의 화면 캡처·화질 휴리스틱을 그대로 가져온다."""
    from . import pdftext

    img = pdftext._read_image(path)
    if img is not None and not img.is_encrypted:
        result.is_screen_capture = img.is_screen_capture
        result.image_quality = min(result.image_quality, img.image_quality)


def _tier2_can_read(path: Path) -> bool:
    """Tier2와 **같은 기준**으로 경계를 긋는다: 암호이거나 첫 쪽에 글자가 하나라도 있으면 Tier2 몫."""
    import fitz

    try:
        with fitz.open(path) as doc:
            if doc.needs_pass or doc.page_count == 0:
                return True
            return bool("".join(mask_rrn(doc[0].get_text()).split()))
    except Exception:  # noqa: BLE001 - 못 여는 파일은 Tier2가 '열 수 없음'으로 처리
        return True


class LocalOcr:
    name = NAME

    def read(self, file_path: str, expected: DocType | None) -> OcrResult | None:
        del expected  # 종류는 슬롯 기대값이 아니라 본문 OCR 결과로 먼저 고른다.
        engine, reason = engine_decision()
        if reason:
            _logger.warning("%s", reason)
        result = self._read(file_path, engine)
        if result is not None and not result.engine:
            result.engine = engine
        return result

    def _read(self, file_path: str, engine: str) -> OcrResult | None:
        path = Path(file_path)
        if not path.exists() or path.suffix.lower() not in {".pdf", ".jpg", ".jpeg", ".png"}:
            return None

        text_pdf = path.suffix.lower() == ".pdf" and _tier2_can_read(path)

        from . import pdftext

        if text_pdf:
            # 텍스트 레이어는 바로 읽어 분류한 다음, 지원되는 NHIS 유형이면 그 추출기를 고른다.
            classified = pdftext._read_pdf(path)
            if classified is None:
                return None
            detected = classified.detected_doc_type
            if (detected not in (DocType.NHIS_PAYMENT, DocType.NHIS_ACQUISITION_LOSS, DocType.INSURANCE_4, DocType.BIZ_REG_PROOF)
                    and detected not in _JOB_DOCS and detected != DocType.NHIS_QUALIFICATION and detected is not None):
                return None  # 그 밖의 텍스트 PDF는 Tier2가 이미 분류·판독한다.
            if detected == DocType.NHIS_QUALIFICATION:
                from engine_v2.extractors.nhis_qualification import is_notification
                import pymupdf

                with pymupdf.open(path) as document:
                    if not is_notification(" ".join(mask_rrn(page.get_text()) for page in document)):
                        return None  # Other qualification forms retain their PdfText reader.
        elif engine == "off":
            return None

        try:
            ra, payment_extractor, acquisition_extractor, run_ocr, PageSource, preprocess, v2types, V2DocumentInput, load_pages, insurance4_extractor = _import_v2()
        except ImportError:
            return None

        if text_pdf:
            v2type = v2types(_JOB_DOCS[detected][1]) if detected in _JOB_DOCS else {
                DocType.NHIS_PAYMENT: v2types.NHIS_PAYMENT,
                DocType.NHIS_QUALIFICATION: v2types.NHIS_QUALIFICATION,
                DocType.NHIS_ACQUISITION_LOSS: v2types.NHIS_ACQUISITION_LOSS,
                DocType.INSURANCE_4: v2types.INSURANCE_4,
                DocType.BIZ_REG_PROOF: v2types.BIZ_REG_PROOF,
            }.get(detected, v2types.UNKNOWN)
            input_doc = V2DocumentInput(doc_id="demo", declared_type=v2type, file_path=str(path))
            if detected in {DocType.INSURANCE_4, DocType.NHIS_PAYMENT, DocType.NHIS_ACQUISITION_LOSS, DocType.NHIS_QUALIFICATION}:
                pages = load_pages(input_doc, engine, allow_page_errors=True)
            else:
                pages = load_pages(input_doc, engine)
            if isinstance(pages, str):
                return None  # OCR 엔진이 없어도 다음 계층이 판독을 이어받는다.
            if detected is None:
                detected, evidence = pdftext.classify_pages_with_evidence(pages)
                if detected not in (DocType.RESIDENT_ABSTRACT, DocType.RESIDENT_CERTIFICATE):
                    return None
                # Coordinate fallback changes classification only. Fields still
                # use the established resident reader and review rules.
                result = _from_resident(ra.extract(pages), pages, ra, v2types)
                result.detected_doc_type = detected
                result.classification_evidence = evidence
                result.classification_confidence = .95
                result.engine = _pages_engine(pages)
                return result
            if detected == DocType.BIZ_REG_PROOF:
                from engine_v2.extractors import business_registration
                result = _from_business_proof(business_registration.extract(pages), pages, classified.classification_evidence)
            elif detected in _JOB_DOCS:
                result = _from_job_doc(_job_extractor(detected)(pages), pages,
                                       classified.classification_evidence, detected)
            elif detected == DocType.INSURANCE_4:
                result = _from_supported_form(insurance4_extractor, pages, v2types,
                                              classified.classification_evidence, detected)
            else:
                extractor = payment_extractor if detected == DocType.NHIS_PAYMENT else acquisition_extractor
                if detected == DocType.NHIS_QUALIFICATION:
                    from engine_v2.extractors import nhis_qualification
                    extractor = nhis_qualification
                result = _from_supported_form(extractor, pages, v2types,
                                              classified.classification_evidence, detected)
            result.engine = result.engine or _pages_engine(pages)
            return result

        try:
            page_images = preprocess(path)
        except ValueError:
            return None
        if any(p.source == PageSource.TEXT_LAYER for p in page_images):
            return None

        pages = []
        for p in page_images:
            r = run_ocr(engine, p.png, p.pixel_size)
            if r.error:
                return None  # 엔진 미설치 등 → 다음 계층
            pages.append((p, r))

        text = "\n".join(result.text for _, result in pages)
        detected, evidence = pdftext.classify_pages_with_evidence(pages)
        if detected is None:
            # Do not discard successfully read words and independent folios just
            # because damaged title glyphs cannot establish a document type.
            from .file_evidence import independent_page_markers
            markers = independent_page_markers(pages)
            fields = {"독립쪽표기자료": json.dumps(markers)} if markers else {}
            result = OcrResult(fields=fields, page_count=len(pages), tier=NAME,
                               engine=engine, image_quality=_quality(page_images),
                               classification_evidence=evidence)
            if path.suffix.lower() != ".pdf":
                _merge_image_heuristics(result, path)
            return result

        if detected == DocType.BIZ_REG_PROOF:
            from engine_v2.extractors import business_registration
            result = _from_business_proof(business_registration.extract(pages), pages, evidence)
            if path.suffix.lower() != ".pdf":
                _merge_image_heuristics(result, path)
            return result

        if detected in _JOB_DOCS:
            result = _from_job_doc(_job_extractor(detected)(pages), pages, evidence, detected)
            if path.suffix.lower() != ".pdf":
                _merge_image_heuristics(result, path)
            return result

        if detected == DocType.NHIS_QUALIFICATION:
            from engine_v2.extractors import nhis_qualification
            if nhis_qualification.is_notification(text):
                result = _from_supported_form(nhis_qualification, pages, v2types, evidence, detected)
                if path.suffix.lower() != ".pdf":
                    _merge_image_heuristics(result, path)
                return result

        if detected in (DocType.NHIS_PAYMENT, DocType.NHIS_ACQUISITION_LOSS, DocType.INSURANCE_4):
            if detected == DocType.INSURANCE_4:
                result = _from_supported_form(insurance4_extractor, pages, v2types, evidence, detected)
            else:
                extractor = payment_extractor if detected == DocType.NHIS_PAYMENT else acquisition_extractor
                result = _from_supported_form(extractor, pages, v2types, evidence, detected)
            if path.suffix.lower() != ".pdf":
                _merge_image_heuristics(result, path)
            return result

        if detected in (DocType.RESIDENT_ABSTRACT, DocType.RESIDENT_CERTIFICATE):
            ex = ra.extract(pages)
            result = _from_resident(ex, pages, ra, v2types)
            result.detected_doc_type = detected
            result.classification_evidence = evidence
            result.classification_confidence = 0.95
            if path.suffix.lower() != ".pdf":
                _merge_image_heuristics(result, path)
            return result

        result = _generic(pages, path)
        if result is not None:
            result.detected_doc_type = detected
            result.classification_evidence = evidence
            result.classification_confidence = 0.95
        return result

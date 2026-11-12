"""업로드 즉시 1단계 판정 (R2).

엔진의 `run_stage1`은 신청 건 전체(필수서류 목록 대비 누락까지)를 본다. 업로드
직후에는 아직 나머지 서류가 없으므로 그걸 그대로 쓰면 항상 '누락'이 뜬다.
그래서 서류 **한 건**만 보는 `engine.stage1_document_check.check_single_document`를
그대로 재사용하고, 엔진에 없는 항목(오분류·화면캡처·주소이력)만 여기서 얹는다.

엔진 판정 로직을 복제하지 않는 것이 핵심이다. 임계값(신뢰도 0.85, 화질 0.6)이
엔진과 어긋나면 업로드 화면과 최종 심사 결과가 달라진다.
"""

from dataclasses import dataclass, field
from datetime import date
import json

from ..engine_adapter import engine_check_single_document, engine_config, engine_models
from ..ocr.base import OcrResult
from .doc_types import DocType
from .identity import Identity, compare, nhis_subscriber_assessment
from .months import format_month_ranges
from .required_docs import DocRequirement
from .scoring import ESTIMATE_LABEL

#: 판독 신뢰도·화질 컷라인은 **엔진 config의 가정값**이다. 엔진 config.py 첫 줄이
#: "회의 전 데모용으로 우리가 임의로 정한 값"이라고 밝히고 있고, PRD의 Open
#: Question 5(저신뢰 시 자동 반려인가 담당자 큐인가, 임계값은 얼마인가)가 아직
#: 열려 있다. 코드와 화면 양쪽에 같은 라벨을 달아 둔다.
THRESHOLD_NOTES: list[str] = [
    f"{ESTIMATE_LABEL} 자동 판독 신뢰도가 "
    f"{engine_config.OCR_CONFIDENCE_THRESHOLD:.2f} 미만이면 반려하지 않고 '확인필요'로 "
    "담당자에게 넘깁니다. 이 컷라인은 TF 미확정 값입니다.",
    f"{ESTIMATE_LABEL} 화질 점수 "
    f"{engine_config.IMAGE_QUALITY_THRESHOLD:.1f} 미만을 화질 불량으로 봅니다. "
    "이 기준도 TF 미확정 값입니다.",
]

#: 데모가 자체적으로 얹는 사유 코드. 엔진 `ReasonCode`에 없는 항목이다.
#: 진과 합의되면 엔진 쪽으로 옮긴다 (design.md 9절 E-목록의 후속).
CODE_SCREEN_CAPTURE = "SCREEN_CAPTURE_SUSPECTED"
CODE_MISSING_ADDRESS_HISTORY = "MISSING_ADDRESS_HISTORY"
CODE_PAST_ADDRESS_OMISSION_SUSPECTED = "PAST_ADDRESS_OMISSION_SUSPECTED"
CODE_RESIDENT_APPLICANT_UNREADABLE = "RESIDENT_APPLICANT_UNREADABLE"
CODE_UNKNOWN_DOCUMENT_TYPE = "UNKNOWN_DOCUMENT_TYPE"
CODE_MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"
#: 사진·스캔을 OCR로 읽어 필수 항목을 찾지 못함 — '안 적힌 것'과 '못 읽은 것'을 구별할 수 없어 담당자 확인
CODE_REQUIRED_FIELD_UNREADABLE = "REQUIRED_FIELD_UNREADABLE"
CODE_RECEIPT_AMOUNT_UNREADABLE = "RECEIPT_AMOUNT_UNREADABLE"
#: 서류의 성명·생년월일이 본인인증 정보와 다름 (판독 확실 → 부적합)
CODE_IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
#: 위와 같으나 판독이 불확실 → 오독일 수 있어 담당자 확인
CODE_IDENTITY_UNCERTAIN = "IDENTITY_UNCERTAIN"
CODE_MISSING_BILLING_MONTHS = "MISSING_BILLING_MONTHS"
CODE_NHIS_DEPENDENT_INSURED_PERSON = "NHIS_DEPENDENT_INSURED_PERSON"
CODE_NHIS_SUBSCRIBER_IDENTITY_REVIEW = "NHIS_SUBSCRIBER_IDENTITY_REVIEW"
CODE_PAGES_INCOMPLETE = "PAGES_INCOMPLETE"
CODE_PAGES_UNREADABLE = "PAGES_UNREADABLE"
CODE_PAGES_DUPLICATED = "PAGES_DUPLICATED"
CODE_IMAGE_RESOLUTION_TOO_LOW = "IMAGE_RESOLUTION_TOO_LOW"
CODE_MISSING_ADDRESS_DATES = "MISSING_ADDRESS_DATES"
CODE_DAILY_RECORDS_PARTIALLY_SELECTED = "DAILY_RECORDS_PARTIALLY_SELECTED"

PHOTO_RETAKE_GUIDANCE = (
    "흐리거나 옆으로 누운 사진은 읽기 어렵습니다. "
    "서류 전체가 똑바로 보이게 밝은 곳에서 선명하게 다시 촬영해 주세요. "
)
RETAKE_GUIDANCE = PHOTO_RETAKE_GUIDANCE + "이대로 제출해도 담당자가 확인합니다."

#: 사유 코드 → 해결 방법. 공고문 문구와 발급 절차를 그대로 옮긴 것이다.
#: "무엇이 잘못됐는지"만 말하면 신청자는 또 전화한다. 해결 방법이 같이 있어야 한다.
HOW_TO_FIX: dict[str, str] = {
    CODE_DAILY_RECORDS_PARTIALLY_SELECTED: "전체 이력을 선택해 다시 발급받아 올려 주세요",
    CODE_IMAGE_RESOLUTION_TOO_LOW: "선명한 원본(원본 PDF 또는 고해상도 스캔)으로 다시 올려 주세요",
    CODE_MISSING_ADDRESS_DATES: "정부24에서 초본을 발급할 때 주소 변동 사항의 발생일·신고일이 표시되도록 선택해 다시 발급받아 주세요",
    "WRONG_DOCUMENT_TYPE": "요구되는 서류와 다른 종류를 올리셨습니다. 아래 발급처에서 '{label}'을(를) 다시 발급받아 올려 주세요.",
    "DOCUMENT_ISSUED_TOO_EARLY": "{cutoff} 이후 발급분만 인정됩니다. 발급처에서 새로 발급받아 다시 올려 주세요.",
    "DECLARED_DATE_MISMATCH": "입력하신 발급일과 서류에 찍힌 발급일이 다릅니다. 발급일을 다시 확인하시거나, 올바른 파일을 올려 주세요.",
    CODE_MISSING_BILLING_MONTHS: "조회기간에 {months}이 포함되도록 다시 발급해 주세요.",
    "DECLARED_DATE_UNCERTAIN": "발급일을 서류에 찍힌 대로 입력하셨다면 그대로 두셔도 됩니다. 담당자가 원본에서 직접 확인합니다. " + RETAKE_GUIDANCE,
    "UNREADABLE_FILE": "PDF 암호를 해제한 뒤 다시 올려 주세요. 발급처에서 '암호 설정 안 함'으로 재발급받는 것이 가장 확실합니다.",
    "LOW_IMAGE_QUALITY": RETAKE_GUIDANCE,
    "LOW_OCR_CONFIDENCE": RETAKE_GUIDANCE,
    "MISSING_SIGNATURE": "서명란에 서명한 뒤 다시 올려 주세요.",
    CODE_SCREEN_CAPTURE: "모니터 화면을 캡처한 이미지는 인정되지 않습니다. 발급처에서 내려받은 pdf 원본이나 스캔본으로 올려 주세요.",
    CODE_MISSING_ADDRESS_HISTORY: "정부24에서 초본을 발급할 때 '과거의 주소 변동사항(최근 5년)' 포함을 체크해 다시 발급받아 주세요.",
    CODE_MISSING_REQUIRED_FIELD: "{field}이(가) 표기된 서류로 다시 발급받아 올려 주세요. 발급 기관에 {field} 표기를 요청하시면 됩니다.",
    CODE_REQUIRED_FIELD_UNREADABLE: "서류에 {field}이(가) 적혀 있다면 그대로 두셔도 됩니다. 담당자가 원본에서 직접 확인합니다. {field}이(가) 잘 보이게 다시 찍어 올리면 더 빨리 확인됩니다. " + RETAKE_GUIDANCE,
    CODE_IDENTITY_MISMATCH: "본인 명의로 발급받은 서류만 인정됩니다. 가족이나 다른 사람 명의의 서류가 아닌지 확인하고 다시 올려 주세요.",
    CODE_IDENTITY_UNCERTAIN: RETAKE_GUIDANCE,
    CODE_NHIS_DEPENDENT_INSURED_PERSON: "건강보험 가입자 명의 서류로 확인했습니다.",
    CODE_NHIS_SUBSCRIBER_IDENTITY_REVIEW: "가입자 명의 확인이 필요해 담당자가 확인합니다.",
    CODE_UNKNOWN_DOCUMENT_TYPE: RETAKE_GUIDANCE,
    CODE_RESIDENT_APPLICANT_UNREADABLE: RETAKE_GUIDANCE,
    CODE_PAGES_UNREADABLE: "서류 전체가 선명하게 보이게 다시 촬영해 주세요. " + RETAKE_GUIDANCE,
    CODE_PAGES_INCOMPLETE: "빠진 쪽까지 모두 올려 주세요.",
    CODE_PAGES_DUPLICATED: "중복된 쪽을 확인하고 서로 다른 모든 쪽을 올려 주세요.",
    "NHIS_HISTORY_PERIOD_UNREADABLE": "최근 변동내역의 범위는 담당자가 원본에서 확인합니다. " + RETAKE_GUIDANCE,
    "NHIS_HISTORY_PERIOD_MISSING": "조회기간에 최근 {years}년 전체가 포함되도록 다시 발급받아 올려 주세요.",
}

_DOC_TYPE_DISPLAY = {
    DocType.NHIS_PAYMENT: "건강보험료 납부확인서",
    DocType.NHIS_QUALIFICATION: "건강보험 자격확인서",
    DocType.NHIS_ACQUISITION_LOSS: "건강보험 자격득실확인서",
    DocType.RESIDENT_ABSTRACT: "주민등록초본",
    DocType.RESIDENT_CERTIFICATE: "주민등록등본",
    DocType.INTERVIEW_CONFIRMATION: "면접확인서",
    DocType.PAYMENT_RECEIPT: "결제영수증",
    DocType.EXAM_CONFIRMATION: "응시확인서",
    DocType.EXAM_TRANSCRIPT: "성적표",
    DocType.INSURANCE_4: "4대보험가입내역확인서",
    DocType.DAILY_WORK_RECORD: "고용산재보험일용근로내역서",
    DocType.BIZ_REG_PROOF: "사업자등록증명",
    DocType.BIZ_REG_CERT: "사업자등록증",
    DocType.FARM_BIZ_CERT: "농업경영체증명서",
    DocType.FISHERY_BIZ_CERT: "어업경영체증명서",
    DocType.LABOR_CONTRACT: "근로계약서",
    DocType.ID_PHOTO_COPY: "면접용사진사본",
    DocType.ADMIN_INFO_CONSENT: "행정정보공동이용동의서",
}


def _display_doc_type(doc_type: DocType) -> str:
    return _DOC_TYPE_DISPLAY.get(doc_type, str(doc_type))


def _date_korean(value: date) -> str:
    return f"{value.year}년 {value.month}월 {value.day}일"


def _has_final_consonant(value: str) -> bool:
    if not value:
        return False
    code = ord(value[-1]) - 0xAC00
    return 0 <= code <= 11171 and code % 28 != 0

#: NEEDS_REVIEW로만 보내는 코드. 나머지는 확정 부적합(FAIL)이다.
#: 화면캡처는 오탐 시 신청자가 억울해지므로 자동 반려하지 않는다.
REVIEW_ONLY_CODES = {
    "LOW_OCR_CONFIDENCE",
    "LOW_IMAGE_QUALITY",
    "NHIS_HISTORY_PERIOD_UNREADABLE",
    CODE_RESIDENT_APPLICANT_UNREADABLE,
    CODE_PAGES_UNREADABLE,
    # 입력 발급일 불일치이나 판독이 불확실 — 오독일 수 있어 자동 반려하지 않는다.
    "DECLARED_DATE_UNCERTAIN",
    # 본인 정보 불일치이나 판독이 불확실 — 남의 서류로 단정하지 않는다.
    CODE_IDENTITY_UNCERTAIN,
    CODE_SCREEN_CAPTURE,
    CODE_UNKNOWN_DOCUMENT_TYPE,
    CODE_RECEIPT_AMOUNT_UNREADABLE,
    CODE_REQUIRED_FIELD_UNREADABLE,
}


@dataclass
class CheckFinding:
    code: str
    message: str
    how_to_fix: str = ""
    link: str = ""
    #: FAIL | NEEDS_REVIEW
    severity: str = "FAIL"
    #: 담당자 화면에서만 보는 근거. 신청자 API는 이 값을 직렬화하지 않는다.
    detail: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
            "how_to_fix": self.how_to_fix,
            "link": self.link,
            "severity": self.severity,
            "detail": self.detail,
        }


@dataclass
class CheckResult:
    #: PASS | FAIL | NEEDS_REVIEW
    status: str
    findings: list[CheckFinding] = field(default_factory=list)

    @property
    def codes(self) -> list[str]:
        return [f.code for f in self.findings]


def to_engine_spec(req: DocRequirement):
    """체크리스트 한 줄 → 엔진 `RequiredDocumentSpec`."""
    return engine_models.RequiredDocumentSpec(
        doc_type=str(req.doc_type),
        required=req.required,
        requires_signature=req.requires_signature,
        min_issue_date=req.min_issue_date,
        max_issue_date=req.max_issue_date,
        check_declared_date=req.check_declared_date,
    )


def to_engine_document(
    req: DocRequirement,
    ocr: OcrResult,
    declared_issue_date: date | None,
    file_format: str,
    date_basis: str = "issue_date",
):
    """판독 결과 → 엔진 `Document`.

    `doc_type`에는 **요구된 서류 종류**를 넣는다. 엔진의 단건 검사는 doc_type을
    메시지 렌더링에만 쓰고, 오분류 판정은 데모 쪽에서 별도로 하기 때문이다.
    """
    basis_field = {
        "issue_date": "발급일", "payment_date": "결제일",
        "interview_date": "면접일", "exam_date": "응시일",
    }.get(date_basis)
    effective_date = ocr.issue_date
    if basis_field:
        try:
            effective_date = date.fromisoformat(str(ocr.fields.get(basis_field) or "")[:10])
        except ValueError:
            effective_date = None
    elif date_basis == "none":
        effective_date = None
    return engine_models.Document(
        doc_type=str(req.doc_type),
        file_format=file_format,
        ocr_confidence=ocr.confidence,
        image_quality_score=ocr.image_quality,
        has_signature=ocr.has_signature,
        issue_date=effective_date,
        declared_issue_date=declared_issue_date,
        extracted_fields=dict(ocr.fields),
        is_encrypted_or_corrupted=ocr.is_encrypted,
    )


def _finding(code: str, message: str, req: DocRequirement, **fmt: str) -> CheckFinding:
    how_to_fix = HOW_TO_FIX.get(code, "")
    if how_to_fix:
        how_to_fix = how_to_fix.format(
            label=req.label,
            cutoff=req.min_issue_date.isoformat() if req.min_issue_date else "",
            **fmt,
        )
    return CheckFinding(
        code=code,
        message=message,
        how_to_fix=how_to_fix,
        link=req.issuer_url,
        severity="NEEDS_REVIEW" if code in REVIEW_ONLY_CODES else "FAIL",
    )


def _insurance_identity_unreadable(req: DocRequirement, ocr: OcrResult) -> CheckFinding | None:
    name = str(ocr.fields.get("성명") or "").strip()
    try:
        birth = date.fromisoformat(str(ocr.fields.get("생년월일") or "")[:10])
    except ValueError:
        birth = None
    missing = (["성명"] if not name else []) + (["생년월일"] if birth is None else [])
    if not missing:
        return None
    field = "·".join(missing)
    action = "을 모두 읽지 못했습니다" if len(missing) == 2 else "을 읽지 못했습니다"
    return _finding(
        CODE_REQUIRED_FIELD_UNREADABLE,
        f"4대보험 서류의 {field}{action}. 담당자가 원본을 확인합니다.",
        req, field=field,
    )


def _uncertain(finding: CheckFinding) -> CheckFinding:
    """읽기 불확실성은 확정 위반 문구와 제출 차단을 함께 없앤다."""
    finding.message = "서류의 내용을 확실하게 읽지 못했습니다. 담당자가 원본에서 직접 확인합니다."
    finding.how_to_fix = RETAKE_GUIDANCE
    finding.severity = "NEEDS_REVIEW"
    return finding


def _nhis_history_coverage(data, issue: date, years: int, structure_complete: bool):
    """Read new evidence conservatively while retaining legacy positive results."""
    from engine_v2.extractors.nhis_acquisition_loss import history_covers_recent_years

    if not isinstance(data, dict):
        raise ValueError("invalid history")
    covered = data.get("recent_five_years_covered")
    has_basis = "coverage_basis" in data
    basis = data.get("coverage_basis")
    # Markerless legacy true booleans were already accepted without parsing.
    if not has_basis and covered is True:
        return True, False
    if has_basis:
        if basis == "undetermined" or covered is None:
            return None, False
        if type(covered) is not bool or basis not in {"query_period", "full_history", "history_rows"}:
            raise ValueError("invalid coverage evidence")
        if basis == "full_history":
            if (covered and structure_complete and data.get("period") is None
                    and data.get("period_label_present") is False):
                return True, False
            return None, False
    raw_period = data.get("period")
    period = None
    # Old JSON treated every empty period representation as absent.
    if raw_period is not None and (has_basis or raw_period):
        if not isinstance(raw_period, (list, tuple)) or len(raw_period) != 2:
            raise ValueError("invalid period")
        period = (date.fromisoformat(raw_period[0]), date.fromisoformat(raw_period[1]))
        if period[0] > period[1]:
            raise ValueError("reversed period")
    if has_basis and (basis == "query_period") != (period is not None):
        raise ValueError("conflicting coverage evidence")
    if period is not None:
        return history_covers_recent_years(issue, period, (), years), True
    if has_basis and data.get("period_label_present") is not False:
        return None, False
    if not has_basis and covered is False:
        return False, False
    raw_rows = data.get("rows", [])
    if not isinstance(raw_rows, list) or any(not isinstance(row, dict) for row in raw_rows):
        raise ValueError("invalid rows")
    history = [(date.fromisoformat(row["acquired"]) if row.get("acquired") else None,
                date.fromisoformat(row["lost"]) if row.get("lost") else None) for row in raw_rows]
    covered = history_covers_recent_years(issue, None, history, years)
    # A new insufficient row range is unknown; legacy negatives retain their
    # finding code, but the caller downgrades them to review without reissuance.
    return (covered if covered or not has_basis else None), False


def _check_resident_pages(ocr: OcrResult, req: DocRequirement) -> list[CheckFinding]:
    # 쪽 완전성 검사를 수행한 추출기의 구조화된 결과만 소비한다.
    # 기존 fixture/일반 글자층 판독값에는 이 검사의 결과 자체가 없다.
    if "쪽표기자료" not in ocr.fields:
        return []
    unreadable = _finding(
        CODE_PAGES_UNREADABLE,
        "주민등록초본의 쪽표기를 확실하게 읽지 못했습니다. 담당자가 전체 쪽을 확인합니다.", req,
    )
    try:
        data = json.loads(ocr.fields["쪽표기자료"])
        markers = data["markers"]
        confidence = min(float(data["confidence"]), ocr.confidence)
        failed = {name.strip() for name in ocr.fields.get("판독검증실패", "").split(",") if name.strip()}
        # Duplicated pages can invalidate the combined history and cap document
        # confidence. Their independently read page markers still prove a page
        # defect when type and marker evidence are both reliable.
        history_limited = (ocr.tier == "localocr" and not ocr.fallback_reason and ocr.confidence == .4 and
                           any(name.startswith(("history", "occurred")) for name in failed) and
                           all(name == "pages_complete" or name.startswith(("history", "occurred"))
                               for name in failed))
        if history_limited:
            confidence = min(float(data["confidence"]), ocr.classification_confidence)
        if (not markers or len(markers) != ocr.page_count
                or not confidence >= engine_config.OCR_CONFIDENCE_THRESHOLD):
            return [unreadable]
        if any(not isinstance(m, list) or len(m) != 2
               or any(type(v) is not int for v in m) or not 1 <= m[0] <= m[1] for m in markers):
            return [unreadable]
        totals = {m[1] for m in markers}
        if len(totals) != 1:
            return [unreadable]
        total = totals.pop()
        seen = {m[0] for m in markers}
        if len(seen) < total:
            return [_finding(
                CODE_PAGES_INCOMPLETE,
                f"주민등록초본 {total}쪽 중 {len(seen)}쪽만 올라왔습니다. 빠진 쪽까지 모두 올려 주세요.", req,
            )]
        if len(markers) != len(seen):
            return [_finding(CODE_PAGES_DUPLICATED, "주민등록초본에 중복된 쪽이 올라왔습니다.", req)]
    except (ValueError, TypeError, KeyError, AttributeError):
        return [unreadable]
    return []


def _check_billing_months(ocr: OcrResult, req: DocRequirement) -> list[CheckFinding]:
    """Reject only independently proven range or bounded amount omissions."""
    from engine_v2.extractors.payment_period import FIELD

    def review():
        finding = _finding(
            CODE_MISSING_BILLING_MONTHS,
            "납부확인서의 조회기간 또는 심사 대상 고지월을 확실하게 확인하지 못했습니다. 담당자가 원본을 확인합니다.",
            req, months=format_month_ranges(req.premium_months),
        )
        finding.severity = "NEEDS_REVIEW"
        finding.how_to_fix = RETAKE_GUIDANCE
        return [finding]

    raw = ocr.fields.get(FIELD)
    if raw is not None:
        try:
            data = json.loads(raw)
            period = data.get("period")
            if (data.get("version") != 1 or data.get("status") != "READABLE" or
                    not isinstance(period, list) or len(period) != 2 or
                    any(not isinstance(value, str) or len(value) != 7 or
                        date.fromisoformat(value + "-01").strftime("%Y-%m") != value for value in period) or
                    period[0] > period[1]):
                return review()
            missing = [month for month in req.premium_months if not period[0] <= month <= period[1]]
            if not missing and data.get("amounts_certain") is True:
                absent = data.get("absent_amount_months")
                uncertain_absent = data.get("uncertain_absent_amount_months")
                if (not isinstance(absent, list) or not isinstance(uncertain_absent, list) or
                        any(not isinstance(value, str) for value in absent + uncertain_absent)):
                    return review()
                missing = [month for month in req.premium_months if month in absent]
                if not missing and any(month in uncertain_absent for month in req.premium_months):
                    return review()
            if missing:
                rendered = format_month_ranges(missing)
                finding = _finding(
                    CODE_MISSING_BILLING_MONTHS,
                    f"납부확인서에 심사 대상 고지월 {rendered}의 고지금액이 없어 평균 보험료를 계산할 수 없습니다.",
                    req, months=rendered,
                )
                finding.detail = (f"독립 판독 조회기간 {period[0]}~{period[1]}; "
                                  "제목·월 행 모순 없음. 금액 부재는 표 머리글·열·합계 검증 근거에 한함.")
                return [finding]
        except (ValueError, TypeError, KeyError, AttributeError):
            return review()

    # Historical fields without independent range evidence retain their good
    # monthly maps, but absence/corruption cannot establish a certain rejection.
    raw_months = ocr.fields.get("월별고지금액")
    if raw_months is None:
        return review()
    try:
        found = json.loads(raw_months)
        if not isinstance(found, dict) or any(month not in found for month in req.premium_months):
            return review()
    except (ValueError, TypeError):
        return review()
    return []


def _check_document(
    req: DocRequirement,
    ocr: OcrResult,
    declared_issue_date: date | None = None,
    file_format: str = "pdf",
    identity: Identity | None = None,
    related_nhis_docs: list[tuple[str, dict[str, str]]] | None = None,
    suggested_slot_label: str | None = None,
) -> CheckResult:
    """업로드된 서류 한 건을 적합/부적합/확인필요로 판정한다.

    `identity`(본인인증 결과)가 있으면 서류의 성명·생년월일이 본인 것인지 대조한다.
    """
    findings: list[CheckFinding] = []
    nhis_review_needed = False

    # File facts are independent of OCR confidence and survive type failure.
    if ocr.is_encrypted:
        return CheckResult("FAIL", [_finding("UNREADABLE_FILE", "파일을 열 수 없습니다.", req)])
    from ..ocr.file_evidence import resolution_defect
    if (size := resolution_defect(ocr)) is not None:
        finding = _finding(CODE_IMAGE_RESOLUTION_TOO_LOW,
                           "원본 이미지가 너무 작아 서류 종류 또는 주요 내용을 판독할 수 없습니다.", req)
        finding.detail = f"원본 {size['width']}×{size['height']}px; 짧은 변 600px 및 긴 변 800px 미만과 미판독 조건 모두 충족."
        findings.append(finding)
        try:
            data = json.loads(ocr.fields.get("독립쪽표기자료", "null"))
            markers = data["markers"]
            if (data["confidence"] >= .85 and len(markers) == ocr.page_count and
                    all(isinstance(m, list) and len(m) == 2 and
                        all(type(v) is int for v in m) and 1 <= m[0] <= m[1] for m in markers) and
                    len({m[1] for m in markers}) == 1 and len({m[0] for m in markers}) < markers[0][1]):
                findings.append(_finding(CODE_PAGES_INCOMPLETE,
                    f"서류 {markers[0][1]}쪽 중 {len({m[0] for m in markers})}쪽만 올라왔습니다. 빠진 쪽까지 모두 올려 주세요.", req))
        except (ValueError, TypeError, KeyError, IndexError):
            pass
        return CheckResult("FAIL", findings)

    # 종류 판별이 끝나지 않았거나 다른 지원 서류로 판명되면 여기서 끝낸다.
    # 그 파일과 무관한 발급일·필수 항목 경고를 뒤에 붙이지 않는다.
    if not ocr.is_encrypted:
        detected = ocr.detected_doc_type
        if detected is None:
            finding = CheckFinding(
                code=CODE_UNKNOWN_DOCUMENT_TYPE,
                message=f"'{req.label}' 자리에 올리신 파일의 서류 종류를 판별하지 못했습니다. 담당자가 확인합니다.",
                link=req.issuer_url,
                severity="NEEDS_REVIEW",
                how_to_fix=HOW_TO_FIX[CODE_UNKNOWN_DOCUMENT_TYPE],
                detail=ocr.classification_evidence or "본문에서 지원 서류의 제목·서식 단서를 찾지 못했습니다.",
            )
            return CheckResult(status="NEEDS_REVIEW", findings=[finding])
        elif not req.accepts(detected):
            expected_label = req.label if req.accepted_doc_types else _display_doc_type(req.doc_type)
            detected_label = _display_doc_type(detected)
            object_particle = "을" if _has_final_consonant(detected_label) else "를"
            subject_particle = "이" if _has_final_consonant(expected_label) else "가"
            title = f"'{expected_label}' 자리에 '{detected_label}'{object_particle} 올리신 것 같습니다."
            body = f"이 자리에는 {expected_label}{subject_particle} 필요합니다."
            if suggested_slot_label:
                body += f"\n{suggested_slot_label} 칸에 올리실 파일이라면 그 칸에 올려 주세요."
            evidence = ocr.classification_evidence or f"본문 단서로 '{_display_doc_type(detected)}' 판별"
            finding = CheckFinding(
                code="WRONG_DOCUMENT_TYPE",
                message=title,
                how_to_fix=body,
                link=req.issuer_url,
                detail=evidence,
            )
            # 다른 항목을 못 읽어도 제목은 확실히 읽었을 수 있다.
            type_confidence = ocr.classification_confidence or ocr.confidence
            if type_confidence < engine_config.OCR_CONFIDENCE_THRESHOLD:
                _uncertain(finding)
            return CheckResult(status=finding.severity, findings=[finding])

    if ocr.detected_doc_type is DocType.RESIDENT_ABSTRACT:
        try:
            data = json.loads(ocr.fields.get("주소날짜검증자료", "null"))
            if (data["status"] == "MISSING" and data["confidence"] >= .85 and
                    ocr.classification_confidence >= .85):
                finding = _finding(CODE_MISSING_ADDRESS_DATES,
                    "초본 주소 이력에 발생일·신고일 날짜 값이 없어 도 거주기간을 확인할 수 없습니다.", req)
                finding.detail = "주소 표·행은 확인됐지만 날짜가 없습니다. 신청서 전입일은 참고 입력값이며 서류상 거주기간 근거를 대신하지 않습니다."
                findings.append(finding)
        except (ValueError, TypeError, KeyError):
            pass

    if ocr.detected_doc_type is DocType.DAILY_WORK_RECORD and ocr.tier != "fixture":
        from engine_v2.extractors.daily_work_record import selection_status
        if selection_status(ocr.fields) == "PARTIAL":
            return CheckResult("FAIL", [_finding(CODE_DAILY_RECORDS_PARTIALLY_SELECTED,
                "일용근로 이력 중 일부만 선택해 발급된 서류입니다. 전체 이력을 선택해 다시 발급받아 올려 주세요.", req)])
        if ocr.fields.get("양식판독상태") != "완전":
            return CheckResult("NEEDS_REVIEW", [_finding(CODE_REQUIRED_FIELD_UNREADABLE,
                "일용근로·노무제공내역서의 표·조회기간·확인 내용을 완전히 읽지 못했습니다. 담당자가 확인합니다.",
                req, field="표·조회기간")])
        if identity is not None and not ocr.fields.get("생년월일"):
            try:
                candidates = json.loads(ocr.fields.get("생년월일후보", "[]"))
                matched = (ocr.fields.get("성명", "").replace(" ", "") == identity.name and
                           identity.birth.isoformat() in candidates)
            except (ValueError, TypeError):
                matched = False
            if not matched:
                return CheckResult("NEEDS_REVIEW", [_finding(CODE_IDENTITY_UNCERTAIN,
                    "일용근로 서류의 신청인 성명·생년월일을 본인인증 정보와 확인해야 합니다.", req)])

    if (not ocr.is_encrypted and ocr.tier != "fixture" and ocr.detected_doc_type is DocType.BIZ_REG_PROOF):
        from ..ocr.localocr import ensure_business_required_fields

        ensure_business_required_fields(ocr)
        if ocr.fields.get("양식판독상태") != "완전":
            return CheckResult(status="NEEDS_REVIEW", findings=[_finding(
                CODE_REQUIRED_FIELD_UNREADABLE,
                "사업자등록증명의 필수 정보 또는 양식을 완전히 확인하지 못했습니다. 담당자가 원본을 확인합니다.",
                req, field="사업자등록증명 필수 정보",
            )])
        checked, mismatched = compare(identity, ocr.fields) if identity is not None else ([], [])
        if len(checked) != 2 or mismatched:
            return CheckResult(status="NEEDS_REVIEW", findings=[_finding(
                CODE_IDENTITY_UNCERTAIN,
                "사업자등록증명의 대표자 성명·생년월일을 본인인증 정보와 확인해야 합니다. 담당자가 원본을 확인합니다.",
                req,
            )])

    if (not ocr.is_encrypted and ocr.tier != "fixture"
            and ocr.detected_doc_type is DocType.INSURANCE_4
            and ocr.fields.get("양식판독상태") == "불완전"):
        finding = _insurance_identity_unreadable(req, ocr) or _finding(
            CODE_REQUIRED_FIELD_UNREADABLE,
            "4대보험 서류의 양식 또는 가입 표를 완전히 확인하지 못했습니다. 담당자가 원본을 확인합니다.",
            req, field="양식·가입 표",
        )
        return CheckResult(status="NEEDS_REVIEW", findings=[finding])

    if (not ocr.is_encrypted and ocr.tier != "fixture"
            and (ocr.detected_doc_type is DocType.NHIS_ACQUISITION_LOSS or
                 (ocr.detected_doc_type is DocType.NHIS_QUALIFICATION and "양식판독상태" in ocr.fields))):
        missing = []
        for label in ("성명", "생년월일", "발급일"):
            value = str(ocr.fields.get(label) or "").strip()
            valid = bool(value)
            if label != "성명":
                try:
                    date.fromisoformat(value[:10])
                except ValueError:
                    valid = False
            if not valid:
                missing.append(label)
        if ocr.fields.get("양식판독상태") == "불완전":
            return CheckResult(status="NEEDS_REVIEW", findings=[_finding(
                CODE_REQUIRED_FIELD_UNREADABLE,
                f"{_display_doc_type(ocr.detected_doc_type)}의 양식 또는 표 구조를 완전히 확인하지 못했습니다. 담당자가 원본을 확인합니다.",
                req, field="양식·표 구조",
            )])
        if missing:
            nhis_review_needed = True
            findings.append(_finding(
                CODE_REQUIRED_FIELD_UNREADABLE,
                f"{_display_doc_type(ocr.detected_doc_type)}의 필수 정보를 읽지 못했습니다. 담당자가 원본을 확인합니다.",
                req, field="·".join(missing),
            ))

    # 2) 엔진 단건 검사 — 암호/화질/서명/발급일/입력일 대조/신뢰도.
    engine_doc = to_engine_document(req, ocr, declared_issue_date, file_format, req.date_basis)
    if (not ocr.is_encrypted and ocr.tier == "pdftext" and req.date_basis == "issue_date"
            and engine_doc.issue_date is None
            and (req.check_declared_date or req.min_issue_date is not None or req.max_issue_date is not None)):
        findings.append(_finding(
            CODE_REQUIRED_FIELD_UNREADABLE,
            "서류의 발급일 라벨과 날짜를 확인하지 못했습니다. 담당자가 원본을 확인합니다.",
            req, field="발급일",
        ))
    for f in engine_check_single_document(engine_doc, to_engine_spec(req)):
        finding = _finding(f.code.value, f.message, req)
        if f.code.value == "DECLARED_DATE_MISMATCH" and req.date_basis == "issue_date":
            actual = engine_doc.issue_date
            if actual is not None and declared_issue_date is not None:
                finding.message = (
                    f"서류에서 읽은 발급일은 {_date_korean(actual)}입니다. "
                    f"입력하신 날짜({_date_korean(declared_issue_date)})와 다릅니다. 서류를 보고 고쳐 주세요. "
                    f"(서류 날짜 {actual.isoformat()}, 입력 날짜 {declared_issue_date.isoformat()})"
                )
                finding.how_to_fix = "입력하신 발급일을 서류를 보고 다시 확인해 주세요."
                finding.detail = (
                    f"발급일 판독 신뢰도 {ocr.confidence:.2f}; "
                    f"확정 불일치 기준 {engine_config.OCR_CONFIDENCE_THRESHOLD:.2f} 이상."
                )
        elif f.code.value == "DOCUMENT_ISSUED_TOO_EARLY" and req.date_basis == "issue_date":
            actual = engine_doc.issue_date
            cutoff = req.min_issue_date
            if actual is not None and cutoff is not None:
                finding.message = (
                    f"서류에서 읽은 발급일은 {_date_korean(actual)}입니다. "
                    f"이 사업은 {_date_korean(cutoff)} 이후 발급된 서류만 인정합니다. "
                    f"(서류 발급일 {actual.isoformat()})"
                )
                finding.how_to_fix = (
                    f"{_date_korean(cutoff)} 이후 새로 발급받아 올려 주세요. "
                    f"(기준일: {cutoff.isoformat()})"
                )
        date_label = {
            "payment_date": "결제일", "interview_date": "면접일", "exam_date": "응시일",
        }.get(req.date_basis)
        if date_label:
            finding.message = finding.message.replace("발급일", date_label).replace("발급분", "기준 날짜")
            finding.how_to_fix = finding.how_to_fix.replace("발급일", date_label).replace("발급분", "기준 날짜")
        if (f.code.value in {"DOCUMENT_ISSUED_TOO_EARLY", "DOCUMENT_ISSUED_AFTER_APPLICATION"}
                and ocr.confidence < engine_config.OCR_CONFIDENCE_THRESHOLD):
            _uncertain(finding)
        findings.append(finding)

    # 3) 데모가 얹는 항목.
    if not ocr.is_encrypted and ocr.detected_doc_type is DocType.RESIDENT_ABSTRACT:
        findings.extend(_check_resident_pages(ocr, req))
    if ocr.is_screen_capture:
        findings.append(
            _finding(
                CODE_SCREEN_CAPTURE,
                "모니터 화면을 캡처한 이미지로 보입니다. 담당자가 직접 확인합니다.",
                req,
            )
        )

    # 서류에 반드시 찍혀 있어야 하는 항목. 취업패키지 응시확인서·성적표의
    # "응시일 표기 필수"가 여기로 들어온다. 사업별 하드코딩 없이 체크리스트가
    # 요구한 필드만 본다.
    #
    # 서류 종류가 이미 틀렸다면 필드를 따지지 않는다. "엉뚱한 서류다 + 그 서류에
    # 응시일이 없다"를 같이 띄우면 신청자는 무엇부터 고쳐야 할지 헷갈린다.
    if not ocr.is_encrypted and req.accepts(ocr.detected_doc_type):
        for name in req.required_fields:
            if not str(ocr.fields.get(name) or "").strip():
                if name == "결제금액" and req.slot_key.endswith("_receipt"):
                    findings.append(CheckFinding(
                        code=CODE_RECEIPT_AMOUNT_UNREADABLE,
                        message="영수증 결제금액을 자동으로 확인하지 못했습니다. 담당자가 원본을 확인합니다.",
                        how_to_fix="영수증에 표시된 결제금액을 확인할 수 있도록 담당자에게 원본을 제출해 주세요.",
                        severity="NEEDS_REVIEW",
                    ))
                    continue
                if ocr.tier in ("localocr", "jbai") and ocr.engine != "pdftext":
                    # 사진·스캔을 OCR로 읽었으면 '안 적힌 것'과 '못 읽은 것'을 구별할 수 없다.
                    # 글자층 PDF에서 없을 때만 부적합으로 본다 (영수증 결제금액 미판독과 같은 처리).
                    findings.append(
                        _finding(
                            CODE_REQUIRED_FIELD_UNREADABLE,
                            f"'{req.label}'에서 {name}을(를) 자동으로 확인하지 못했습니다. 담당자가 원본을 확인합니다.",
                            req,
                            field=name,
                        )
                    )
                    continue
                findings.append(
                    _finding(
                        CODE_MISSING_REQUIRED_FIELD,
                        f"'{req.label}'에서 {name}을(를) 찾지 못했습니다. "
                        f"{name}이(가) 표기된 서류만 인정됩니다.",
                        req,
                        field=name,
                    )
                )

    if (not ocr.is_encrypted and ocr.detected_doc_type is DocType.NHIS_PAYMENT
            and req.slot_key == "nhis_payment" and req.premium_months):
        findings.extend(_check_billing_months(ocr, req))

    if (not ocr.is_encrypted and req.slot_key == "nhis_acquisition_loss" and req.recent_years
            and (ocr.fields.get("자격이력자료") or ocr.tier != "fixture")):
        try:
            data = json.loads(ocr.fields["자격이력자료"])
            issue = ocr.issue_date
            if issue is None:
                issue = date.fromisoformat(ocr.fields.get("발급일", ""))
            covered, explicit_period = _nhis_history_coverage(
                data, issue, req.recent_years, ocr.fields.get("양식판독상태") == "완전")
            if covered is None:
                raise ValueError("undetermined coverage")
            if covered is False:
                finding = _finding(
                    "NHIS_HISTORY_PERIOD_MISSING",
                    f"자격득실확인서에 최근 {req.recent_years}년 변동내역이 포함되지 않았습니다.",
                    req, years=str(req.recent_years),
                )
                if (not explicit_period or ocr.confidence < engine_config.OCR_CONFIDENCE_THRESHOLD
                        or ocr.image_quality < engine_config.IMAGE_QUALITY_THRESHOLD):
                    _uncertain(finding)
                findings.append(finding)
        except (ValueError, TypeError, KeyError):
            findings.append(_finding(
                "NHIS_HISTORY_PERIOD_UNREADABLE",
                "자격득실확인서의 조회 기간을 확인하지 못했습니다. 담당자가 확인합니다.", req,
            ))

    abstract_applicant_name = ocr.fields.get("초본신청인성명")
    abstract_applicant_birth = ocr.fields.get("초본신청인생년월일")
    abstract_applicant_birth_date = None
    try:
        abstract_applicant_birth_date = date.fromisoformat((abstract_applicant_birth or "")[:10])
    except ValueError:
        pass
    abstract_applicant_missing = (
        req.doc_type is DocType.RESIDENT_ABSTRACT
        and ocr.detected_doc_type is DocType.RESIDENT_ABSTRACT
        and ocr.tier != "fixture"
        and (not abstract_applicant_name or abstract_applicant_birth_date is None)
    )
    if abstract_applicant_missing:
        findings.append(CheckFinding(
            CODE_RESIDENT_APPLICANT_UNREADABLE,
            "초본의 신청인 정보를 읽지 못해 담당자가 확인합니다.",
            severity="NEEDS_REVIEW",
            how_to_fix=RETAKE_GUIDANCE,
            detail="첫 쪽 신청인 성명과 생년월일을 모두 판독해야 본인인증 정보와 대조할 수 있습니다.",
        ))

    if (not ocr.is_encrypted and ocr.tier != "fixture"
            and ocr.detected_doc_type is DocType.INSURANCE_4):
        finding = _insurance_identity_unreadable(req, ocr)
        if finding:
            findings.append(finding)

    # 본인 대조 — 서류 종류가 맞았을 때만 본다 (엉뚱한 서류면 그 사유가 먼저다).
    # 판독이 확실할 때만 '본인 서류가 아님'으로 반려하고, 불확실하면 담당자에게 넘긴다.
    # 신청자 안내에는 서류에 적힌 남의 이름을 되읊지 않는다.
    # 시연용 고정 샘플(Tier1 fixture)은 전부 가상 인물 명의라 대조하지 않는다 — 실제로
    # 읽은 서류(로컬 판독·텍스트 PDF)만 대상이다. 본인 초본 + 나머지는 샘플로 시연할 수 있게.
    if (
        identity is not None
        and not ocr.is_encrypted
        and req.accepts(ocr.detected_doc_type)
    ):
        if ocr.detected_doc_type in (DocType.NHIS_PAYMENT, DocType.NHIS_QUALIFICATION):
            assessment = nhis_subscriber_assessment(
                identity, str(ocr.detected_doc_type), ocr.fields, related_nhis_docs or []
            )
            if assessment:
                code, severity, applicant_message, officer_detail = assessment
                findings.append(CheckFinding(
                    code,
                    applicant_message,
                    HOW_TO_FIX.get(code, "가입자 명의 확인이 필요해 담당자가 확인합니다."),
                    severity=severity,
                    detail=officer_detail,
                ))
        elif ocr.detected_doc_type is DocType.NHIS_ACQUISITION_LOSS and ocr.tier != "fixture":
            checked, mismatched = compare(identity, ocr.fields)
            if len(checked) != 2 or mismatched:
                nhis_review_needed = True
                findings.append(_finding(
                    CODE_IDENTITY_UNCERTAIN,
                    "자격득실확인서의 성명·생년월일을 본인인증 정보와 확인해야 합니다. 담당자가 원본을 확인합니다.",
                    req,
                ))
        elif req.doc_type is DocType.RESIDENT_ABSTRACT and ocr.detected_doc_type is DocType.RESIDENT_ABSTRACT and ocr.tier != "fixture":
            if abstract_applicant_missing:
                pass  # 신청인 칸 미판독은 위에서 인증 여부와 무관하게 확인필요로 기록했다.
            elif (abstract_applicant_name or "").replace(" ", "") != identity.name or abstract_applicant_birth_date != identity.birth:
                finding = CheckFinding(
                    CODE_IDENTITY_MISMATCH,
                    "본인이 직접 발급받은 초본이 아닙니다. 본인 명의로 발급받아 다시 올려 주세요.",
                    severity="FAIL",
                    detail=(
                        f"초본 첫 쪽 신청인 칸 판독: 성명={abstract_applicant_name}, 생년월일={abstract_applicant_birth_date.isoformat()}; "
                        f"본인인증 정보와 일치하지 않음."
                    ),
                )
                if ocr.confidence < engine_config.OCR_CONFIDENCE_THRESHOLD:
                    finding.code = CODE_IDENTITY_UNCERTAIN
                    _uncertain(finding)
                findings.append(finding)
            else:
                # 기존 주민등록표 성명·생년월일 대조도 유지한다. 신청인 칸이 본인과
                # 맞더라도 초본 본문에서 읽은 대상자 정보가 다르면 기존 신뢰도 규칙을 쓴다.
                _, mismatched = compare(identity, ocr.fields)
                if mismatched:
                    what = "·".join(mismatched)
                    if ocr.confidence >= engine_config.OCR_CONFIDENCE_THRESHOLD:
                        findings.append(_finding(
                            CODE_IDENTITY_MISMATCH,
                            f"올리신 '{req.label}'의 {what}이(가) 본인인증 정보와 다릅니다.",
                            req,
                        ))
                    else:
                        findings.append(_finding(
                            CODE_IDENTITY_UNCERTAIN,
                            f"올리신 '{req.label}'의 {what}이(가) 본인인증 정보와 다르게 판독되었습니다. "
                            "담당자가 원본에서 직접 확인합니다.",
                            req,
                        ))
        elif req.doc_type is DocType.ADMIN_INFO_CONSENT and ocr.detected_doc_type is DocType.ADMIN_INFO_CONSENT:
            name = str(ocr.fields.get("성명") or "").strip()
            birth = str(ocr.fields.get("생년월일") or "").strip()[:10]
            try:
                birth_date = date.fromisoformat(birth)
            except ValueError:
                birth_date = None
            if not name or birth_date is None:
                findings.append(CheckFinding(
                    "ADMIN_CONSENT_IDENTITY_UNREADABLE",
                    "서식의 본인 정보를 자동 판독하지 못했습니다. 담당자가 원본을 확인합니다.",
                    severity="NEEDS_REVIEW",
                    detail="종이 서식의 성명과 생년월일을 모두 읽어 본인인증 정보와 대조해야 합니다.",
                ))
            elif name.replace(" ", "") != identity.name or birth_date != identity.birth:
                severity = "FAIL" if ocr.confidence >= engine_config.OCR_CONFIDENCE_THRESHOLD else "NEEDS_REVIEW"
                findings.append(CheckFinding(
                    "ADMIN_CONSENT_IDENTITY_MISMATCH" if severity == "FAIL" else "ADMIN_CONSENT_IDENTITY_UNCERTAIN",
                    "서식의 본인 정보가 본인인증 정보와 다릅니다. 담당자가 원본을 확인합니다." if severity != "FAIL" else "본인 명의 서식이 아닙니다. 본인 명의 서식으로 다시 제출해 주세요.",
                    severity=severity,
                    detail=f"서식 판독 성명={name}, 생년월일={birth_date.isoformat()}; 본인인증 정보와 대조 결과 불일치.",
                ))
        elif ocr.tier != "fixture":
            _, mismatched = compare(identity, ocr.fields)
            if mismatched:
                what = "·".join(mismatched)
                if ocr.confidence >= engine_config.OCR_CONFIDENCE_THRESHOLD:
                    findings.append(
                        _finding(
                            CODE_IDENTITY_MISMATCH,
                            f"올리신 '{req.label}'의 {what}이(가) 본인인증 정보와 다릅니다.",
                            req,
                        )
                    )
                else:
                    findings.append(
                        _finding(
                            CODE_IDENTITY_UNCERTAIN,
                            f"올리신 '{req.label}'의 {what}이(가) 본인인증 정보와 다르게 판독되었습니다. "
                            "담당자가 원본에서 직접 확인합니다.",
                            req,
                        )
                    )

    if (
        req.doc_type is DocType.RESIDENT_ABSTRACT
        and ocr.fields.get("주소변동내역") in {"미포함", "없음"}
    ):
        findings.append(
            _finding(
                CODE_MISSING_ADDRESS_HISTORY,
                "주민등록초본에 최근 5년 주소변동내역이 포함되어 있지 않습니다.",
                req,
            )
        )

    if (
        req.doc_type is DocType.RESIDENT_ABSTRACT
        and ocr.fields.get("주소이력건수") == "1"
    ):
        findings.append(CheckFinding(
            CODE_PAST_ADDRESS_OMISSION_SUSPECTED,
            "과거 주소 변동사항이 빠진 초본으로 보입니다. 정부24에서 '과거의 주소 변동사항'을 포함해 다시 발급받으면 거주기간이 정확히 계산됩니다.",
            severity="NEEDS_REVIEW",
            detail="판독한 주소 이력이 1건뿐이어서 과거 주소 변동사항이 생략됐을 가능성이 있습니다. 부적합으로 단정하지 않습니다.",
        ))

    if nhis_review_needed:
        # Incomplete or mismatching identity cannot establish this applicant's
        # eligibility. Retain legacy finding codes while sending them for review.
        for finding in findings:
            if finding.severity == "FAIL":
                _uncertain(finding)
    if any(f.severity == "FAIL" for f in findings):
        status = "FAIL"
    elif any(f.severity == "NEEDS_REVIEW" for f in findings):
        status = "NEEDS_REVIEW"
    else:
        status = "PASS"

    return CheckResult(status=status, findings=findings)


def check_document(
    req: DocRequirement,
    ocr: OcrResult,
    declared_issue_date: date | None = None,
    file_format: str = "pdf",
    identity: Identity | None = None,
    related_nhis_docs: list[tuple[str, dict[str, str]]] | None = None,
    suggested_slot_label: str | None = None,
) -> CheckResult:
    """Check one upload and adapt only photo-specific guidance to its format."""
    result = _check_document(req, ocr, declared_issue_date, file_format, identity,
                             related_nhis_docs, suggested_slot_label)
    if file_format.lower() == "pdf":
        for finding in result.findings:
            finding.message = finding.message.replace(PHOTO_RETAKE_GUIDANCE, "")
            finding.how_to_fix = finding.how_to_fix.replace(PHOTO_RETAKE_GUIDANCE, "")
    return result

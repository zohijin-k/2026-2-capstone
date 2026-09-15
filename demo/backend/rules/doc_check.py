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

from ..engine_adapter import engine_check_single_document, engine_models
from ..ocr.base import OcrResult
from .doc_types import DocType, confusable_with
from .required_docs import DocRequirement

#: 데모가 자체적으로 얹는 사유 코드. 엔진 `ReasonCode`에 없는 항목이다.
#: 진과 합의되면 엔진 쪽으로 옮긴다 (design.md 9절 E-목록의 후속).
CODE_SCREEN_CAPTURE = "SCREEN_CAPTURE_SUSPECTED"
CODE_MISSING_ADDRESS_HISTORY = "MISSING_ADDRESS_HISTORY"
CODE_UNKNOWN_DOCUMENT_TYPE = "UNKNOWN_DOCUMENT_TYPE"
CODE_MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"

#: 사유 코드 → 해결 방법. 공고문 문구와 발급 절차를 그대로 옮긴 것이다.
#: "무엇이 잘못됐는지"만 말하면 신청자는 또 전화한다. 해결 방법이 같이 있어야 한다.
HOW_TO_FIX: dict[str, str] = {
    "WRONG_DOCUMENT_TYPE": "요구되는 서류와 다른 종류를 올리셨습니다. 아래 발급처에서 '{label}'을(를) 다시 발급받아 올려 주세요.",
    "DOCUMENT_ISSUED_TOO_EARLY": "{cutoff} 이후 발급분만 인정됩니다. 발급처에서 새로 발급받아 다시 올려 주세요.",
    "DECLARED_DATE_MISMATCH": "입력하신 발급일과 서류에 찍힌 발급일이 다릅니다. 발급일을 다시 확인하시거나, 올바른 파일을 올려 주세요.",
    "UNREADABLE_FILE": "PDF 암호를 해제한 뒤 다시 올려 주세요. 발급처에서 '암호 설정 안 함'으로 재발급받는 것이 가장 확실합니다.",
    "LOW_IMAGE_QUALITY": "글자가 또렷하게 보이도록 스캔본이나 밝은 곳에서 찍은 사진으로 다시 올려 주세요. pdf 파일을 권장합니다.",
    "LOW_OCR_CONFIDENCE": "자동 판독이 되지 않은 항목이 있어 담당자가 직접 확인합니다. 더 선명한 파일이 있다면 교체해 주세요.",
    "MISSING_SIGNATURE": "서명란에 서명한 뒤 다시 올려 주세요.",
    CODE_SCREEN_CAPTURE: "모니터 화면을 캡처한 이미지는 인정되지 않습니다. 발급처에서 내려받은 pdf 원본이나 스캔본으로 올려 주세요.",
    CODE_MISSING_ADDRESS_HISTORY: "정부24에서 초본을 발급할 때 '과거의 주소 변동사항(최근 5년)' 포함을 체크해 다시 발급받아 주세요.",
    CODE_MISSING_REQUIRED_FIELD: "{field}이(가) 표기된 서류로 다시 발급받아 올려 주세요. 발급 기관에 {field} 표기를 요청하시면 됩니다.",
    CODE_UNKNOWN_DOCUMENT_TYPE: "자동으로 서류 종류를 판별하지 못했습니다. 담당자가 직접 확인하므로 그대로 두셔도 되고, 더 선명한 파일이 있다면 교체해 주세요.",
}

#: NEEDS_REVIEW로만 보내는 코드. 나머지는 확정 부적합(FAIL)이다.
#: 화면캡처는 오탐 시 신청자가 억울해지므로 자동 반려하지 않는다.
REVIEW_ONLY_CODES = {
    "LOW_OCR_CONFIDENCE",
    CODE_SCREEN_CAPTURE,
    CODE_UNKNOWN_DOCUMENT_TYPE,
}


@dataclass
class CheckFinding:
    code: str
    message: str
    how_to_fix: str = ""
    link: str = ""
    #: FAIL | NEEDS_REVIEW
    severity: str = "FAIL"

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
            "how_to_fix": self.how_to_fix,
            "link": self.link,
            "severity": self.severity,
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
        check_declared_date=req.check_declared_date,
    )


def to_engine_document(
    req: DocRequirement,
    ocr: OcrResult,
    declared_issue_date: date | None,
    file_format: str,
):
    """판독 결과 → 엔진 `Document`.

    `doc_type`에는 **요구된 서류 종류**를 넣는다. 엔진의 단건 검사는 doc_type을
    메시지 렌더링에만 쓰고, 오분류 판정은 데모 쪽에서 별도로 하기 때문이다.
    """
    return engine_models.Document(
        doc_type=str(req.doc_type),
        file_format=file_format,
        ocr_confidence=ocr.confidence,
        image_quality_score=ocr.image_quality,
        has_signature=ocr.has_signature,
        issue_date=ocr.issue_date,
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


def check_document(
    req: DocRequirement,
    ocr: OcrResult,
    declared_issue_date: date | None = None,
    file_format: str = "pdf",
) -> CheckResult:
    """업로드된 서류 한 건을 적합/부적합/확인필요로 판정한다."""
    findings: list[CheckFinding] = []

    # 1) 오분류 — 공고문이 직접 지목한 미비 사유(초본 자리에 등본)를 가장 먼저 본다.
    #    파일을 열지도 못한 경우(암호)에는 판별 자체가 안 되므로 건너뛴다.
    if not ocr.is_encrypted:
        detected = ocr.detected_doc_type
        if detected is None:
            findings.append(
                _finding(
                    CODE_UNKNOWN_DOCUMENT_TYPE,
                    f"'{req.label}' 자리에 올리신 파일의 서류 종류를 자동으로 판별하지 못했습니다.",
                    req,
                )
            )
        elif not req.accepts(detected):
            # 인정되는 서류가 여럿인 자리(응시확인서 또는 성적표)는 그중 아무것도
            # 아닐 때만 오분류다.
            confusable = confusable_with(req.doc_type)
            extra = (
                f" '{req.doc_type}'와 '{detected}'는 이름이 비슷하지만 다른 서류입니다."
                if detected in confusable
                else ""
            )
            findings.append(
                _finding(
                    "WRONG_DOCUMENT_TYPE",
                    f"'{req.label}'을(를) 올려야 하는데 '{detected}'이(가) 업로드되었습니다.{extra}",
                    req,
                )
            )

    # 2) 엔진 단건 검사 — 암호/화질/서명/발급일/입력일 대조/신뢰도.
    engine_doc = to_engine_document(req, ocr, declared_issue_date, file_format)
    for f in engine_check_single_document(engine_doc, to_engine_spec(req)):
        findings.append(_finding(f.code.value, f.message, req))

    # 3) 데모가 얹는 항목.
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
                findings.append(
                    _finding(
                        CODE_MISSING_REQUIRED_FIELD,
                        f"'{req.label}'에서 {name}을(를) 찾지 못했습니다. "
                        f"{name}이(가) 표기된 서류만 인정됩니다.",
                        req,
                        field=name,
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

    if any(f.severity == "FAIL" for f in findings):
        status = "FAIL"
    elif findings:
        status = "NEEDS_REVIEW"
    else:
        status = "PASS"

    return CheckResult(status=status, findings=findings)

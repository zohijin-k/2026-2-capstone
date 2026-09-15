"""채점 입력값 조립 — 신청서 입력값 + 서류 판독값 → `ScoringFacts`.

두 출처가 같은 값을 갖는 항목이 있다(전입일: 신청서 입력 vs 초본 판독). 원칙은
**서류 판독값 우선**이다. 심사는 서류로 하는 것이고, 신청서 입력값은 서류가 없거나
판독이 안 될 때의 보조값이다. 어느 쪽을 썼는지는 `FactSource.origin`에 남겨
담당자가 되짚을 수 있게 한다.

`scoring.py`와 마찬가지로 DB·HTTP를 모른다. 입력은 순수 dict다.
"""

from datetime import date
from typing import Any

from .doc_types import DocType
from .scoring import FactSource, ScoringFacts

#: 업로드 서류 한 건을 채점 입력으로 넘길 때의 최소 형태.
#: {"document_id": 1, "doc_type": "건강보험료납부확인서", "fields": {...}, "bboxes": {...}}
DocFact = dict[str, Any]


def parse_ymd(value: Any) -> date | None:
    """서식1의 년·월·일 3분할 입력({"y","m","d"}) 또는 ISO 문자열 → date."""
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    if isinstance(value, dict):
        try:
            return date(int(value.get("y")), int(value.get("m")), int(value.get("d")))
        except (TypeError, ValueError):
            return None
    return None


def parse_int(value: Any) -> int | None:
    """'200,000' · '4인' · 200000 → int. 숫자가 없으면 None."""
    if isinstance(value, int):
        return value
    if not isinstance(value, str):
        return None
    digits = "".join(c for c in value if c.isdigit())
    return int(digits) if digits else None


#: 근로확인서류 ⑥ (5종 택1). 취업일 대조 근거로 쓴다.
WORK_PROOF_TYPES = (
    DocType.INSURANCE_4,
    DocType.DAILY_WORK_RECORD,
    DocType.LABOR_CONTRACT,
    DocType.BIZ_REG_PROOF,
    DocType.FARM_BIZ_CERT,
    DocType.FISHERY_BIZ_CERT,
)


def _find(documents: list[DocFact], doc_type: DocType) -> DocFact | None:
    for d in documents:
        if d.get("doc_type") == str(doc_type):
            return d
    return None


def _find_any(
    documents: list[DocFact], doc_types: tuple[DocType, ...]
) -> DocFact | None:
    for doc_type in doc_types:
        hit = _find(documents, doc_type)
        if hit is not None:
            return hit
    return None


def _field(doc: DocFact | None, key: str) -> str | None:
    if not doc:
        return None
    value = (doc.get("fields") or {}).get(key)
    return value if isinstance(value, str) and value else None


def _bbox(doc: DocFact | None, key: str) -> dict[str, Any] | None:
    if not doc:
        return None
    box = (doc.get("bboxes") or {}).get(key)
    return box if isinstance(box, dict) else None


def _source(doc: DocFact | None, doc_type: DocType, bbox_key: str, origin: str) -> FactSource:
    return FactSource(
        doc_type=doc_type if doc else None,
        document_id=doc.get("document_id") if doc else None,
        bbox=_bbox(doc, bbox_key),
        origin=origin,
    )


def build_facts(form1: dict[str, Any], documents: list[DocFact]) -> ScoringFacts:
    """서식1 입력값과 서류 판독 결과에서 채점에 쓸 사실값만 뽑는다."""
    payment = _find(documents, DocType.NHIS_PAYMENT)
    qualification = _find(documents, DocType.NHIS_QUALIFICATION)
    abstract = _find(documents, DocType.RESIDENT_ABSTRACT)
    insurance4 = _find(documents, DocType.INSURANCE_4)

    # --- 1. 소득: 자격확인서의 가구원수 + 납부확인서의 고지금액 (R5.2) ---
    household = parse_int(_field(qualification, "가구원수"))
    household_origin = "건강보험 자격확인서 판독"
    if household is None:
        household = parse_int(form1.get("householdSize"))
        household_origin = "신청서 입력값(가구원 수)"
    premium = parse_int(_field(payment, "건강보험료"))
    insurance_type = (
        _field(qualification, "가입구분") or _field(payment, "가입구분") or "직장"
    )

    income_source = _source(
        payment,
        DocType.NHIS_PAYMENT,
        "건강보험료",
        f"건강보험료 납부확인서 고지금액 판독 · 가구원수는 {household_origin}",
    )

    # --- 2. 거주기간: 초본의 전입일 우선, 없으면 신청서 입력값 ---
    transfer_in = parse_ymd(_field(abstract, "전입일"))
    if transfer_in is not None:
        residence_source = _source(
            abstract, DocType.RESIDENT_ABSTRACT, "전입일", "주민등록초본 전입일 판독"
        )
    else:
        transfer_in = parse_ymd(form1.get("transferIn"))
        residence_source = FactSource(origin="신청서 입력값(최종 전입일)")

    # --- 3. 근로기간: 신청서의 현직장 취업일. 근로확인서류를 대조 근거로 붙인다 ---
    work_proof = _find_any(documents, WORK_PROOF_TYPES) or insurance4
    proof_type = (
        DocType(work_proof["doc_type"]) if work_proof and work_proof.get("doc_type") else None
    )
    employed_at = parse_ymd(form1.get("employedAt"))
    if employed_at is not None:
        work_source = FactSource(
            doc_type=proof_type,
            document_id=work_proof.get("document_id") if work_proof else None,
            bbox=_bbox(work_proof, "취업일"),
            origin="신청서 입력값(현 직장 취업일) · 근로확인서류와 대조",
        )
    else:
        employed_at = parse_ymd(_field(work_proof, "취업일"))
        work_source = FactSource(
            doc_type=proof_type,
            document_id=work_proof.get("document_id") if work_proof else None,
            bbox=_bbox(work_proof, "취업일"),
            origin="근로확인서류 취업일 판독",
        )

    # --- 4. 연령: 신청서 생년월일. 대조 근거는 주민등록초본이다 ---
    birth = parse_ymd(form1.get("birth"))
    age_source = FactSource(
        doc_type=DocType.RESIDENT_ABSTRACT if abstract else None,
        document_id=abstract.get("document_id") if abstract else None,
        bbox=_bbox(abstract, "생년월일"),
        origin="신청서 입력값(생년월일) · 주민등록초본과 대조",
    )

    return ScoringFacts(
        household_size=household,
        monthly_premium=premium,
        insurance_type=insurance_type,
        transfer_in_date=transfer_in,
        employment_date=employed_at,
        birth_date=birth,
        sources={
            "income": income_source,
            "residence": residence_source,
            "work": work_source,
            "age": age_source,
        },
    )


#: 주소 문자열에서 시군을 뽑을 때 쓰는 접미사.
_REGION_SUFFIXES = ("특별자치도", "광역시", "특별시")


def extract_region(address: str, known_regions: list[str]) -> str:
    """주소 문자열에서 시군명을 뽑는다.

    엔진 2단계가 `residence_region`을 시군 집합과 대조하므로(NOT_TARGET_REGION),
    자유입력 주소를 시군으로 환원해야 한다. 데모 범위라 문자열 포함 검사로 충분하다.
    실서비스는 도로명주소 API를 쓸 자리다.
    """
    flat = (address or "").replace(" ", "")
    for suffix in _REGION_SUFFIXES:
        flat = flat.replace(suffix, "")
    for region in known_regions:
        if region in flat:
            return region
        # "전주시 완산구"를 "전주"로만 적은 경우.
        if region.endswith(("시", "군")) and region[:-1] in flat:
            return region
    return ""

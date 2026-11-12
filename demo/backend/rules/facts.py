"""채점 입력값 조립 — 신청서 입력값 + 서류 판독값 → `ScoringFacts`.

두 출처가 같은 값을 갖는 항목이 있다(전입일: 신청서 입력 vs 초본 판독). 원칙은
**서류 판독값 우선**이다. 심사는 서류로 하는 것이고, 신청서 입력값은 서류가 없거나
판독이 안 될 때의 보조값이다. 어느 쪽을 썼는지는 `FactSource.origin`에 남겨
담당자가 되짚을 수 있게 한다.

`scoring.py`와 마찬가지로 DB·HTTP를 모른다. 입력은 순수 dict다.
"""

from datetime import date
import json
import math
import re
from typing import Any
from engine import config as engine_config
from engine_v2.extractors.nhis_payment import has_failed_payment_validation
from engine_v2.extractors.nhis_common import is_header_only_value

from .doc_types import DocType
from .household import parse_household_members
from .scoring import FactSource, ScoringFacts

#: 업로드 서류 한 건을 채점 입력으로 넘길 때의 최소 형태.
#: {"document_id": 1, "doc_type": "건강보험료납부확인서", "fields": {...}, "bboxes": {...}}
DocFact = dict[str, Any]
PAYMENT_AMOUNT_FIELDS = frozenset({
    "건강보험료", "월별고지금액", "장기요양보험료", "월별장기요양보험료",
    "보수외소득월액_건강", "월별보수외소득월액_건강",
})
DEFAULT_PAYMENT_MONTHS = ("2025-10", "2025-11", "2025-12")


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
    compact = value.replace(",", "").replace("원", "").replace(" ", "").replace("−", "-")
    if compact.startswith("-"):
        digits = "".join(c for c in compact[1:] if c.isdigit())
        return -int(digits) if digits else None
    digits = "".join(c for c in compact if c.isdigit())
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


def _payment_amounts_trusted(doc: DocFact | None) -> bool:
    fields = (doc or {}).get("fields") or {}
    if not doc or doc.get("doc_type") != str(DocType.NHIS_PAYMENT):
        return True
    if has_failed_payment_validation(fields):
        return False
    if doc.get("status") not in {None, "PASS"}:
        return False
    if "confidence" in doc:
        try:
            confidence = float(doc["confidence"])
            if isinstance(doc["confidence"], bool) or not math.isfinite(confidence) or confidence < engine_config.OCR_CONFIDENCE_THRESHOLD:
                return False
        except (TypeError, ValueError):
            return False
    return "양식판독상태" not in fields or fields["양식판독상태"] == "완전"


def _field(doc: DocFact | None, key: str) -> str | None:
    if not doc:
        return None
    if key in PAYMENT_AMOUNT_FIELDS and not _payment_amounts_trusted(doc):
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


def _insurance_doc_trusted(doc: DocFact | None, *, complete: bool) -> bool:
    if not doc or doc.get("status") not in {None, "PASS"}:
        return False
    fields = doc.get("fields") or {}
    if fields.get("판독검증실패"):
        return False
    if complete and fields.get("양식판독상태") != "완전":
        return False
    if not complete and fields.get("양식판독상태", "완전") != "완전":
        return False
    if "confidence" not in doc:
        return not complete  # legacy minimal facts have no confidence metadata
    try:
        confidence = float(doc["confidence"])
        return (not isinstance(doc["confidence"], bool) and math.isfinite(confidence) and
                confidence >= engine_config.OCR_CONFIDENCE_THRESHOLD)
    except (TypeError, ValueError):
        return False


def _insurance_facts(qualification, payment):
    evidence, sources = {}, {}
    for key, doc, doc_type, label in (
        ("A", qualification, DocType.NHIS_QUALIFICATION, "사업장관리번호"),
        ("B", payment, DocType.NHIS_PAYMENT, "사업장명칭"),
    ):
        fields = (doc or {}).get("fields") or {}
        state, value = fields.get(label + "_상태"), fields.get(label)
        declared_state = state
        usable = _insurance_doc_trusted(doc, complete=True) and isinstance(value, str)
        category = None
        if usable and state == "확실한 공란" and not re.search(r"[^\s|:：.·=~\-－—–]", value):
            category = "지역"
        elif usable and state == "값 있음":
            valid = (bool(re.fullmatch(r"[0-9]+", value)) if key == "A" else
                     bool(re.search(r"[가-힣A-Za-z]", value) and
                          re.fullmatch(r"[가-힣A-Za-z0-9\s()（）&.,·'’\-]+", value) and
                          not is_header_only_value(value)))
            if valid:
                category = "직장"
        state = state if category else "못 읽음"
        source_key = "insurance_a" if key == "A" else "insurance_b"
        source = _source(doc, doc_type, label + "_상태", f"{label} · {state} · {category or '모름'}")
        sources[source_key] = source
        evidence[key] = {"state": state, "declared_state": declared_state, "category": category,
                         "value": value, "source": source.as_dict()}

    explicit = []
    unsupported = False
    for kind, doc, doc_type in (("qualification", qualification, DocType.NHIS_QUALIFICATION),
                                ("payment", payment, DocType.NHIS_PAYMENT)):
        raw = _field(doc, "가입구분")
        category = None
        if raw and _insurance_doc_trusted(doc, complete=False):
            category = {"직장": "직장", "직장가입자": "직장", "지역": "지역", "지역가입자": "지역",
                        "혼합": "혼합", "혼합가입자": "혼합"}.get(re.sub(r"\s+", "", raw))
            unsupported = unsupported or category not in {"직장", "지역"}
            if category:
                explicit.append(category)
        source = _source(doc, doc_type, "가입구분", f"기록된 가입구분 · {category or '모름'}")
        sources["insurance_explicit_" + kind] = source
        evidence["explicit_" + kind] = {"value": raw, "category": category, "source": source.as_dict()}

    cells = [evidence[key]["category"] for key in ("A", "B") if evidence[key]["category"]]
    conflict = len(set(cells + explicit)) > 1
    explicit_conflict = bool(explicit) and len(set(cells + explicit)) > 1
    reasons = []
    if conflict:
        insurance_type = "모름"
        reasons.append("INSURANCE_EXPLICIT_CONFLICT" if explicit_conflict else "INSURANCE_EVIDENCE_CONFLICT")
        issue = "가입구분 근거 또는 기록된 가입구분이 서로 일치하지 않습니다."
    elif unsupported:
        insurance_type = "모름"
        reasons.append("INSURANCE_TYPE_UNSUPPORTED")
        issue = "혼합 또는 지원하지 않는 가입구분은 자동 판정할 수 없습니다."
    elif explicit:
        insurance_type, issue = explicit[0], None
    elif len(cells) == 2:
        insurance_type, issue = cells[0], None
    else:
        insurance_type = "모름"
        reasons.append("INSURANCE_EVIDENCE_INSUFFICIENT")
        issue = "사업장관리번호와 사업장명칭의 일치하는 두 가입구분 근거를 확인하지 못했습니다."
    return insurance_type, evidence, sources, issue, reasons, conflict, explicit_conflict


def _monthly_premium(payment, payment_months):
    if not payment or not _payment_amounts_trusted(payment):
        return None, "납부확인서 판독 또는 명의 확인이 완료되지 않아 보험료 채점 보류", "PREMIUM_UNTRUSTED"
    months = list(DEFAULT_PAYMENT_MONTHS if payment_months is None else payment_months)
    if len(months) != 3 or len(set(months)) != 3:
        return None, "건강보험료 고지금액 판정 대상 석 달을 확인하지 못했습니다.", "PREMIUM_MONTHS_INVALID"
    try:
        monthly = json.loads(_field(payment, "월별고지금액") or "null")
    except (TypeError, ValueError):
        monthly = None
    if not isinstance(monthly, dict) or any(month not in monthly for month in months):
        return None, "판정 대상 석 달의 건강보험료 고지금액이 모두 필요합니다.", "PREMIUM_MONTH_MISSING"
    values = []
    for month in months:
        raw = monthly[month]
        if type(raw) is int and raw >= 0:
            values.append(raw)
        elif isinstance(raw, str) and re.fullmatch(r"(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)", raw.strip()):
            values.append(int(raw.strip().replace(",", "")))
        else:
            return None, "판정 대상 건강보험료 고지금액을 정수 금액으로 신뢰할 수 없습니다.", "PREMIUM_AMOUNT_INVALID"
    return (sum(values) * 2 + len(values)) // (2 * len(values)), None, None


def build_facts(form1: dict[str, Any], documents: list[DocFact], payment_months: list[str] | None = None) -> ScoringFacts:
    """서식1 입력값과 서류 판독 결과에서 채점에 쓸 사실값만 뽑는다."""
    payment = _find(documents, DocType.NHIS_PAYMENT)
    qualification = _find(documents, DocType.NHIS_QUALIFICATION)
    abstract = _find(documents, DocType.RESIDENT_ABSTRACT)
    insurance4 = _find(documents, DocType.INSURANCE_4)

    # --- 1. 소득: 자격확인서만 가구원수 근거로 사용 (R5.2) ---
    qualification_fields = (qualification or {}).get("fields") or {}
    printed_household = parse_int(_field(qualification, "가구원수"))
    household_issue = None
    member_list_present = "가구원목록" in qualification_fields
    members = (
        parse_household_members(qualification_fields.get("가구원목록"))
        if member_list_present else None
    )
    if member_list_present and members is None:
        household = None
        household_issue = "건강보험 자격확인서에서 가구원 수를 확인하지 못했습니다."
    elif members is not None:
        listed_household = len(members)
        if printed_household is not None and printed_household != listed_household:
            household = None
            household_issue = "건강보험 자격확인서 가구원 목록 인원 수와 가구원수 표기가 일치하지 않습니다."
        else:
            household = listed_household
    else:
        household = printed_household
        if household is None:
            household_issue = "건강보험 자격확인서에서 가구원 수를 확인하지 못했습니다."
    if qualification and not _insurance_doc_trusted(qualification, complete=False):
        household = None
        household_issue = "건강보험 자격확인서 판독 또는 명의 확인이 완료되지 않아 가구원 수를 신뢰할 수 없습니다."

    form_household = parse_int(form1.get("householdSize"))
    household_form_mismatch = (
        (form_household, household)
        if form_household is not None and household is not None and form_household != household
        else None
    )
    premium, premium_issue, premium_reason = _monthly_premium(payment, payment_months)
    insurance_type, insurance_evidence, insurance_sources, insurance_issue, insurance_reasons, insurance_conflict, explicit_conflict = (
        _insurance_facts(qualification, payment)
    )

    income_origin = "건강보험료 납부확인서 고지금액 판독 · 가구원수는 건강보험 자격확인서 판독"
    if premium_issue:
        income_origin += " · " + premium_issue
    income_origin += " · " + " · ".join(source.origin for source in insurance_sources.values())
    if insurance_issue:
        income_origin += " · " + insurance_issue
    if household_issue:
        income_origin += " · " + household_issue
    if household_form_mismatch:
        income_origin += (
            f" · 신청서 입력 {household_form_mismatch[0]}명과 자격확인서 "
            f"{household_form_mismatch[1]}명 불일치(신청서 값은 참고만 함)"
        )
    income_source = _source(payment, DocType.NHIS_PAYMENT, "건강보험료", income_origin)

    # --- 2. 거주기간: 초본의 전입일 우선, 없으면 신청서 입력값 ---
    transfer_in = parse_ymd(_field(abstract, "전입일"))
    residence_history_incomplete_suspected = _field(abstract, "주소이력건수") == "1"
    if residence_history_incomplete_suspected:
        residence_origin = "주민등록초본 전입일 판독 · 과거 주소 미포함 의심(주소 이력 1건), 거주기간 담당자 확인 필요"
    else:
        residence_origin = "주민등록초본 전입일 판독"
    if transfer_in is not None:
        residence_source = _source(
            abstract, DocType.RESIDENT_ABSTRACT, "전입일", residence_origin
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
    try:
        birth = parse_ymd(form1.get("birth"))
    except OverflowError:
        birth = None
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
        premium_determinable=premium is not None,
        premium_issue=premium_issue,
        premium_reason_code=premium_reason,
        insurance_evidence=insurance_evidence,
        insurance_issue=insurance_issue,
        insurance_reason_codes=insurance_reasons,
        insurance_conflict=insurance_conflict,
        insurance_explicit_conflict=explicit_conflict,
        transfer_in_date=transfer_in,
        employment_date=employed_at,
        birth_date=birth,
        household_size_issue=household_issue,
        household_size_form_mismatch=household_form_mismatch,
        residence_history_incomplete_suspected=residence_history_incomplete_suspected,
        sources={
            **insurance_sources,
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


#: 읍·면·동 토큰. 주소 문자열의 세 번째 행정단위에 해당한다.
_TOWN_SUFFIXES = ("읍", "면", "동")


def extract_town(address: str, region: str = "") -> str:
    """주소 문자열에서 읍·면·동을 뽑는다.

    담당자 역할 중 **읍면동**은 관할 접수 건만 봐야 한다(시행지침 선발절차 2단계).
    시군까지만 알아서는 그 범위를 만들 수 없어 한 단계 더 내려간다.

    구(區)가 있는 시(전주시 완산구 효자동)에서는 '구'를 건너뛰고 '동'을 잡는다.
    데모 범위라 토큰 검사로 충분하다 — 실서비스는 도로명주소 API를 쓸 자리다.
    """
    tail = (address or "").strip()
    if region and region in tail:
        tail = tail.split(region, 1)[1]
    tokens = tail.split()

    for token in tokens:
        if len(token) >= 2 and token.endswith(_TOWN_SUFFIXES):
            return token

    # "효자동3가"처럼 뒤에 무언가 더 붙는 표기. 위 규칙으로 못 잡았을 때만 쓴다
    # ("중동로"처럼 도로명을 읍면동으로 오인할 수 있어 마지막 수단으로 둔다).
    for token in tokens:
        for suffix in _TOWN_SUFFIXES:
            head, sep, _ = token.partition(suffix)
            if sep and head and not head.endswith(("시", "군", "구")):
                return head + suffix
    return ""

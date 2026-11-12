"""심사표 100점 채점 (시행지침 서식6).

엔진에는 점수 계산 기능이 **없다**(E9). 엔진 수정 일정에 데모가 종속되면 안 되므로
데모가 들고 있되, 나중에 `engine/stage3_scoring.py`로 그대로 옮길 수 있게 **순수
함수**로 작성한다. 이 모듈은 DB·FastAPI·파일시스템을 일절 모른다.

이 설계의 핵심은 항목마다 `basis`(근거 문장) + `source_doc` + `bbox`를 같이 담는
것이다. "소득분위 초과"라고만 쓰면 담당자는 결국 원본을 뒤진다. 근거 문장과 좌표를
함께 넘기면 눈으로 3초 안에 검증된다 (R4.3).

배점 출처: `docs/demo-site-dev-plan.md` 2.4절 (시행지침 서식6 원문 대조 확정본)
"""

from dataclasses import dataclass, field, replace
from datetime import date

from .doc_types import DocType

#: 심사표 총점.
MAX_TOTAL = 100

#: 미확정 가정값 라벨. 코드와 화면 양쪽에 같은 문자열을 쓴다.
ESTIMATE_LABEL = "(데모 추정치)"

#: 중위소득 140% 판정 상한 — 노인장기요양보험료 제외.
#: 1~10인 모두 공고문 공식 값 (사용자 확인).
MEDIAN_INCOME_140: dict[int, dict[str, int]] = {
    1: {"직장": 118_821, "지역": 46_072},
    2: {"직장": 196_177, "지역": 133_680, "혼합": 198_905},
    3: {"직장": 252_203, "지역": 196_416, "혼합": 256_716},
    4: {"직장": 311_031, "지역": 269_976, "혼합": 320_322},
    5: {"직장": 354_964, "지역": 320_449, "혼합": 369_517},
    6: {"직장": 407_092, "지역": 382_076, "혼합": 431_294},
    7: {"직장": 461_699, "지역": 447_279, "혼합": 506_004},
    8: {"직장": 506_004, "지역": 496_008, "혼합": 552_230},
    9: {"직장": 552_230, "지역": 545_971, "혼합": 599_810},
    10: {"직장": 599_810, "지역": 591_277, "혼합": 673_463},
}

#: 공식 기준표 최대 가구원수. 11인 이상은 소득 판정 불가다.
MAX_SUPPORTED_HOUSEHOLD = max(MEDIAN_INCOME_140)
OFFICIAL_NOTICE_MAX_HOUSEHOLD = MAX_SUPPORTED_HOUSEHOLD

#: 신청 자격 상한. 이 값을 넘으면 점수와 무관하게 부적합이다.
INCOME_LIMIT_PERCENT = 140.0

#: 공개 기준표의 가입구분. 혼합 상한은 초과 확정 경계에만 쓰며 가입구분으로 선택하지 않는다.
INSURANCE_TYPES = ("직장", "지역", "혼합")

#: 항목 1. 중위소득 — (하한 %, 점수). 위에서부터 먼저 걸리는 구간을 쓴다.
INCOME_BANDS: list[tuple[float, int, str]] = [
    (130.0, 28, "130% 이상"),
    (120.0, 31, "120% 이상 ~ 130% 미만"),
    (110.0, 34, "110% 이상 ~ 120% 미만"),
    (100.0, 37, "100% 이상 ~ 110% 미만"),
    (0.0, 40, "100% 미만"),
]

#: 항목 2. 도 거주기간 — 만 경과 연수 → (점수, 구간 라벨). 서식1의 6구간과 같다.
RESIDENCE_BANDS: list[tuple[int, str]] = [
    (15, "1년 미만"),
    (17, "1년 이상 ~ 2년 미만"),
    (19, "2년 이상 ~ 3년 미만"),
    (21, "3년 이상 ~ 4년 미만"),
    (23, "4년 이상 ~ 5년 미만"),
    (25, "5년 이상"),
]

#: 항목 3. 현직장 근로기간 — 서식1의 4구간과 같다.
WORK_BANDS: list[tuple[int, str]] = [
    (16, "1년 미만"),
    (19, "1년 이상 ~ 2년 미만"),
    (22, "2년 이상 ~ 3년 미만"),
    (25, "3년 이상"),
]

#: 항목 4. 연령 — (상한 만나이, 점수, 구간 라벨).
AGE_BANDS: list[tuple[int, int, str]] = [
    (24, 10, "24세 이하"),
    (29, 9, "25~29세"),
    (34, 8, "30~34세"),
    (200, 7, "35세 이상"),
]


# ---------------------------------------------------------------- 입력 스키마


@dataclass(frozen=True)
class FactSource:
    """값을 어디서 가져왔는지.

    담당자 화면이 "이 점수는 어느 서류의 어디를 보고 나온 것인가"를 되짚는 데 쓴다.
    """

    #: 근거 서류 종류. 신청서 입력값이면 None.
    doc_type: DocType | None = None
    #: 근거 서류의 DB id. `/api/files/{id}` 로 원본을 연다.
    document_id: int | None = None
    #: 원본에서의 위치 {page, x0, y0, x1, y1}. 없으면 None.
    bbox: dict[str, float | int] | None = None
    #: "건강보험 자격확인서 판독" / "신청서 입력값" 등 사람이 읽는 출처 표기.
    origin: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "doc_type": str(self.doc_type) if self.doc_type else None,
            "document_id": self.document_id,
            "bbox": self.bbox,
            "origin": self.origin,
        }


@dataclass
class ScoringFacts:
    """채점에 필요한 사실값만 모은 것.

    어디서 왔는지(OCR/입력)는 `sources`가 따로 들고 있다. 채점 로직은 값만 본다.
    """

    household_size: int | None = None
    #: '25.10~12월 **고지금액** 평균. 실납부액이 아니다 (R5.2).
    monthly_premium: int | None = None
    insurance_type: str = "모름"
    #: None supports callers supplying already established pure facts directly.
    premium_determinable: bool | None = None
    premium_issue: str | None = None
    premium_reason_code: str | None = None
    insurance_evidence: dict[str, dict[str, object]] = field(default_factory=dict)
    insurance_issue: str | None = None
    insurance_reason_codes: list[str] = field(default_factory=list)
    insurance_conflict: bool = False
    insurance_explicit_conflict: bool = False
    transfer_in_date: date | None = None
    employment_date: date | None = None
    birth_date: date | None = None
    #: 소득 가구원수 판독 실패 또는 자격확인서 내부 표기 불일치 사유.
    household_size_issue: str | None = None
    #: (신청서 입력값, 건강보험 자격확인서 값). 계산에는 자격확인서만 사용한다.
    household_size_form_mismatch: tuple[int, int] | None = None
    residence_history_incomplete_suspected: bool = False
    sources: dict[str, FactSource] = field(default_factory=dict)

    def source(self, key: str) -> FactSource:
        return self.sources.get(key, FactSource())


# ---------------------------------------------------------------- 출력 스키마


@dataclass
class ScoreItem:
    """심사표 한 줄. 담당자 화면이 서식6 레이아웃으로 그대로 렌더한다 (R8.7)."""

    key: str
    label: str
    score: int
    max_score: int
    #: 선택된 구간 라벨 ("4년 이상 ~ 5년 미만").
    band: str
    #: 왜 그 구간인지 한 문장. 담당자가 원본과 대조하는 근거다.
    basis: str
    source: FactSource = field(default_factory=FactSource)
    #: 값이 없어 채점하지 못한 항목. 담당자 확인 대상이다.
    incomplete: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "label": self.label,
            "score": self.score,
            "max_score": self.max_score,
            "band": self.band,
            "basis": self.basis,
            "source_doc": str(self.source.doc_type) if self.source.doc_type else None,
            "source_document_id": self.source.document_id,
            "bbox": self.source.bbox,
            "source_origin": self.source.origin,
            "incomplete": self.incomplete,
        }


@dataclass
class ScoreSheet:
    items: list[ScoreItem]
    total: int
    max_total: int = MAX_TOTAL
    #: 가구 중위소득 대비 비율(%). 판정 불가 시 None.
    income_percent: float | None = None
    #: 140% 초과 여부. 초과면 점수와 무관하게 자격 부적합이다.
    income_over_limit: bool = False
    income_status: str = "UNDETERMINED"
    income_reason_codes: list[str] = field(default_factory=list)
    #: 동점자 정렬 키 (시행지침 우선순위 ①~④).
    tiebreak: list[float] = field(default_factory=list)
    #: 화면에 그대로 띄우는 주의 문구. `(데모 추정치)` 라벨이 여기에 들어간다.
    notes: list[str] = field(default_factory=list)

    @property
    def incomplete(self) -> bool:
        return any(i.incomplete for i in self.items)

    def as_dict(self) -> dict[str, object]:
        return {
            "items": [i.as_dict() for i in self.items],
            "total": self.total,
            "max_total": self.max_total,
            "income_percent": self.income_percent,
            "income_over_limit": self.income_over_limit,
            "income_status": self.income_status,
            "income_reason_codes": self.income_reason_codes,
            "incomplete": self.incomplete,
            "tiebreak": self.tiebreak,
            "notes": self.notes,
        }


@dataclass
class IncomeScoreResult:
    """Authoritative eligibility plus the existing four scoring return values."""

    item: ScoreItem
    percent: float | None
    over_limit: bool
    notes: list[str]
    status: str
    reason_codes: list[str]

    def __iter__(self):
        return iter((self.item, self.percent, self.over_limit, self.notes))

    def __getitem__(self, index):
        return (self.item, self.percent, self.over_limit, self.notes)[index]

    def __len__(self):
        return 4


# ---------------------------------------------------------------- 계산 도우미


def elapsed_years_months(start: date, end: date) -> tuple[int, int]:
    """`start`부터 `end`까지 만 경과 연·월.

    프론트 `lib/period.ts`의 자동 구간 판정과 같은 규칙이어야 한다. 신청 화면에서
    "4년 이상 ~ 5년 미만"으로 보여주고 채점은 5년으로 하면 곧바로 민원이 된다.
    """
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day < start.day:
        months -= 1
    return months // 12, months % 12


def korean_age_at(birth: date, basis: date) -> int:
    """기준일의 만나이."""
    age = basis.year - birth.year
    if (basis.month, basis.day) < (birth.month, birth.day):
        age -= 1
    return age


def premium_limit_140(household_size: int, insurance_type: str) -> tuple[int, str]:
    """가구원수·가입구분별 140% 건보료 상한과 주석."""
    if type(household_size) is not int or household_size not in MEDIAN_INCOME_140:
        raise ValueError("공식 소득 기준표는 1~10인 가구만 지원합니다.")
    size = household_size
    row = MEDIAN_INCOME_140[size]
    if insurance_type in row:
        return row[insurance_type], ""
    # Preserve the public informational helper's historical one-person lookup.
    # Eligibility never selects this fallback or a mixed limit.
    if size == 1 and insurance_type == "혼합":
        return row["직장"], f"{ESTIMATE_LABEL} 1인 혼합 기준이 없어 참고 환산에 직장 기준을 적용했습니다."
    raise ValueError("해당 가입구분의 공식 소득 기준값이 없습니다.")


def income_percent(
    household_size: int, monthly_premium: int, insurance_type: str
) -> tuple[float, int, str]:
    """건보료 고지금액 → 가구 중위소득 비율(%).

    공고문은 **140% 표만** 제공한다. 심사표는 100/110/120/130% 구간을 요구하므로
    140% 값을 선형 환산해 100% 기준선을 만든다. 이 환산값은 확정 자료가 아니므로
    반환 주석에 `(데모 추정치)` 라벨을 붙인다 (Open Question 1).
    """
    limit_140, note = premium_limit_140(household_size, insurance_type)
    base_100 = limit_140 / (INCOME_LIMIT_PERCENT / 100)
    return monthly_premium / base_100 * 100, round(base_100), note


# ---------------------------------------------------------------- 항목별 채점


def _missing(key: str, label: str, max_score: int, what: str, source: FactSource) -> ScoreItem:
    return ScoreItem(
        key=key,
        label=label,
        score=0,
        max_score=max_score,
        band="판정 불가",
        basis=f"{what}을(를) 확인할 수 없어 0점 처리했습니다. 담당자 확인이 필요합니다.",
        source=source,
        incomplete=True,
    )


def score_income(facts: ScoringFacts) -> IncomeScoreResult:
    """1. 중위소득: 정수 상한으로 자격을 정하고 별도로 점수 구간을 환산한다."""
    source = facts.source("income")
    notes = []
    if facts.household_size_form_mismatch:
        form_count, certificate_count = facts.household_size_form_mismatch
        notes.append(
            f"신청서 입력 가구원수 {form_count}명과 건강보험 자격확인서 "
            f"가구원수 {certificate_count}명이 다릅니다. 판정에는 자격확인서 값을 사용했습니다."
        )
    details, reasons = [], []
    size, premium = facts.household_size, facts.monthly_premium
    if facts.household_size_issue or type(size) is not int or size < 1:
        details.append(facts.household_size_issue or "건강보험 자격확인서 가구원 수를 확인하지 못했습니다.")
        reasons.append("HOUSEHOLD_SIZE_UNCONFIRMED")
    elif size not in MEDIAN_INCOME_140:
        details.append("11인 이상 가구는 공식 소득 기준표가 없어 자동 판정할 수 없습니다.")
        reasons.append("HOUSEHOLD_SIZE_UNSUPPORTED")
    if (facts.premium_determinable is False or facts.premium_issue or
            type(premium) is not int or premium < 0):
        details.append(facts.premium_issue or "판정 대상 석 달의 신뢰할 수 있는 건강보험료 고지금액이 필요합니다.")
        reasons.append(facts.premium_reason_code or "PREMIUM_AMOUNT_UNCONFIRMED")
    if facts.insurance_explicit_conflict:
        details.append(facts.insurance_issue or "기록된 가입구분이 다른 가입구분 근거와 일치하지 않습니다.")
        reasons.append("INSURANCE_EXPLICIT_CONFLICT")
    if details:
        item = _missing("income", "중위소득(가구소득)", 40, "소득 요건 판정 근거", source)
        item.basis = " ".join(details) + " 담당자 재검토가 필요합니다."
        return IncomeScoreResult(item, None, False, notes + details, "UNDETERMINED", reasons)

    row = MEDIAN_INCOME_140[size]
    minimum, maximum = min(row["직장"], row["지역"]), max(row["직장"], row["지역"])
    category = facts.insurance_type if facts.insurance_type in {"직장", "지역"} else None
    if premium <= minimum:
        over = False
        reason = "INCOME_AT_OR_BELOW_BOTH_LIMITS"
        decision = f"직장·지역 두 상한 중 낮은 {minimum:,}원 이하 → 소득 요건 충족"
    elif premium > max(row.values()):
        over = True
        reason = "INCOME_ABOVE_ALL_LIMITS" if "혼합" in row else "INCOME_ABOVE_BOTH_LIMITS"
        limits_label = "직장·지역·혼합 모든 상한" if "혼합" in row else "직장·지역 두 상한"
        decision = f"{limits_label} 중 높은 {max(row.values()):,}원 초과 → 140% 초과 확정"
    elif premium > maximum:
        item = _missing("income", "중위소득(가구소득)", 40, "혼합 가구 여부와 적용 규칙", source)
        item.basis = (
            f"{size}인 가구의 혼합 가구 여부를 확정할 수 없습니다. "
            f"고지금액 평균 {premium:,}원은 직장·지역 상한 중 높은 {maximum:,}원을 넘지만 "
            f"혼합 상한 {row['혼합']:,}원 이하입니다. "
            "혼합 가구 식별과 적용 규칙이 미확정이므로 초과로 확정하지 않고 담당자 재검토가 필요합니다."
        )
        return IncomeScoreResult(item, None, False, notes + [item.basis],
                                 "UNDETERMINED", ["INCOME_MIXED_POSSIBLE"])
    elif category is not None:
        limit = row[category]
        over = premium > limit
        reason = "INCOME_ABOVE_CATEGORY_LIMIT" if over else "INCOME_AT_OR_BELOW_CATEGORY_LIMIT"
        decision = f"확정된 {category} 상한 {limit:,}원 " + ("초과 → 140% 초과 확정" if over else "이하 → 소득 요건 충족")
    else:
        item = _missing("income", "중위소득(가구소득)", 40, "일치하는 가입구분 근거", source)
        item.basis = (
            f"{size}인 가구 고지금액 평균 {premium:,}원은 직장·지역 상한 "
            f"{minimum:,}원과 {maximum:,}원 사이입니다. "
            + (facts.insurance_issue or "가입구분을 확정하지 못했습니다.")
            + " 담당자 재검토가 필요합니다."
        )
        reasons = facts.insurance_reason_codes or ["INSURANCE_EVIDENCE_INSUFFICIENT"]
        return IncomeScoreResult(item, None, False, notes + [item.basis], "UNDETERMINED", list(reasons))

    # Unknown membership does not prevent a category-independent eligibility
    # decision. Its score estimate uses a disclosed reference row, not a category fact.
    reference = category
    if reference is None:
        reference = min(("직장", "지역"), key=lambda key: row[key]) if not over else max(
            ("직장", "지역"), key=lambda key: row[key])
        notes.append(
            f"{ESTIMATE_LABEL} 가입구분 미확정: 점수 구간만 {reference} 기준표로 임시 환산했습니다. "
            + ("소득 요건은 직장·지역·혼합 모든 상한 비교로 확정했습니다."
               if over and "혼합" in row else "소득 요건은 직장·지역 두 상한 비교로 확정했습니다.")
        )
    percent, base_100, note = income_percent(size, premium, reference)
    score, band = next((score, band) for lower, score, band in INCOME_BANDS if percent >= lower)
    membership = f"{category}가입자" if category else "가입구분 미확정"
    basis = (
        f"{size}인 가구 {membership}, 고지금액 평균 {premium:,}원 · {decision} · "
        f"100% 기준 {base_100:,}원으로 점수 환산 {percent:.1f}% → {band}"
    )
    evidence = []
    for key, label in (("A", "사업장관리번호"), ("B", "사업장명칭")):
        record = facts.insurance_evidence.get(key)
        if record:
            evidence.append(f"{label} {record.get('state', '못 읽음')}({record.get('category') or '모름'})")
    for key in ("explicit_qualification", "explicit_payment"):
        record = facts.insurance_evidence.get(key)
        if record and record.get("category"):
            evidence.append(f"기록된 가입구분 {record['category']}")
    if evidence:
        basis += " · " + " · ".join(evidence)
    notes.append(
        f"{ESTIMATE_LABEL} 100% 기준선은 공고문 140% 기준표를 선형 환산한 값입니다. "
        "TF에서 원표를 확보하면 상수 표만 교체합니다."
    )
    if note:
        notes.append(note)
    item = ScoreItem("income", "중위소득(가구소득)", score, 40, band, basis, source)
    return IncomeScoreResult(item, round(percent, 1), over, notes, "OVER_LIMIT" if over else "MET", [reason])


def score_residence(facts: ScoringFacts, basis_date: date) -> ScoreItem:
    """2. 도 거주기간 (25점). 최종 전입일 → 공고일 역산."""
    source = facts.source("residence")
    if facts.residence_history_incomplete_suspected:
        source = replace(
            source,
            origin=(source.origin + " · 과거 주소 미포함 의심(주소 이력 1건), 거주기간 담당자 확인 필요").strip(" ·"),
        )
    start = facts.transfer_in_date
    if start is None or start > basis_date:
        return _missing("residence", "도 거주기간", 25, "전북특별자치도 최종 전입일", source)

    years, months = elapsed_years_months(start, basis_date)
    index = min(years, len(RESIDENCE_BANDS) - 1)
    score, band = RESIDENCE_BANDS[index]
    return ScoreItem(
        key="residence",
        label="도 거주기간",
        score=score,
        max_score=25,
        band=band,
        basis=(
            f"{start.isoformat()} 전입 → 공고일({basis_date.isoformat()})까지 "
            f"{years}년 {months}개월 → {band}"
            + (" · 과거 주소 미포함 의심, 거주기간 담당자 확인 필요" if facts.residence_history_incomplete_suspected else "")
        ),
        source=source,
    )


def score_work(facts: ScoringFacts, basis_date: date) -> ScoreItem:
    """3. 근로기간 (25점). 현직장 취업일 → 공고일 역산."""
    source = facts.source("work")
    start = facts.employment_date
    if start is None or start > basis_date:
        return _missing("work", "근로기간(현 직장)", 25, "현 직장 취업일", source)

    years, months = elapsed_years_months(start, basis_date)
    index = min(years, len(WORK_BANDS) - 1)
    score, band = WORK_BANDS[index]
    return ScoreItem(
        key="work",
        label="근로기간(현 직장)",
        score=score,
        max_score=25,
        band=band,
        basis=(
            f"{start.isoformat()} 취업 → 공고일({basis_date.isoformat()})까지 "
            f"{years}년 {months}개월 → {band}"
        ),
        source=source,
    )


def score_age(facts: ScoringFacts, age_basis_date: date) -> ScoreItem:
    """4. 신청자 연령 (10점). 2025-12-31 기준 만나이."""
    source = facts.source("age")
    birth = facts.birth_date
    if birth is None:
        return _missing("age", "신청자 연령", 10, "생년월일", source)

    age = korean_age_at(birth, age_basis_date)
    score, band = next(
        ((s, b) for upper, s, b in AGE_BANDS if age <= upper),
        AGE_BANDS[-1][1:],
    )
    return ScoreItem(
        key="age",
        label="신청자 연령",
        score=score,
        max_score=10,
        band=band,
        basis=(
            f"{birth.isoformat()} 출생 → {age_basis_date.isoformat()} 기준 만 {age}세 → {band}"
        ),
        source=source,
    )


# ---------------------------------------------------------------- 진입점


def score_application(
    facts: ScoringFacts,
    *,
    announcement_date: date,
    age_basis_date: date,
) -> ScoreSheet:
    """심사표 100점 채점.

    `announcement_date`(거주·근로 역산 기준)와 `age_basis_date`(연령 기준)를 사업
    설정에서 주입받는다. 두 날짜가 다르다 — 두배적금은 공고일 2026-03-03,
    연령은 2025-12-31 기준이다.
    """
    income = score_income(facts)
    income_item, percent, over_limit, notes = income
    items = [
        income_item,
        score_residence(facts, announcement_date),
        score_work(facts, announcement_date),
        score_age(facts, age_basis_date),
    ]
    total = sum(i.score for i in items)
    sheet = ScoreSheet(
        items=items,
        total=total,
        income_percent=percent,
        income_over_limit=over_limit,
        income_status=income.status,
        income_reason_codes=income.reason_codes,
        notes=notes,
    )
    sheet.tiebreak = tiebreak_key(sheet, facts, announcement_date)
    return sheet


def tiebreak_key(
    sheet: ScoreSheet, facts: ScoringFacts, basis_date: date
) -> list[float]:
    """동점자 정렬 키 (시행지침 '26년 기준).

    ① 가구소득이 적은 자 ② 도 거주기간이 긴 자 ③ 근로기간이 긴 자 ④ 연령이 낮은 자.
    오름차순 정렬하면 그대로 순위가 된다 — 큰 값이 유리한 항목은 부호를 뒤집는다.
    ('25년 순서와 다르므로 그대로 옮겨 쓰면 안 된다.)
    """
    residence_days = (
        (basis_date - facts.transfer_in_date).days if facts.transfer_in_date else 0
    )
    work_days = (
        (basis_date - facts.employment_date).days if facts.employment_date else 0
    )
    # 연령이 낮을수록 유리 = 생년월일이 늦을수록 유리.
    birth_ordinal = facts.birth_date.toordinal() if facts.birth_date else 0
    return [
        -sheet.total,
        float(sheet.income_percent if sheet.income_percent is not None else 999.0),
        -residence_days,
        -work_days,
        -birth_ordinal,
    ]

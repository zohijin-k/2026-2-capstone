"""심사표 100점 채점 (시행지침 서식6).

엔진에는 점수 계산 기능이 **없다**(E9). 엔진 수정 일정에 데모가 종속되면 안 되므로
데모가 들고 있되, 나중에 `engine/stage3_scoring.py`로 그대로 옮길 수 있게 **순수
함수**로 작성한다. 이 모듈은 DB·FastAPI·파일시스템을 일절 모른다.

이 설계의 핵심은 항목마다 `basis`(근거 문장) + `source_doc` + `bbox`를 같이 담는
것이다. "소득분위 초과"라고만 쓰면 담당자는 결국 원본을 뒤진다. 근거 문장과 좌표를
함께 넘기면 눈으로 3초 안에 검증된다 (R4.3).

배점 출처: `docs/demo-site-dev-plan.md` 2.4절 (시행지침 서식6 원문 대조 확정본)
"""

from dataclasses import dataclass, field
from datetime import date

from .doc_types import DocType

#: 심사표 총점.
MAX_TOTAL = 100

#: 미확정 가정값 라벨. 코드와 화면 양쪽에 같은 문자열을 쓴다.
ESTIMATE_LABEL = "(데모 추정치)"

#: 중위소득 140% 판정 기준표 — 2025년, 노인장기요양보험료 제외 (공고문 제2026-443호).
#: 가구원수 → 가입구분별 월 건강보험료 상한.
MEDIAN_INCOME_140: dict[int, dict[str, int]] = {
    1: {"직장": 118_821, "지역": 46_072},
    2: {"직장": 196_177, "지역": 133_680, "혼합": 198_905},
    3: {"직장": 252_203, "지역": 196_416, "혼합": 256_716},
    4: {"직장": 311_031, "지역": 269_976, "혼합": 320_322},
    5: {"직장": 354_964, "지역": 320_449, "혼합": 369_517},
    6: {"직장": 407_092, "지역": 382_076, "혼합": 431_294},
    7: {"직장": 461_699, "지역": 447_279, "혼합": 506_004},
}

#: 표에 있는 최대 가구원수. 그 이상은 이 값을 적용한다.
MAX_TABLE_HOUSEHOLD = max(MEDIAN_INCOME_140)

#: 신청 자격 상한. 이 값을 넘으면 점수와 무관하게 부적합이다.
INCOME_LIMIT_PERCENT = 140.0

#: 가입구분 표기. 건강보험 자격확인서의 직장가입자 칸 기재 여부로 갈린다.
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
    insurance_type: str = "직장"
    transfer_in_date: date | None = None
    employment_date: date | None = None
    birth_date: date | None = None
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
            "incomplete": self.incomplete,
            "tiebreak": self.tiebreak,
            "notes": self.notes,
        }


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
    note = ""
    size = household_size
    if size > MAX_TABLE_HOUSEHOLD:
        size = MAX_TABLE_HOUSEHOLD
        note = (
            f"{ESTIMATE_LABEL} 공고문 기준표는 7인까지만 제공되어 "
            f"{household_size}인 가구에 7인 기준을 적용했습니다."
        )
    size = max(1, size)
    row = MEDIAN_INCOME_140[size]
    if insurance_type in row:
        return row[insurance_type], note
    # 1인 가구에는 혼합 값이 없다. 직장 기준으로 대체하고 그 사실을 남긴다.
    fallback = row.get("직장") or next(iter(row.values()))
    extra = (
        f"{ESTIMATE_LABEL} {size}인 가구의 '{insurance_type}' 기준값이 공고문 표에 "
        "없어 직장가입자 기준을 적용했습니다."
    )
    return fallback, " ".join(x for x in (note, extra) if x)


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


def score_income(facts: ScoringFacts) -> tuple[ScoreItem, float | None, bool, list[str]]:
    """1. 중위소득 (40점). 가구원수 + '25.10~12월 고지금액 평균으로 판정한다."""
    source = facts.source("income")
    if not facts.household_size or not facts.monthly_premium:
        return (
            _missing("income", "중위소득(가구소득)", 40, "가구원수 또는 건강보험료 고지금액", source),
            None,
            False,
            [],
        )

    insurance_type = facts.insurance_type if facts.insurance_type in INSURANCE_TYPES else "직장"
    percent, base_100, note = income_percent(
        facts.household_size, facts.monthly_premium, insurance_type
    )
    score, band = next(
        (s, b) for lower, s, b in INCOME_BANDS if percent >= lower
    )
    over = percent > INCOME_LIMIT_PERCENT
    basis = (
        f"{facts.household_size}인 가구 {insurance_type}가입자, 고지금액 평균 "
        f"{facts.monthly_premium:,}원 ÷ 100% 기준 {base_100:,}원 = 중위소득 "
        f"{percent:.1f}% → {band}"
    )
    if over:
        basis += f" · 신청 상한 {INCOME_LIMIT_PERCENT:.0f}% 초과"
    notes = [
        f"{ESTIMATE_LABEL} 100% 기준선은 공고문 140% 기준표를 선형 환산한 값입니다. "
        "TF에서 원표를 확보하면 상수 표만 교체합니다."
    ]
    if note:
        notes.append(note)
    return (
        ScoreItem(
            key="income",
            label="중위소득(가구소득)",
            score=score,
            max_score=40,
            band=band,
            basis=basis,
            source=source,
        ),
        round(percent, 1),
        over,
        notes,
    )


def score_residence(facts: ScoringFacts, basis_date: date) -> ScoreItem:
    """2. 도 거주기간 (25점). 최종 전입일 → 공고일 역산."""
    source = facts.source("residence")
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
    score, band = next((s, b) for upper, s, b in AGE_BANDS if age <= upper)
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
    income_item, percent, over_limit, notes = score_income(facts)
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

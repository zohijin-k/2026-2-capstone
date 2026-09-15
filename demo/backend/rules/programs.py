"""사업별 상수.

두배적금과 취업지원패키지는 선발 방식·보완 정책·연령 기준·서류 인정일이 전부
다르다. 분기가 코드 전체에 흩어지지 않게 여기 한 곳에 모은다. 화면도 규칙도
"사업 코드가 무엇인가"로 갈라지지 않고, 이 구조체의 값을 읽어 동작한다.

값의 출처:
  - 두배적금: 공고문 제2026-443호, '26년 시행지침
  - 취업지원패키지: 2026년 전북청년 취업지원패키지 사업계획서
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Literal

DOUBLE_SAVINGS = "double_savings"
JOB_PACKAGE = "job_package"


@dataclass(frozen=True)
class ProgramConfig:
    code: str
    name: str
    #: 거주기간·근로기간 역산 기준일
    announcement_date: date
    #: 이 날짜 '이후' 발급분만 인정
    document_cutoff: date
    #: 연령 계산 기준일
    age_basis_date: date
    #: 신청 가능 출생일 범위 (포함)
    birth_range: tuple[date, date]
    selection: Literal["scored", "first_come"]
    #: 서류 보완 허용 일수. None이면 보완 불가.
    supplement_days: int | None
    has_income_requirement: bool
    apply_period: tuple[date, date]
    quota_by_region: dict[str, int] | None = None
    #: 선착순 사업의 총 지원 건수. 점수제 사업은 시군별 정원을 쓴다.
    total_quota: int | None = None
    #: 근로요건(계속 근로 중)이 자격요건에 있는가. 근로확인서류·근로기간 배점의 전제다.
    has_work_requirement: bool = True
    #: 지원 항목을 복수로 골라 실비를 정산하는 사업인가.
    has_subsidy_items: bool = False
    #: 제출 전에 비어 있으면 안 되는 신청서 항목 (키, 화면 표기).
    required_form_fields: tuple[tuple[str, str], ...] = ()
    #: 최종 확인 화면의 입력값 요약 순서. "account"는 은행·계좌·예금주를 한 줄로 묶는다.
    summary_fields: tuple[tuple[str, str], ...] = ()
    #: 받아야 하는 동의 종류. 사업마다 서식이 다르다.
    consent_types: tuple[str, ...] = ()
    #: 신청 홈페이지
    site_url: str = ""
    #: 전담 콜센터
    call_center: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def allows_supplement(self) -> bool:
        return self.supplement_days is not None

    @property
    def is_first_come(self) -> bool:
        return self.selection == "first_come"

    @property
    def target_regions(self) -> list[str]:
        """신청 가능 시군.

        시군별 정원이 있는 사업은 그 키가 곧 대상 지역이고, 정원을 시군으로 나누지
        않는 사업(취업패키지)은 도내 14개 시군 전체가 대상이다. 이 값이 비면 엔진
        2단계가 주소를 도외로 보고 전건을 부적합으로 떨어뜨린다.
        """
        return list(self.quota_by_region or JEONBUK_REGIONS)

    @property
    def quota_total(self) -> int | None:
        if self.total_quota is not None:
            return self.total_quota
        if self.quota_by_region:
            return sum(self.quota_by_region.values())
        return None


#: 전북특별자치도 14개 시군. 두 사업 모두 이 안에 주민등록이 있어야 한다.
JEONBUK_REGIONS: list[str] = [
    "전주시",
    "군산시",
    "익산시",
    "정읍시",
    "남원시",
    "김제시",
    "완주군",
    "진안군",
    "무주군",
    "장수군",
    "임실군",
    "순창군",
    "고창군",
    "부안군",
]

# 시행지침 '26년 지원대상자 모집 — 시군별 배정 인원 (총 1,300명)
DOUBLE_SAVINGS_QUOTA: dict[str, int] = {
    "전주시": 550,
    "군산시": 180,
    "익산시": 200,
    "정읍시": 75,
    "남원시": 50,
    "김제시": 50,
    "완주군": 60,
    "진안군": 15,
    "무주군": 15,
    "장수군": 15,
    "임실군": 15,
    "순창군": 15,
    "고창군": 30,
    "부안군": 30,
}

#: 서식1(참여신청서)에서 비어 있으면 제출할 수 없는 항목. 라벨은 서식 원문 표기.
DOUBLE_SAVINGS_REQUIRED_FIELDS: tuple[tuple[str, str], ...] = (
    ("name", "신청자 이름"),
    ("birth", "생년월일"),
    ("address", "주소"),
    ("mobile", "연락처(휴대전화)"),
    ("transferIn", "전북특별자치도 최종 전입일"),
    ("householdSize", "가구원 수"),
    ("employedAt", "현 직장 취업일"),
    ("bankName", "입금 받을 계좌 — 은행명"),
    ("accountNo", "입금 받을 계좌 — 계좌번호"),
)

#: 취업지원패키지 신청서. 사업계획서에 서식 원본이 없어 항목을 데모가 정했다.
#: 소득·거주기간·근로기간을 묻지 않는다 — 자격요건이 나이와 거주지뿐이기 때문이다.
JOB_PACKAGE_REQUIRED_FIELDS: tuple[tuple[str, str], ...] = (
    ("name", "신청자 이름"),
    ("birth", "생년월일"),
    ("address", "주소"),
    ("mobile", "연락처(휴대전화)"),
    ("bankName", "입금 받을 계좌 — 은행명"),
    ("accountNo", "입금 받을 계좌 — 계좌번호"),
    ("accountHolder", "입금 받을 계좌 — 예금주(본인 명의)"),
)

PROGRAMS: dict[str, ProgramConfig] = {
    DOUBLE_SAVINGS: ProgramConfig(
        code=DOUBLE_SAVINGS,
        name="전북청년 함께 두배적금",
        announcement_date=date(2026, 3, 3),
        # 공고문: "모든 서류는 공고일('26. 3. 3.) 이후 발급분에 한해 인정"
        document_cutoff=date(2026, 3, 3),
        age_basis_date=date(2025, 12, 31),
        birth_range=(date(1986, 1, 1), date(2007, 12, 31)),
        selection="scored",
        # 공고문: "서류 미비가 있는 경우 별도 추가(보충)서류를 요청하지 않고 선발에서 제외"
        supplement_days=None,
        has_income_requirement=True,
        apply_period=(date(2026, 3, 3), date(2026, 3, 16)),
        quota_by_region=DOUBLE_SAVINGS_QUOTA,
        has_work_requirement=True,
        has_subsidy_items=False,
        required_form_fields=DOUBLE_SAVINGS_REQUIRED_FIELDS,
        summary_fields=(
            ("name", "신청자 이름"),
            ("birth", "생년월일"),
            ("gender", "성별"),
            ("address", "주소"),
            ("mobile", "연락처"),
            ("transferIn", "최종 전입일"),
            ("householdType", "가구 특성"),
            ("householdSize", "가구원 수"),
            ("workType", "근로유형"),
            ("employedAt", "현 직장 취업일"),
            ("workplaceName", "근무처"),
            ("savingPurpose", "저축목적"),
            ("account", "입금 받을 계좌"),
        ),
        consent_types=("privacy", "unique_id", "third_party", "admin_info"),
        site_url="https://double.jb2030.or.kr",
        call_center="1660-2040",
        notes=[
            "선착순이 아니며, 신청기간 내 24시간 신청 가능",
            "서류 미비(누락·식별 불가) 시 보완 요청 없이 선발 제외",
            "평가결과는 공개하지 않음",
        ],
    ),
    JOB_PACKAGE: ProgramConfig(
        code=JOB_PACKAGE,
        name="전북청년 취업지원패키지",
        # 취업패키지는 기간 역산 항목이 없다. 1차 신청 시작일을 기준일로 둔다.
        announcement_date=date(2026, 4, 6),
        # 사업계획서: "※ 2026. 1. 1. 이후의 서류만 인정"
        document_cutoff=date(2026, 1, 1),
        # 사업계획서: "2026년 기준 18~39세 청년(1987.1.1. ~ 2008.12.31.출생자)"
        age_basis_date=date(2026, 1, 1),
        birth_range=(date(1987, 1, 1), date(2008, 12, 31)),
        selection="first_come",
        # 추진체계: "7일 내 서류 보완안내 / 미보완시 지원대상자 제외 및 후순위자 선정"
        supplement_days=7,
        # 사업계획서의 자격요건은 나이와 거주지뿐이다. 소득 요건이 없다.
        has_income_requirement=False,
        apply_period=(date(2026, 4, 6), date(2026, 5, 1)),
        quota_by_region=None,
        # "지원규모 : 총 900건"
        total_quota=900,
        has_work_requirement=False,
        has_subsidy_items=True,
        required_form_fields=JOB_PACKAGE_REQUIRED_FIELDS,
        summary_fields=(
            ("name", "신청자 이름"),
            ("birth", "생년월일"),
            ("gender", "성별"),
            ("address", "주소"),
            ("mobile", "연락처"),
            ("account", "입금 받을 계좌"),
        ),
        # 공통서류 ①이 "신청서(개인정보 수집이용제공 동의서)"다. 수집·이용과 제공 두 건.
        consent_types=("privacy", "third_party"),
        site_url="https://www.jbyouthhub.or.kr",
        call_center="",
        notes=[
            "1차 2026.4.6.~5.1. / 2차 2026.9.7.~10.2.",
            "예산 소진 시 조기 마감 (총 900건)",
            "지원 항목 복수 선택 가능",
            "서류 미비 시 7일 내 보완 안내, 미보완 시 후순위자로 교체",
            # 사업계획서에 신청서·자가진단 서식 원본이 없다. 두배적금 서식1~6처럼
            # 대조할 원본이 없으므로 화면·코드 양쪽에 같은 라벨을 단다.
            "신청서·자가진단 양식은 사업계획서에 서식 원본이 없어 데모가 구성했습니다. (데모 추정치)",
            "기간 역산 항목이 없어 기준일은 1차 신청 시작일로 두었습니다. (데모 추정치)",
            # 사업계획서는 "선착순"이라고만 적고 기준 시각을 정하지 않았다.
            # 서류 완비 시각을 기준으로 삼으면 순번이 뒤바뀌는 건이 생긴다 —
            # TF 확인 대상이라 화면·코드 양쪽에 같은 라벨을 단다.
            "선착순 순번은 제출 시각 기준입니다. 서류 완비 시각 기준 여부는 TF 확인이 필요합니다. (데모 추정치)",
        ],
    ),
}


def get_program(code: str) -> ProgramConfig:
    try:
        return PROGRAMS[code]
    except KeyError:
        raise ValueError(f"알 수 없는 사업 코드: {code}") from None

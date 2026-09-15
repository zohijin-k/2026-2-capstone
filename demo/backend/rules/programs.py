"""사업별 상수.

두배적금과 취업지원패키지는 선발 방식·보완 정책·연령 기준·서류 인정일이 전부
다르다. 분기가 코드 전체에 흩어지지 않게 여기 한 곳에 모은다.

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
    #: 신청 홈페이지
    site_url: str = ""
    #: 전담 콜센터
    call_center: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def allows_supplement(self) -> bool:
        return self.supplement_days is not None


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
        # 사업계획서: "2026. 1. 1. 이후의 서류만 인정"
        document_cutoff=date(2026, 1, 1),
        age_basis_date=date(2026, 1, 1),
        birth_range=(date(1987, 1, 1), date(2008, 12, 31)),
        selection="first_come",
        # 추진체계: "7일 내 서류 보완안내 / 미보완시 지원대상자 제외 및 후순위자 선정"
        supplement_days=7,
        has_income_requirement=False,
        apply_period=(date(2026, 4, 6), date(2026, 5, 1)),
        quota_by_region=None,
        site_url="",
        call_center="",
        notes=[
            "1차 2026.4.6.~5.1. / 2차 2026.9.7.~10.2.",
            "예산 소진 시 조기 마감 (총 900건)",
            "지원 항목 복수 선택 가능",
        ],
    ),
}


def get_program(code: str) -> ProgramConfig:
    try:
        return PROGRAMS[code]
    except KeyError:
        raise ValueError(f"알 수 없는 사업 코드: {code}") from None

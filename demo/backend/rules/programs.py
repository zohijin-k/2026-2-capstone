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
class SavingsPlan:
    """적금 구조 한 행. 청년이 얼마를 넣으면 지자체가 얼마를 얹는지."""

    #: 청년 월 저축액 (원)
    monthly_self: int
    #: 지자체 월 지원액 (원)
    monthly_grant: int
    #: 만기까지의 개월 수
    months: int
    #: 만기 수령액 표기. 이자가 붙어 확정 금액이 아니라 문구로 둔다.
    maturity_label: str
    note: str = ""


@dataclass(frozen=True)
class ApplyStep:
    """신청 절차 한 단계. url이 있으면 label 전체를 링크로 건다."""

    label: str
    url: str = ""


@dataclass(frozen=True)
class ProgramDetail:
    """공고문을 사업 선택 카드에 그대로 펼칠 때 쓰는 상세 항목.

    요약 행(dl) 한 줄로 줄이면 사라지는 정보 — 적금 구조, 신청 시각, 첨부파일
    규칙, 미비 서류의 구체적인 예시, 시군별 배정 인원 — 를 공고문 차례대로
    담는다. 상세를 채우지 않은 사업은 카드가 기존 요약 행만 보여준다.
    """

    #: 「지원 대상」 한 줄 요약
    target_summary: str
    #: 대상 요건을 쪼갠 항목 ("연령: 18~39세" 등)
    target_points: tuple[str, ...]
    #: 「지원 내용」 서술
    benefit_summary: str
    #: 지원 내용 표. 적금형이 아닌 사업은 None.
    savings_plan: SavingsPlan | None
    #: 공고 기간. 신청 기간(apply_period)과 다를 수 있다.
    announce_period: tuple[date, date]
    #: 신청 시작일의 접수 개시 시각 / 마감일의 마감 시각
    apply_open_time: str
    apply_close_time: str
    apply_method: str
    apply_steps: tuple[ApplyStep, ...]
    #: 유의사항 맨 앞에 박스로 세우는 한 줄
    deadline_warning: str
    cautions: tuple[str, ...]
    #: "미비 서류"가 실제로 무엇인지 — 가장 많이 걸리는 사례
    missing_doc_examples: tuple[str, ...]
    selection_methods: tuple[str, ...]


@dataclass(frozen=True)
class DocRow:
    """신청서류 표의 「항목별 추가서류」 한 행."""

    #: 지원 항목명. 지원내용 표(`rules/subsidy.py`)의 label과 같은 표기를 쓴다.
    item: str
    docs: tuple[str, ...]


@dataclass(frozen=True)
class ReviewStep:
    """서류심사 절차 한 단계."""

    title: str
    points: tuple[str, ...]


@dataclass(frozen=True)
class PackageDetail:
    """사업계획서 「Ⅲ. 세부사업계획」 1~3절을 사업 선택 카드에 펼칠 때 쓰는 항목.

    두배적금의 `ProgramDetail`이 공고문(모집공고) 구조라면, 이쪽은 사업계획서
    구조다. 절 순서가 그대로 카드의 절 순서다 — 사업신청 → 서류심사 →
    지원금 지급. 4. 사후연계는 신청자 화면의 관심사가 아니라 담지 않는다.

    금액·횟수·지원 항목은 여기 두지 않는다. 그 값은 `rules/subsidy.py`의
    지원 항목표가 유일한 출처이고, 카드는 `subsidy_catalog`를 읽어 그린다.
    """

    #: 선착순 배지 옆 안내 문구. 신청 기간 절에서도 같은 문장을 쓴다.
    early_close_note: str
    #: 신청 대상 요건 ("연령: 18~39세" 등)
    target_points: tuple[str, ...]
    apply_method: str
    #: 지원 항목 선택 규칙 한 줄
    apply_items_note: str
    #: 공통서류. 고른 항목과 무관하게 모두가 낸다.
    common_docs: tuple[str, ...]
    #: 항목별 추가서류 표
    item_docs: tuple[DocRow, ...]
    #: 신청서류 표 아래 강조하는 인정 기준일 한 줄
    doc_cutoff_notice: str
    review_steps: tuple[ReviewStep, ...]
    #: 서류 보완 관련 안내
    supplement_notes: tuple[str, ...]
    payment_methods: tuple[str, ...]


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
    #: 공고문 전문을 카드에 펼칠 사업만 채운다. None이면 카드가 요약 행만 그린다.
    detail: ProgramDetail | None = None
    #: 사업계획서 구조로 카드를 펼칠 사업만 채운다.
    package_detail: PackageDetail | None = None
    #: 2차 모집이 있는 사업의 2차 신청 기간. 1차는 `apply_period`다.
    apply_period_2: tuple[date, date] | None = None

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

#: 신청 홈페이지. 안내문 링크와 ProgramConfig.site_url이 같은 값을 봐야 한다.
DOUBLE_SAVINGS_SITE = "https://double.jb2030.or.kr"

# 공고문 제2026-443호 본문. 카드가 이 값을 그대로 펼친다.
DOUBLE_SAVINGS_DETAIL = ProgramDetail(
    target_summary="도내 거주 근로청년",
    target_points=(
        "연령: 18~39세",
        "소득 기준: 중위소득 140% 이하",
    ),
    benefit_summary=(
        "청년이 매월 10만 원을 납입하면 지자체가 매월 10만 원을 추가로 지원하는 "
        "2년 만기 적금"
    ),
    savings_plan=SavingsPlan(
        monthly_self=100_000,
        monthly_grant=100_000,
        months=24,
        maturity_label="480만 원 + 이자",
        note="매월 적립 시",
    ),
    announce_period=(date(2026, 3, 3), date(2026, 3, 16)),
    apply_open_time="09:00",
    apply_close_time="18:00",
    apply_method="온라인 신청만 가능",
    apply_steps=(
        ApplyStep(label="전북청년 함께 두배적금 홈페이지에 접속", url=DOUBLE_SAVINGS_SITE),
        ApplyStep(label="신청서 작성"),
        ApplyStep(label="관련 서류 업로드"),
    ),
    deadline_warning="2026. 3. 16.(월) 18:00까지 신청서 제출을 완료해야 합니다.",
    cautions=(
        "첨부파일은 PDF, JPG, PNG 형식만 허용됩니다.",
        "첨부서류는 1개의 파일로 압축하여 업로드해야 합니다.",
        "첨부파일에 설정된 암호는 반드시 해제해야 합니다.",
        "가능하면 PDF 형식으로 제출하는 것을 권장합니다.",
        "서류 미비, 서류 누락, 내용 식별 불가 또는 착오 기재가 있는 경우 대상자 선정에서 제외될 수 있습니다.",
        "방문 및 우편 접수는 불가능합니다.",
        "선착순 모집이 아니므로 신청 기간 안에 신청하면 됩니다.",
        "신청 기간에 제출한 서류가 미비한 경우 별도의 추가·보충서류를 요청하지 않고 참여자 선발에서 제외합니다.",
        "서류 작성 및 제출에 대한 책임은 신청자 본인에게 있습니다.",
    ),
    missing_doc_examples=(
        "파일 암호를 해제하지 않은 경우",
        "주민등록초본에 과거 주소 이력이 포함되지 않은 경우",
        "주민등록초본이 아닌 주민등록등본을 제출한 경우",
        "그 밖에 서류가 누락되었거나 내용을 식별할 수 없는 경우",
    ),
    selection_methods=(
        "시·군별 심사평가",
        "다른 유사사업과의 중복 참여 여부 조회",
    ),
)

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
    ("bankbookFileName", "통장 사본(본인 명의)"),
)

# 사업계획서 「Ⅲ. 세부사업계획」 1~3절 본문. 카드가 이 값을 그대로 펼친다.
JOB_PACKAGE_DETAIL = PackageDetail(
    early_close_note="예산 소진 시 조기 마감",
    target_points=(
        "전북특별자치도 내 거주 청년",
        "연령: 18~39세",
        "출생일 기준: 1987. 1. 1. ~ 2008. 12. 31.",
    ),
    apply_method="전북청년허브센터 홈페이지를 통한 온라인 신청",
    apply_items_note="여러 지원 항목을 복수로 선택할 수 있음",
    common_docs=(
        "청년 취업지원패키지 신청서 (개인정보 수집·이용·제공 동의서 포함)",
        "주민등록초본",
        "본인 명의 통장 사본",
    ),
    item_docs=(
        DocRow(item="면접비", docs=("면접확인서",)),
        DocRow(item="면접정장비", docs=("면접확인서", "결제영수증")),
        DocRow(item="면접사진비", docs=("면접용 사진 사본", "결제영수증")),
        DocRow(
            item="자격증 응시료",
            docs=("응시확인서 또는 성적표(응시일 표기 필수)", "결제영수증"),
        ),
    ),
    doc_cutoff_notice="2026. 1. 1. 이후 발급된 서류만 인정",
    review_steps=(
        ReviewStep(
            title="자격요건 검토",
            points=("신청자의 나이와 거주지 등 자격요건 확인",),
        ),
        ReviewStep(
            title="신청서류 검토",
            points=("제출서류 검토", "서류가 미비한 경우 보완 안내"),
        ),
        ReviewStep(
            title="대상자 선정 및 안내",
            points=("최종 지원 대상자 선정", "문자 또는 전화로 결과 안내"),
        ),
    ),
    supplement_notes=(
        "서류 보완 기간: 안내일로부터 7일 이내",
        "기간 내 미보완 시 후순위자로 교체될 수 있음",
    ),
    payment_methods=(
        "신청자별로 월 단위 취합",
        "신청자 본인 명의 계좌로 지급",
    ),
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
        site_url=DOUBLE_SAVINGS_SITE,
        call_center="1660-2040",
        notes=[
            "선착순이 아니며, 신청기간 내 24시간 신청 가능",
            "서류 미비(누락·식별 불가) 시 보완 요청 없이 선발 제외",
            "평가결과는 공개하지 않음",
        ],
        detail=DOUBLE_SAVINGS_DETAIL,
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
        # 사업계획서 「신청기간」: 2차 2026. 9. 7.(월) ~ 10. 2.(금)
        apply_period_2=(date(2026, 9, 7), date(2026, 10, 2)),
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
            ("bankbookFileName", "통장 사본(본인 명의)"),
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
        package_detail=JOB_PACKAGE_DETAIL,
    ),
}


def get_program(code: str) -> ProgramConfig:
    try:
        return PROGRAMS[code]
    except KeyError:
        raise ValueError(f"알 수 없는 사업 코드: {code}") from None

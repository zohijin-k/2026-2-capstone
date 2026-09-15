"""신청자별 맞춤 서류 체크리스트.

공고문의 제출서류 8종 중 ⑥ 근로확인서류는 **5종 중 택1**이고, 무엇을 내야 하는지는
신청자의 근로유형에 달려 있다. 엔진의 `RequiredDocumentSpec`에는 "택1 그룹" 개념이
없으므로(E3), 신청자별 실제 목록을 여기서 조립해 엔진에 넘긴다.

값의 출처: 공고문 제2026-443호 제출서류 표, `docs/demo-site-dev-plan.md` 2.3절.
"""

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum

from .doc_types import ISSUER_LINKS, DocType
from .programs import DOUBLE_SAVINGS, ProgramConfig

#: 공고문 파일 규칙: "pdf, jpg, png만 허용 (pdf 권장)"
ACCEPTED_FORMATS = ["pdf", "jpg", "jpeg", "png"]


class WorkCategory(StrEnum):
    """근로확인서류 ⑥-㉠~㉤ 중 무엇을 내야 하는지를 가르는 축.

    서식1의 '근로유형'(상용직/임시직/일용직)과는 다른 축이다. 서식1은 근로형태를
    묻지만, 근로확인서류는 건강보험 가입 형태와 소득 종류로 갈린다.
    """

    EMPLOYEE = "직장가입자"
    LOCAL = "지역가입자·피부양자"
    BUSINESS = "사업소득 사업자"
    FARM = "농업·임업"
    FISHERY = "어업"


#: 화면 선택지 순서. 공고문 ⑥-㉠~㉤ 순서를 그대로 따른다.
WORK_CATEGORIES: list[WorkCategory] = [
    WorkCategory.EMPLOYEE,
    WorkCategory.LOCAL,
    WorkCategory.BUSINESS,
    WorkCategory.FARM,
    WorkCategory.FISHERY,
]


@dataclass
class ApplicantDocInput:
    """체크리스트를 조립하는 데 필요한 최소 입력."""

    work_category: WorkCategory | None = None
    #: 행정기관 기간제 근로자 여부. 참이면 근로계약서 사본이 추가된다.
    admin_fixed_term: bool = False
    #: 복수 사업장 근무 시 사업장 수. 사업장별로 근로확인서류를 각각 낸다.
    workplace_count: int = 1
    #: 서식5를 자필서명 스캔으로 내는 경우 True (데모 기본값은 전자서명).
    handwritten_admin_consent: bool = False


@dataclass
class DocRequirement:
    """체크리스트 한 줄.

    `slot_key`가 업로드 슬롯의 식별자다. 같은 `doc_type`이 여러 슬롯에 올 수 있어
    (복수 사업장 근로확인서류) `doc_type`과 분리한다.
    """

    slot_key: str
    doc_type: DocType
    #: 화면 표기명. 공고문 표기를 그대로 쓴다.
    label: str
    required: bool = True
    requires_signature: bool = False
    check_declared_date: bool = True
    min_issue_date: date | None = None
    #: 발급처 이름 / 바로가기 URL
    issuer: str = ""
    issuer_url: str = ""
    #: 공고문 세부 요건. 원문 표기를 유지한다.
    notes: list[str] = field(default_factory=list)
    #: 자주 틀리는 것 인라인 경고 (등본≠초본, 등록증≠증명, 암호 해제 등).
    warnings: list[str] = field(default_factory=list)
    #: 이 자리에 대신 인정되는 서류.
    alternatives: list[str] = field(default_factory=list)
    #: 파일 업로드가 필요한가. False면 온라인 작성으로 대체된 항목이다.
    upload: bool = True
    #: 업로드가 아닌 경우 무엇으로 갈음했는지.
    fulfilled_by: str = ""
    accept: list[str] = field(default_factory=lambda: list(ACCEPTED_FORMATS))


#: 모든 업로드 서류에 공통으로 붙는 경고. 공고문 파일 규칙 원문.
COMMON_WARNINGS = [
    "파일 암호를 반드시 해제한 뒤 올려 주세요.",
    "모니터 화면을 캡처한 이미지는 인정되지 않습니다. 스캔본이나 선명한 사진으로 올려 주세요.",
]


def _issuer(doc_type: DocType) -> tuple[str, str]:
    return ISSUER_LINKS.get(doc_type, ("", ""))


def _make(
    slot_key: str,
    doc_type: DocType,
    *,
    label: str | None = None,
    notes: list[str] | None = None,
    warnings: list[str] | None = None,
    alternatives: list[str] | None = None,
    requires_signature: bool = False,
    check_declared_date: bool = True,
    min_issue_date: date | None = None,
) -> DocRequirement:
    issuer, issuer_url = _issuer(doc_type)
    return DocRequirement(
        slot_key=slot_key,
        doc_type=doc_type,
        label=label or str(doc_type),
        requires_signature=requires_signature,
        check_declared_date=check_declared_date,
        min_issue_date=min_issue_date,
        issuer=issuer,
        issuer_url=issuer_url,
        notes=notes or [],
        warnings=(warnings or []) + COMMON_WARNINGS,
        alternatives=alternatives or [],
    )


def _work_proof(
    slot_key: str, category: WorkCategory, cutoff: date, ordinal: str = ""
) -> DocRequirement:
    """근로확인서류 ⑥ — 근로유형에 따라 딱 1종만 남긴다."""
    suffix = f" ({ordinal})" if ordinal else ""

    if category is WorkCategory.EMPLOYEE:
        return _make(
            slot_key,
            DocType.INSURANCE_4,
            label=f"4대보험 가입내역 확인서{suffix}",
            notes=[
                "직장가입자에 해당합니다.",
                "4대보험(국민연금·건강보험·고용보험·산재보험) 중 1개 이상 가입 시 반드시 제출해야 합니다.",
            ],
            min_issue_date=cutoff,
        )
    if category is WorkCategory.LOCAL:
        return _make(
            slot_key,
            DocType.DAILY_WORK_RECORD,
            label=f"고용·산재보험 일용근로내역서{suffix}",
            notes=["지역가입자·피부양자에 해당합니다."],
            alternatives=[
                "고용·산재보험 미가입자는 예외적으로 근로계약서 사본으로 갈음할 수 있습니다.",
            ],
            min_issue_date=cutoff,
        )
    if category is WorkCategory.BUSINESS:
        return _make(
            slot_key,
            DocType.BIZ_REG_PROOF,
            label=f"사업자등록증명{suffix}",
            notes=["사업소득이 있는 사업자만 해당합니다."],
            warnings=["'사업자등록증'이 아니라 '사업자등록증명'입니다. 이름이 한 글자 다릅니다."],
            min_issue_date=cutoff,
        )
    if category is WorkCategory.FARM:
        return _make(
            slot_key,
            DocType.FARM_BIZ_CERT,
            label=f"농업경영체 증명서{suffix}",
            notes=["단독·공동경영주만 해당합니다."],
            min_issue_date=cutoff,
        )
    return _make(
        slot_key,
        DocType.FISHERY_BIZ_CERT,
        label=f"어업경영체 증명서{suffix}",
        notes=["단독·공동경영주만 해당합니다."],
        min_issue_date=cutoff,
    )


def build_checklist(
    program: ProgramConfig, applicant: ApplicantDocInput
) -> list[DocRequirement]:
    """근로유형·선택항목에 따라 실제로 올려야 할 서류만 반환한다.

    취업지원패키지 분기는 형제 태스크(`09-16-demo-jobpkg`)가 채운다. 여기서는
    공통 서류(주민등록초본)까지만 내고 항목별 추가서류는 넣지 않는다.
    """
    cutoff = program.document_cutoff
    items: list[DocRequirement] = []

    # ⑧ 주민등록초본 — 두 사업 공통.
    items.append(
        _make(
            "resident_abstract",
            DocType.RESIDENT_ABSTRACT,
            label="주민등록초본",
            notes=[
                "주민등록번호 뒷자리가 표시되어야 합니다.",
                "최근 5년 주소변동내역이 포함되어야 합니다.",
                "하단 병역사항이 포함되어야 합니다.",
            ],
            warnings=[
                "'주민등록등본'이 아니라 '주민등록초본'입니다. 가장 많이 틀리는 항목입니다.",
                "정부24 발급 화면에서 ① 주민등록번호 뒷자리 표시 ② 과거 주소변동 포함을 반드시 체크하세요.",
            ],
            min_issue_date=cutoff,
        )
    )

    if program.code != DOUBLE_SAVINGS:
        return items

    # ⑦ 소득재산 증빙서류 3종 — 모두 제출.
    items.append(
        _make(
            "nhis_payment",
            DocType.NHIS_PAYMENT,
            label="2025년 건강보험료 납부확인서",
            notes=[
                "'25. 10월 ~ 12월 3개월분이 포함되어야 합니다.",
                "실납부액이 아니라 고지금액 기준으로 심사합니다.",
            ],
            min_issue_date=cutoff,
        )
    )
    items.append(
        _make(
            "nhis_qualification",
            DocType.NHIS_QUALIFICATION,
            label="건강보험 자격확인서",
            notes=["가구원 수 확인용입니다. 가구원이 모두 표시되어야 합니다."],
            warnings=["'자격득실확인서'와 다른 서류입니다. 둘 다 제출해야 합니다."],
            min_issue_date=cutoff,
        )
    )
    items.append(
        _make(
            "nhis_acquisition_loss",
            DocType.NHIS_ACQUISITION_LOSS,
            label="건강보험 자격득실확인서",
            notes=["최근 5년 변동내역이 포함되어야 합니다."],
            warnings=["'자격확인서'와 다른 서류입니다. 둘 다 제출해야 합니다."],
            min_issue_date=cutoff,
        )
    )

    # ⑥ 근로확인서류 — 근로유형이 정해져야 어떤 1종인지 결정된다.
    category = applicant.work_category
    if category is not None:
        count = max(1, applicant.workplace_count)
        if count == 1:
            items.append(_work_proof("work_proof", category, cutoff))
        else:
            # 복수 사업장 근무자는 사업장별로 각각 낸다.
            for i in range(1, count + 1):
                items.append(
                    _work_proof(f"work_proof_{i}", category, cutoff, ordinal=f"{i}번째 사업장")
                )

        if category is WorkCategory.EMPLOYEE and applicant.admin_fixed_term:
            items.append(
                _make(
                    "labor_contract",
                    DocType.LABOR_CONTRACT,
                    label="근로계약서 사본",
                    notes=["행정기관 기간제 근로자만 추가로 제출합니다."],
                    check_declared_date=False,
                )
            )

    # ⑤ 행정정보 공동이용 사전동의서 (서식5).
    # 원문은 자필서명 후 스캔 첨부지만, 데모는 캔버스 전자서명으로 대체한다(R1.2).
    if applicant.handwritten_admin_consent:
        items.append(
            _make(
                "admin_info_consent",
                DocType.ADMIN_INFO_CONSENT,
                label="행정정보 공동이용 사전동의서 (서식5)",
                notes=["자필서명 후 스캔본을 올려 주세요."],
                requires_signature=True,
                check_declared_date=False,
            )
        )
    else:
        issuer, issuer_url = _issuer(DocType.ADMIN_INFO_CONSENT)
        items.append(
            DocRequirement(
                slot_key="admin_info_consent",
                doc_type=DocType.ADMIN_INFO_CONSENT,
                label="행정정보 공동이용 사전동의서 (서식5)",
                requires_signature=True,
                check_declared_date=False,
                issuer=issuer,
                issuer_url=issuer_url,
                notes=["현행 지침은 자필서명을 요구합니다. 데모는 전자서명으로 대체합니다."],
                upload=False,
                fulfilled_by="서식5 캔버스 전자서명",
            )
        )

    return items


def upload_slots(checklist: list[DocRequirement]) -> list[DocRequirement]:
    """실제로 파일을 올려야 하는 슬롯만."""
    return [r for r in checklist if r.upload]


def find_slot(checklist: list[DocRequirement], slot_key: str) -> DocRequirement | None:
    for r in checklist:
        if r.slot_key == slot_key:
            return r
    return None


def slot_for_doc_type(
    checklist: list[DocRequirement], doc_type: DocType
) -> DocRequirement | None:
    """병합 PDF 페이지 자동 배정용. 판독된 문서종류에 맞는 빈 슬롯을 찾는다."""
    for r in checklist:
        if r.upload and r.doc_type == doc_type:
            return r
    return None

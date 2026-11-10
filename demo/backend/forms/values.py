"""신청 1건 → 서식 칸에 넣을 값.

화면에서 보이던 것과 같은 값이 PDF에도 찍혀야 한다. 그래서 자동 판정 항목
(거주기간·근로기간 구간)은 화면과 같은 규칙(`rules/scoring`)으로 다시 계산한다.
여기서 따로 계산하면 화면은 "4년 이상 ~ 5년 미만"인데 PDF는 5년에 체크되는
사고가 난다.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from ..models import Application, Consent
from ..rules.facts import parse_ymd
from ..rules.programs import DOUBLE_SAVINGS, get_program
from ..rules.scoring import RESIDENCE_BANDS, WORK_BANDS, elapsed_years_months

#: 두배적금 납입금액은 보기가 하나뿐이다(월 10만원). 신청 자체가 곧 선택이다.
MONTHLY_DEPOSIT = "월 10만원"


@dataclass
class FilledForm:
    """서식 한 장에 채워 넣을 것 전부."""

    form_no: str
    #: 필드 키 → 적을 글자
    texts: dict[str, str] = field(default_factory=dict)
    #: 체크할 필드 키 (`gender.남` 처럼 묶음.보기)
    checks: list[str] = field(default_factory=list)
    #: 필드 키 → 이미지 파일 경로 (서식5 전자서명)
    images: dict[str, str | bytes] = field(default_factory=dict)


def format_date(value: Any) -> str:
    """서식의 날짜 표기 — 원문 예시(‘26. 3. 3.)와 같은 점 표기를 쓴다."""
    parsed = parse_ymd(value)
    return f"{parsed.year}. {parsed.month}. {parsed.day}." if parsed else ""


def _band(start: Any, basis: date, bands: list[tuple[int, str]]) -> str | None:
    """전입일·취업일 → 서식의 구간 라벨. 화면 자동 선택과 같은 규칙이다."""
    parsed = parse_ymd(start)
    if parsed is None or parsed > basis:
        return None
    years, _ = elapsed_years_months(parsed, basis)
    return bands[min(years, len(bands) - 1)][1]


def _put(target: dict[str, str], key: str, value: Any) -> None:
    if isinstance(value, str) and value.strip():
        target[key] = value.strip()


def _check(checks: list[str], group: str, value: Any) -> None:
    if isinstance(value, str) and value.strip():
        checks.append(f"{group}.{value.strip()}")


def build_form1(app: Application, **_: Any) -> FilledForm:
    form1: dict[str, Any] = app.form1_json or {}
    program = get_program(app.program_code)
    filled = FilledForm(form_no="서식1")

    for key in (
        "priorName",
        "priorPeriod",
        "priorAmount",
        "name",
        "address",
        "mobile",
        "email",
        "ecName",
        "ecRelation",
        "ecContact",
        "workplaceName",
        "workplaceAddress",
        "workplaceContact",
        "bankName",
        "accountNo",
        "accountHolder",
        "householdSizeCount",
    ):
        _put(filled.texts, key, form1.get(key))

    _put(filled.texts, "birth", format_date(form1.get("birth")))

    # 작성일 — 원문은 "2026. . ." 이라 월·일만 채운다. 제출 전이면 마지막 저장 시각.
    written = app.submitted_at or app.updated_at or datetime.now()
    filled.texts["writtenMonth"] = str(written.month)
    filled.texts["writtenDay"] = str(written.day)

    for group in (
        "savingPurpose",
        "priorJoined",
        "gender",
        "householdType",
        "householdSize",
        "workType",
        "workplaceRegion",
        "adminWorkForm",
    ):
        _check(filled.checks, group, form1.get(group))

    # 자동 판정 두 가지. 신청자가 고르는 것이 아니라 날짜에서 나온다 (R3.3/R8.5).
    residence = _band(form1.get("transferIn"), program.announcement_date, RESIDENCE_BANDS)
    if residence:
        filled.checks.append(f"residencePeriod.{residence}")
    work = _band(form1.get("employedAt"), program.announcement_date, WORK_BANDS)
    if work:
        filled.checks.append(f"workPeriod.{work}")

    filled.checks.append(f"monthlyDeposit.{MONTHLY_DEPOSIT}")

    paths = form1.get("referralPaths")
    if isinstance(paths, list):
        for path in paths:
            _check(filled.checks, "referralPaths", path)

    return filled


def _written_values(stamp: datetime | date) -> tuple[str, str, str]:
    value = stamp.date() if isinstance(stamp, datetime) else stamp
    return str(value.year), str(value.month), str(value.day)


def build_self_check(app: Application, **_: Any) -> FilledForm:
    filled = FilledForm(form_no="서식2")
    for number, answer in (app.self_check_json or {}).items():
        if str(number).isdigit():
            _check(filled.checks, f"self_check.{number}", answer)
    return filled


def build_consent_form(form_no: str, app: Application, consents: list[Consent], **_: Any) -> FilledForm:
    form1 = app.form1_json or {}
    filled = FilledForm(form_no=form_no)
    stamp = app.submitted_at or app.updated_at or datetime.now()
    mapping = {
        "서식3": {"privacy": "privacy", "uniqueId": "unique_id"},
        "서식4": {"thirdParty": "third_party"},
        "job_consent": {"privacy": "privacy", "thirdParty": "third_party"},
    }[form_no]
    prefix = "consent.job" if form_no == "job_consent" else f"consent.form{form_no[-1]}"
    year, month, day = _written_values(stamp)
    if form_no == "job_consent":
        # 원본에 연도(2026년)가 인쇄되어 있어 월·일만 채운다.
        for key, value in (("month", month), ("day", day)):
            _put(filled.texts, f"{prefix}.{key}", value)
    else:
        _put(filled.texts, f"{prefix}.year", year)
        _put(filled.texts, f"{prefix}.month", month)
        _put(filled.texts, f"{prefix}.day", day)
    records = {c.consent_type: c for c in consents}
    for field_key, consent_type in mapping.items():
        consent = records.get(consent_type)
        if consent is not None:
            _check(filled.checks, f"consent.{field_key}", "동의함" if consent.agreed else "동의하지 않음")
    if form_no == "job_consent":
        signature = (app.form1_json or {}).get("consent.job.signature")
        if isinstance(signature, str) and signature.startswith("data:image/png;base64,"):
            import base64

            try:
                filled.images["consent.job.signature"] = base64.b64decode(signature.split(",", 1)[1])
            except ValueError:
                pass
    return filled


def build_job_application(
    app: Application, subsidy_items: list[Any] | None = None, **_: Any
) -> FilledForm:
    form1: dict[str, Any] = app.form1_json or {}
    filled = FilledForm(form_no="job_application")
    for key in (
        "name", "address", "mobile", "email", "bankName", "accountNo",
        "job.photo.paymentDate", "job.photo.cost",
        *(f"job.{kind}.{index}.{field}" for kind in ("interview", "suit", "certificate")
          for index in (1, 2) for field in ("company", "location", "date", "detail", "exam", "organizer", "cost")),
    ):
        _put(filled.texts, key, form1.get(key))
    _put(filled.texts, "birth", format_date(form1.get("birth")))
    year, month, day = _written_values(app.submitted_at or app.updated_at or datetime.now())
    for key, value in (("job.applicationYear", year), ("job.applicationMonth", month), ("job.applicationDay", day)):
        _put(filled.texts, key, value)
    signature = form1.get("job.signature")
    if isinstance(signature, str) and signature.startswith("data:image/png;base64,"):
        import base64

        try:
            filled.images["job.signature"] = base64.b64decode(signature.split(",", 1)[1])
        except ValueError:
            pass
    labels = {
        "interview": "면접비", "suit": "면접정장비",
        "photo": "면접사진촬영비", "certificate": "자격증 응시료",
    }
    for item in subsidy_items or []:
        label = labels.get(item.item_type)
        if label:
            _check(filled.checks, f"subsidy.{item.item_type}", label)
    has_interview = any(item.item_type == "interview" for item in subsidy_items or [])
    if has_interview:
        for item in subsidy_items or []:
            if item.item_type != "suit" or item.linked_interview_index is None:
                continue
            for field_name in ("company", "location", "date"):
                source_key = f"job.interview.{item.linked_interview_index}.{field_name}"
                target_key = f"job.suit.{item.count_index}.{field_name}"
                _put(filled.texts, target_key, form1.get(source_key))
    return filled


def build_interview_confirmation(app: Application, **_: Any) -> FilledForm:
    """회사 작성 면접확인서의 신청자 칸만 채운다."""
    form1: dict[str, Any] = app.form1_json or {}
    identity = app.identity_json or {}
    filled = FilledForm(form_no="job_interview_confirmation")
    _put(filled.texts, "name", identity.get("name") or form1.get("name"))
    _put(filled.texts, "birth", format_date(identity.get("birth") or form1.get("birth")))
    for key in ("address", "mobile", "email"):
        _put(filled.texts, key, form1.get(key))
    return filled


def build_form5(app: Application, consents: list[Consent], storage_root: Any, **_: Any) -> FilledForm:
    """서식5 — 값은 서식5 입력값 우선, 비어 있으면 서식1에서 끌어온다.

    동의 여부와 서명은 `consent` 테이블이 정본이다. 서식5 입력값(form5_json)에는
    서명 이미지가 data URL 로 들어 있지만, 저장된 파일이 증거다.
    """
    form5: dict[str, Any] = app.form5_json or {}
    form1: dict[str, Any] = app.form1_json or {}
    filled = FilledForm(form_no="서식5")

    _put(filled.texts, "name", form5.get("name") or form1.get("name"))
    _put(filled.texts, "birth", format_date(form5.get("birth") or form1.get("birth")))
    _put(filled.texts, "phone", form5.get("phone") or form1.get("mobile"))

    admin = next((c for c in consents if c.consent_type == "admin_info"), None)

    written = parse_ymd(form5.get("writtenOn"))
    if written is None:
        stamp = admin.agreed_at if admin else (app.submitted_at or app.updated_at)
        written = (stamp or datetime.now()).date()
    filled.texts["writtenMonth"] = str(written.month)
    filled.texts["writtenDay"] = str(written.day)

    if admin is not None:
        filled.checks.append(f"agree.{'동의함' if admin.agreed else '동의하지 않음'}")
        if admin.signature_path:
            target = storage_root.parent / admin.signature_path
            if target.exists():
                filled.images["signature"] = str(target)

    return filled


def available_forms(app: Application) -> list[str]:
    """이 신청 건에서 내보낼 수 있는 서식.

    서식1·5는 두배적금 서식이다. 취업지원패키지는 원본 서식 자체가 사업계획서에
    없어(P5에서 남긴 것) 내보낼 것이 없다.
    """
    if app.program_code != DOUBLE_SAVINGS:
        return ["job_application", "job_consent"]
    forms = ["서식1", "서식2", "서식3", "서식4"]
    if get_program(app.program_code).consent_types and "admin_info" in get_program(
        app.program_code
    ).consent_types:
        forms.append("서식5")
    return forms


BUILDERS = {
    "서식1": build_form1,
    "서식2": build_self_check,
    "서식3": lambda app, consents=(), **kw: build_consent_form("서식3", app, list(consents), **kw),
    "서식4": lambda app, consents=(), **kw: build_consent_form("서식4", app, list(consents), **kw),
    "서식5": build_form5,
    "job_application": build_job_application,
    "job_consent": lambda app, consents=(), **kw: build_consent_form("job_consent", app, list(consents), **kw),
    "job_interview_confirmation": build_interview_confirmation,
}

"""현황 대시보드 집계 (신청자·담당자 화면과 같은 앱의 세 번째 탭).

**서버는 집계하지 않고 행을 내려준다.** 대시보드의 중심 기능이 기준일 타임머신
이라서다 — 재생 버튼이 200ms마다 기준일을 하루씩 밀고 그때마다 전건을 다시
집계한다. 스냅샷을 서버에서 만들면 74일 구간 재생이 74번의 왕복이 되어 기능이
통째로 죽는다. 게다가 집계 로직(`lib/metrics.ts` + `lifecycle.ts` + `dates.ts`)을
파이썬으로 한 벌 더 만들면, 두 벌이 어긋났는지 확인할 방법이 양쪽에 없다.

응답 크기로 반대할 만한 지점도 여기선 성립하지 않는다. 실데이터는 시연 규모라
수십 건이고, 12,821건짜리 목업은 **서버를 거치지 않는다**(프론트가 만든다 —
백엔드가 죽었을 때 목업으로 떨어지는 것이 폴백의 정의인데, 목업이 서버에 있으면
폴백도 같이 죽는다).

배점·커트라인은 `scores`라는 **별도 배열**로 나간다. 같은 행에 섞어 두고 권한에
따라 값을 지우는 방식은 한 군데만 빠뜨려도 조용히 새어나간다. 배열째 있거나
없거나면 누락이 구조적으로 불가능하다.

다만 데모에는 로그인이 없다. `?role=province`를 붙이면 누구나 점수를 본다.
**권한이 아니라 권한 구조의 시연**이라는 사실을 응답(`scores_withheld_reason`)과
화면에 그대로 밝힌다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlmodel import select

from ..models import Application, Review, get_session
from ..rules import scoring
from ..rules.facts import extract_region, parse_int, parse_ymd
from ..rules.programs import get_program
from ..rules.roles import ROLE_CITY, ROLE_PROVINCE

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

STATUS_DRAFT = "draft"

#: 배점을 볼 수 있는 역할. 읍·면·동은 구비서류 완비만 확인하므로 제외한다.
SCORE_ROLES = {ROLE_CITY, ROLE_PROVINCE}


# ---------------------------------------------------------------- 구간 역매핑

#: 점수 → 화면 구간 인덱스.
#:
#: **인덱스를 그대로 주고받으면 소득 배점이 뒤집힌다.** 백엔드 INCOME_BANDS 는
#: 높은 소득이 0번(130% 이상 = 28점)이고 화면은 낮은 소득이 0번(100% 미만 = 40점)
#: 이다. 거주·근로는 순서가 같다. 표를 손으로 베끼면 언젠가 어긋나므로 규칙 표에서
#: 직접 만든다.
INCOME_INDEX = {score: i for i, (_, score, _) in enumerate(reversed(scoring.INCOME_BANDS))}
RESIDENCE_INDEX = {score: i for i, (score, _) in enumerate(scoring.RESIDENCE_BANDS)}
WORK_INDEX = {score: i for i, (score, _) in enumerate(scoring.WORK_BANDS)}

#: 화면이 쓰는 표기. 백엔드는 '직장' / '지역' / '혼합' 으로 짧게 쓴다.
INSURANCE_LABEL = {"직장": "직장가입자", "지역": "지역가입자", "혼합": "혼합가입자"}

GENDER_LABEL = {"남": "남성", "여": "여성", "남성": "남성", "여성": "여성"}

#: `doc_context.work_category` 가 이기는 값들. 서식1의 근로유형과는 다른 축이라
#: 사업자·농어업인은 이쪽에만 있다.
WORK_CATEGORY_LABEL = {
    "사업소득 사업자": "사업자",
    "농업·임업": "농어업인",
    "어업": "농어업인",
}

#: 화면이 아는 근로유형. 여기 없으면 집계에서 빼고 notes 에 남긴다.
WORK_TYPES = {"상용직", "임시직", "일용직", "사업자", "농어업인"}

#: 화면 심사표의 연령 구간 범위. 밖이면 `AGE_BANDS[-1]` 을 집어 TypeError 가 난다.
MIN_AGE, MAX_AGE = 18, 39

#: 화면 배점 분포의 최저 총점. 미만이면 `scoreBins[score-66]` 이 범위를 벗어난다.
MIN_TOTAL_SCORE = (
    scoring.INCOME_BANDS[0][1]
    + scoring.RESIDENCE_BANDS[0][0]
    + scoring.WORK_BANDS[0][0]
    + scoring.AGE_BANDS[-1][1]
)


# ---------------------------------------------------------------- 응답 스키마


class DashboardSchedule(BaseModel):
    openAt: int
    closeAt: int
    reviewStartAt: int
    firstSelectionAt: dict[str, int]
    secondVerificationAt: int
    announcementAt: int


class RegionQuota(BaseModel):
    name: str
    quota: int


class DashboardApplication(BaseModel):
    """화면에 공개해도 되는 12필드. **이름·주소는 절대 싣지 않는다.**"""

    id: str
    region: str
    submittedAt: int | None
    age: int
    gender: str
    workType: str
    insuranceType: str
    householdSize: int
    docReviewedAt: int | None
    eligibilityReviewedAt: int | None
    rejectStage: str | None
    rejectReason: str | None
    firstSelected: bool
    finalSelected: bool


class ScoreRow(BaseModel):
    """담당자 전용. 권한이 없으면 이 배열 자체가 내려가지 않는다."""

    id: str
    incomeBand: int
    residenceBand: int
    workBand: int
    score: int


class DashboardDataset(BaseModel):
    source: Literal["live"]
    #: 0이면 프론트가 목업으로 전환한다.
    total: int
    generatedAt: int
    schedule: DashboardSchedule
    regions: list[RegionQuota]
    applications: list[DashboardApplication]
    scores: list[ScoreRow] | None = None
    #: 배점을 왜 빼고 보냈는지. 화면에 그대로 띄운다.
    scoresWithheldReason: str | None = None
    #: 원천이 없어 제외했거나 근사한 사실. 화면 각주로 나간다.
    notes: list[str] = []


class DashboardMeta(BaseModel):
    """전건을 받기 전에 배지·폴백만 먼저 정하고 싶을 때."""

    source: Literal["live"]
    total: int
    generatedAt: int


# ---------------------------------------------------------------- 조회


@dataclass
class _Row:
    app: Application
    review: Review | None


def _load(program_code: str) -> list[_Row]:
    """제출된 신청 건 + 심사 결과. 쿼리 2개 고정 — N+1 을 만들지 않는다.

    `document` 는 읽지 않는다. 부적합 사유는 엔진이 `review_payload_json` 에 이미
    복사해 두었고, 대시보드가 필요한 것은 그 문장 하나뿐이다.
    """
    with get_session() as s:
        apps = list(
            s.exec(
                select(Application).where(
                    Application.status != STATUS_DRAFT,
                    Application.program_code == program_code,
                )
            ).all()
        )
        reviews = {r.application_id: r for r in s.exec(select(Review)).all()}
    return [_Row(a, reviews.get(a.id or 0)) for a in apps]


# ---------------------------------------------------------------- 값 변환


def _ms(value: datetime | None) -> int | None:
    return int(value.timestamp() * 1000) if value else None


def _work_type(form1: dict[str, Any], doc_context: dict[str, Any]) -> str | None:
    """근로유형 5종.

    서식1의 `workType`(4종)과 `doc_context.work_category`(5종)는 **다른 축**이다
    (`rules/required_docs.WorkCategory` 주석 참고). 사업자·농어업인은 후자에만
    있으므로 그쪽을 먼저 본다. 서식1의 '기타(혼합)'은 화면에 대응 값이 없다.
    """
    category = str(doc_context.get("work_category") or "")
    if category in WORK_CATEGORY_LABEL:
        return WORK_CATEGORY_LABEL[category]
    raw = str(form1.get("workType") or "")
    head = raw.split("(")[0].strip()
    return head if head in WORK_TYPES else None


def _reject(review: Review | None) -> tuple[str | None, str | None]:
    """(단계, 사유 한 줄).

    2차 중복 조회(`duplicate`)는 **데모에서 발화하지 않는다** — 행복e음·일모아가
    미연동이라 중복 판정 경로 자체가 없다. 그래서 여기서도 만들지 않는다.
    """
    if review is None or review.final_status != "FAIL":
        return None, None
    stage = "document" if review.stage1_status == "FAIL" else "eligibility"
    want = "stage1_document" if stage == "document" else "stage2_eligibility"
    reasons = (review.review_payload_json or {}).get("reasons") or []
    message = next(
        (str(r.get("message")) for r in reasons if r.get("stage") == want and r.get("message")),
        None,
    )
    return stage, message


def _selection(review: Review | None) -> tuple[bool, bool]:
    """(1차 선정, 최종 선정).

    `review` 는 판단 컬럼을 **하나만** 들고 있다. 시군이 1차 선발한 뒤 도가 최종
    선정하면 앞 기록이 덮어써지므로, 두 단계를 동시에 볼 수는 없다. 화면의
    "1차 660명 중 최종 550명"은 실데이터로는 그릴 수 없는 그림이다.
    """
    if review is None or review.officer_decision != "approve":
        return False, False
    if review.officer_role == ROLE_PROVINCE:
        return True, True
    if review.officer_role == ROLE_CITY:
        return True, False
    return False, False


def _band(score_json: dict[str, Any], key: str, table: dict[int, int]) -> int | None:
    """심사표 항목 점수 → 화면 구간 인덱스. 채점 못 한 항목(incomplete)은 None."""
    for item in score_json.get("items") or []:
        if item.get("key") == key:
            if item.get("incomplete"):
                return None
            return table.get(int(item.get("score") or -1))
    return None


# ---------------------------------------------------------------- 일정


def _schedule(submitted: list[datetime], regions: list[str]) -> DashboardSchedule:
    """실데이터용 일정.

    목업은 '26.3.3~5.15 타임라인 위에 있지만 실제 신청 건은 시연 당일에 찍힌다.
    두 타임라인을 맞추겠다고 실제 `submitted_at` 을 옮겨 앉히지는 않는다 — 그건
    기록의 위조이고, 이 대시보드의 값어치는 "이 숫자가 어디서 나왔는가"를 댈 수
    있다는 데 있다. 대신 일정 쪽을 실데이터에 맞춘다.

    대가는 정직하게 적어 둔다. **live 모드에서 타임머신은 사실상 하루짜리가 된다.**
    타임머신은 목업 모드의 기능이고, live 모드의 기능은 "방금 낸 신청이 여기 잡힌다"다.
    """
    today = date.today()
    first = min(submitted).date() if submitted else today
    open_at = datetime.combine(first, time.min)
    close_at = datetime.combine(today, time.max)
    # 아직 오지 않은 단계들. 슬라이더에 폭은 생기되 데이터는 오늘까지만 있다.
    first_selection = datetime.combine(today + timedelta(days=1), time.max)
    second = datetime.combine(today + timedelta(days=2), time.max)
    announcement = datetime.combine(today + timedelta(days=3), time.max)
    return DashboardSchedule(
        openAt=int(open_at.timestamp() * 1000),
        closeAt=int(close_at.timestamp() * 1000),
        reviewStartAt=int(open_at.timestamp() * 1000),
        firstSelectionAt={r: int(first_selection.timestamp() * 1000) for r in regions},
        secondVerificationAt=int(second.timestamp() * 1000),
        announcementAt=int(announcement.timestamp() * 1000),
    )


# ---------------------------------------------------------------- 엔드포인트


@router.get("/meta", response_model=DashboardMeta)
def meta(program: str = Query("double_savings")) -> DashboardMeta:
    rows = _load(program)
    return DashboardMeta(
        source="live",
        total=len(rows),
        generatedAt=int(datetime.now().timestamp() * 1000),
    )


@router.get("/dataset", response_model=DashboardDataset)
def dataset(
    program: str = Query("double_savings"),
    role: str | None = Query(None, description="배점을 보려면 city 또는 province"),
) -> DashboardDataset:
    prog = get_program(program)
    regions = prog.target_regions
    quota = prog.quota_by_region or {}
    rows = _load(program)

    applications: list[DashboardApplication] = []
    scores: list[ScoreRow] = []
    dropped_region = 0
    dropped_age = 0
    dropped_work = 0
    dropped_score = 0
    submitted_times: list[datetime] = []

    for row in rows:
        form1 = row.app.form1_json or {}
        doc_context = row.app.doc_context_json or {}

        # --- 가드 1. 시군을 못 읽으면 버린다.
        # 화면의 집계는 14개 시군 맵에 바로 꽂는 구조라(accumulators.get(region)!),
        # 목록 밖 값이 하나 섞이면 그 자리에서 TypeError 로 터진다.
        region = extract_region(str(form1.get("address") or ""), regions)
        if region not in regions:
            dropped_region += 1
            continue

        # --- 가드 2. 연령이 18~39 밖이면 버린다.
        # 화면 심사표는 그 범위만 갖고 있어서, 밖이면 AGE_BANDS[-1] 을 집어 터진다.
        # 연령 미달·초과 신청 자체는 막히지 않는다(엔진이 부적합으로 처리할 뿐).
        birth = parse_ymd(form1.get("birth"))
        if birth is None:
            dropped_age += 1
            continue
        age = scoring.korean_age_at(birth, prog.age_basis_date)
        if not (MIN_AGE <= age <= MAX_AGE):
            dropped_age += 1
            continue

        # --- 가드 3. 화면에 없는 근로유형('기타(혼합)')은 버린다.
        work_type = _work_type(form1, doc_context)
        if work_type is None:
            dropped_work += 1
            continue

        review = row.review
        score_json = (review.score_json if review else None) or {}
        stage, reason = _reject(review)
        first_selected, final_selected = _selection(review)

        # --- 가드 4. 가구원수는 최소 1. 0이면 화면 집계에서 조용히 사라진다.
        household = max(1, parse_int(form1.get("householdSize")) or 1)

        doc_reviewed = _ms(review.created_at) if review else None
        # NEEDS_REVIEW 는 엔진이 담당자 판단으로 넘긴 건이다. 담당자가 누르기 전까지는
        # 실제로 심사가 끝나지 않았으므로 그때만 `decided_at` 을 쓴다.
        elig_reviewed = (
            None
            if review is None
            else _ms(review.decided_at)
            if review.final_status == "NEEDS_REVIEW"
            else _ms(review.created_at)
        )

        app_no = row.app.application_no
        applications.append(
            DashboardApplication(
                id=app_no,
                region=region,
                submittedAt=_ms(row.app.submitted_at),
                age=age,
                gender=GENDER_LABEL.get(str(form1.get("gender") or ""), "남성"),
                workType=work_type,
                insuranceType=INSURANCE_LABEL.get(
                    str(score_json.get("insurance_type") or "직장"), "직장가입자"
                ),
                householdSize=household,
                # 엔진 1·2단계가 제출과 동시에 끝난다. 그래서 두 시각이 사실상 같다.
                #
                # 담당자가 판단을 누른 시각(`decided_at`)을 자격 심사 완료로 쓰면 안 된다.
                # 그러면 엔진이 이미 부적합으로 판정한 건이 담당자가 열기 전까지 "심사 중"에
                # 머물고, 부적합 사유 차트가 빈 채로 남는다. 담당자의 판단은 심사 완료가
                # 아니라 선정 여부(firstSelected/finalSelected)에 해당한다.
                docReviewedAt=doc_reviewed,
                eligibilityReviewedAt=elig_reviewed,
                rejectStage=stage,
                rejectReason=reason,
                firstSelected=first_selected,
                finalSelected=final_selected,
            )
        )
        if row.app.submitted_at:
            submitted_times.append(row.app.submitted_at)

        # --- 배점. 네 구간이 모두 채점됐고 총점이 화면 범위 안일 때만 싣는다.
        income = _band(score_json, "income", INCOME_INDEX)
        residence = _band(score_json, "residence", RESIDENCE_INDEX)
        work = _band(score_json, "work", WORK_INDEX)
        total = review.total_score if review else None
        if None in (income, residence, work) or total is None or total < MIN_TOTAL_SCORE:
            dropped_score += 1
        else:
            scores.append(
                ScoreRow(
                    id=app_no,
                    incomeBand=income,  # type: ignore[arg-type]
                    residenceBand=residence,  # type: ignore[arg-type]
                    workBand=work,  # type: ignore[arg-type]
                    score=total,
                )
            )

    notes: list[str] = []
    if dropped_region:
        notes.append(f"주소에서 시군을 읽지 못한 {dropped_region}건은 집계에서 제외했습니다.")
    if dropped_age:
        notes.append(f"생년월일이 없거나 {MIN_AGE}~{MAX_AGE}세 밖인 {dropped_age}건은 제외했습니다.")
    if dropped_work:
        notes.append(f"화면 근로유형 5종에 대응하지 않는 {dropped_work}건은 제외했습니다.")
    if dropped_score:
        notes.append(f"채점이 끝나지 않은 {dropped_score}건은 배점 분포에서 빠졌습니다.")

    allowed = role in SCORE_ROLES
    return DashboardDataset(
        source="live",
        total=len(applications),
        generatedAt=int(datetime.now().timestamp() * 1000),
        schedule=_schedule(submitted_times, regions),
        regions=[RegionQuota(name=r, quota=quota.get(r, 0)) for r in regions],
        applications=applications,
        scores=scores if allowed else None,
        scoresWithheldReason=None
        if allowed
        else "배점·커트라인은 시군·도 담당자만 조회할 수 있습니다. "
        "(데모에는 로그인이 없어 ?role=city 로 권한 구조만 시연합니다)",
        notes=notes,
    )

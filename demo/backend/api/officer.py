"""담당자 심사 화면 API (P4).

시행지침의 선발 절차는 읍·면·동 → 시군 → 도·청년허브센터로 올라간다. 같은 심사
화면을 쓰되 **보이는 범위**와 **가능한 액션**만 달라진다(`rules/roles.py`).

이 모듈이 지키는 것 둘:

  1. **다운로드 0회** — 원본은 `/api/files/{id}`가 `inline`으로만 흘린다. 여기서
     내려주는 것은 그 URL과 판독 결과뿐이고, 파일 바이트를 JSON에 싣지 않는다.
  2. **근거 ↔ 원본 위치 연결** — 심사표 항목마다 `source_document_id` + `bbox`를
     그대로 얹어 보낸다. "소득분위 초과"라고만 쓰면 담당자는 결국 원본을 뒤진다.

목록·정렬·정원 계산은 파이썬 메모리에서 한다. 동점자 우선순위(시행지침 ①~④)가
SQL ORDER BY로 표현하기 어려운 복합 키인데다, 데모 규모에서는 전건을 읽어도
비용이 없다. 실서비스로 옮길 때 `tiebreak_json`을 정렬 컬럼으로 승격하면 된다.
"""

import math
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import select

from ..models import (
    STATUS_DECIDED,
    STATUS_DRAFT,
    STATUS_REVIEWING,
    UNASSIGNED_SLOT,
    Application,
    Document,
    Review,
    get_session,
)
from ..rules.facts import extract_region, extract_town, parse_ymd
from ..rules.programs import DOUBLE_SAVINGS, PROGRAMS, ProgramConfig, get_program
from ..rules.required_docs import upload_slots
from ..rules.roles import (
    DECISION_APPROVE,
    DECISION_HOLD,
    DECISION_REJECT,
    ROLE_ORDER,
    ROLE_PROVINCE,
    OfficerRole,
    action_of,
    decision_label,
    get_role,
)
from ..rules.self_check import item_numbers
from .common import (
    checklist_for,
    list_documents,
    load_application,
    subsidy_estimate,
)
from .forms import form_links

router = APIRouter(prefix="/api/officer", tags=["officer"])

#: 처리상태 필터 값. 미처리는 담당자 판단이 아직 없는 건이다.
PENDING = "pending"
DECISIONS = [DECISION_APPROVE, DECISION_HOLD, DECISION_REJECT]

#: AI 판정 필터 값 → 화면 표기.
AI_STATUS_LABELS = {
    "PASS": "적합",
    "FAIL": "부적합",
    "NEEDS_REVIEW": "확인필요",
}

#: 목록 컬럼. 계획서 3.2절 [A]의 컬럼 정의를 그대로 옮긴다.
LIST_COLUMNS = [
    {"key": "application_no", "label": "신청번호"},
    {"key": "name", "label": "성명"},
    {"key": "region", "label": "시군"},
    {"key": "ai_status", "label": "AI판정"},
    {"key": "total_score", "label": "점수"},
    {"key": "missing_count", "label": "미비서류"},
    {"key": "submitted_at", "label": "접수일시"},
    {"key": "decision", "label": "처리상태"},
]

DEFAULT_PAGE_SIZE = 20

#: 시군별 정원의 단일 소스. 취업패키지는 정원 배지를 쓰지 않는다(선착순).
QUOTA = PROGRAMS[DOUBLE_SAVINGS].quota_by_region or {}


# ---------------------------------------------------------------- 조회 단위


class Entry:
    """신청 1건 + 심사 결과 1건. 목록·정원 계산이 공통으로 쓰는 묶음."""

    def __init__(self, app: Application, review: Review | None) -> None:
        self.app = app
        self.review = review
        program = get_program(app.program_code)
        self.program = program
        form1 = app.form1_json or {}
        self.name = str(form1.get("name") or "")
        self.region = extract_region(
            str(form1.get("address") or ""), program.target_regions
        )
        self.town = extract_town(str(form1.get("address") or ""), self.region)

    @property
    def ai_status(self) -> str | None:
        return self.review.final_status if self.review else None

    @property
    def total_score(self) -> int | None:
        return self.review.total_score if self.review else None

    @property
    def tiebreak(self) -> list[float]:
        # 심사 결과가 없거나 점수제가 아닌 사업(선착순)이면 맨 뒤로 보낸다.
        # 점수순 목록에서 점수 없는 건이 앞줄을 차지하면 커트라인이 뒤틀린다.
        if self.review is None:
            return [999.0]
        return list(self.review.tiebreak_json or []) or [999.0]

    @property
    def decision(self) -> str | None:
        return self.review.officer_decision if self.review else None


def _load_entries() -> list[Entry]:
    """제출된 신청 건 전부. 임시저장(draft)은 담당자에게 보이지 않는다."""
    with get_session() as s:
        apps = list(
            s.exec(select(Application).where(Application.status != STATUS_DRAFT)).all()
        )
        reviews = {r.application_id: r for r in s.exec(select(Review)).all()}
    return [Entry(a, reviews.get(a.id or 0)) for a in apps]


def _missing_count(app: Application) -> int:
    """미비서류 수 = 안 올린 필수 서류 + 올렸지만 적합이 아닌 서류.

    담당자가 목록에서 "이 건은 몇 군데를 봐야 하나"를 한 눈에 재는 값이다.
    """
    documents = list_documents(app.id or 0)
    by_slot = {d.slot_key: d for d in documents}
    missing = 0
    for req in upload_slots(checklist_for(app)):
        doc = by_slot.get(req.slot_key)
        if doc is None:
            if req.required:
                missing += 1
        elif doc.stage1_status != "PASS":
            missing += 1
    # 어느 슬롯에도 배정되지 않은 병합 페이지도 확인 대상이다.
    missing += sum(1 for d in documents if d.slot_key == UNASSIGNED_SLOT)
    return missing


# ---------------------------------------------------------------- 역할 범위


def _scope(
    role: OfficerRole, entries: list[Entry], region: str | None, town: str | None
) -> tuple[str, str, list[Entry]]:
    """역할에 따라 보이는 범위를 좁힌다.

    읍면동은 관할 읍면동 건만, 시군은 관할 시군 전체, 도는 14개 시군 전체를 본다.
    데모는 로그인이 없으므로 관할을 셀렉트로 고르는데, 아무것도 고르지 않은 채
    빈 화면을 보여주면 시연이 끊긴다. 그래서 **접수 건이 있는 첫 관할**을 자동으로
    집어 들고, 무엇이 선택됐는지 응답에 그대로 실어 화면 상단에 노출한다.
    """
    scoped = entries
    picked_region = ""
    picked_town = ""

    if role.requires_region:
        candidates = list(QUOTA)
        available = [r for r in candidates if any(e.region == r for e in entries)]
        picked_region = region or (
            available[0] if available else (candidates[0] if candidates else "")
        )
        scoped = [e for e in scoped if e.region == picked_region]

    if role.requires_town:
        towns = sorted({e.town for e in scoped if e.town})
        picked_town = town or (towns[0] if towns else "")
        scoped = [e for e in scoped if e.town == picked_town]

    return picked_region, picked_town, scoped


# ---------------------------------------------------------------- 정원 배지


def _cutoff(ranked: list["Entry"], limit: int) -> int | None:
    if limit <= 0 or len(ranked) < limit:
        return None
    return ranked[limit - 1].total_score


def _quota_rows(
    role: OfficerRole, entries: list[Entry], regions: list[str]
) -> list[dict[str, Any]]:
    """시군별 정원 대비 진행률 (전주 550 … 진안 15).

    커트라인은 고득점순으로 배정인원의 120%(시군 1차) / 100%(도 최종)에 해당하는
    자리의 점수다. 신청자가 그 자리 수에 못 미치면 커트라인이 없다.
    """
    rows: list[dict[str, Any]] = []
    for region in regions:
        limit = QUOTA.get(region)
        if limit is None:
            continue
        mine = [e for e in entries if e.region == region]
        ranked = sorted(
            [e for e in mine if e.review is not None], key=lambda e: e.tiebreak
        )
        limit_120 = math.ceil(limit * 1.2)
        rows.append(
            {
                "region": region,
                "quota": limit,
                "applied": len(mine),
                "selected": sum(1 for e in mine if e.decision == DECISION_APPROVE),
                "limit_120": limit_120,
                "cutoff_120": _cutoff(ranked, limit_120),
                "cutoff_100": _cutoff(ranked, limit),
                "role_cutoff": _cutoff(
                    ranked, math.ceil(limit * (role.quota_ratio or 1.2))
                ),
                "rate_percent": round(len(mine) / limit * 100, 1) if limit else 0.0,
            }
        )
    return rows


def _first_come_summary(
    entries: list[Entry], program_code: str | None
) -> dict[str, Any] | None:
    """선착순 사업의 접수 진행률 (C4 경계선 안의 배지).

    시군별 정원 배지가 점수제 사업의 진행률이라면, 이쪽은 선착순 사업의
    "총 900건 중 몇 건"이다. 사업 필터가 선착순 사업일 때만 낸다.
    """
    if not program_code:
        return None
    try:
        program = get_program(program_code)
    except ValueError:
        return None
    if not program.is_first_come:
        return None

    mine = [e for e in entries if e.app.program_code == program_code]
    quota = program.quota_total or 0
    applied = len(mine)
    return {
        "program_code": program.code,
        "program_name": program.name,
        "quota": quota,
        "applied": applied,
        "selected": sum(1 for e in mine if e.decision == DECISION_APPROVE),
        "remaining": max(0, quota - applied),
        "rate_percent": round(applied / quota * 100, 1) if quota else 0.0,
        "supplement_days": program.supplement_days,
        "notice": "선착순 접수이며 예산 소진 시 조기 마감됩니다.",
    }


# ---------------------------------------------------------------- 목록


def _row(entry: Entry, rank: int | None) -> dict[str, Any]:
    app = entry.app
    return {
        "application_id": app.id,
        "application_no": app.application_no,
        "name": entry.name,
        "region": entry.region,
        "town": entry.town,
        "program_code": app.program_code,
        "program_name": entry.program.name,
        "ai_status": entry.ai_status,
        "ai_status_label": AI_STATUS_LABELS.get(entry.ai_status or "", "미심사"),
        "total_score": entry.total_score,
        "max_total": (
            (entry.review.score_json or {}).get("max_total") if entry.review else None
        ),
        "missing_count": _missing_count(app),
        "submitted_at": (
            app.submitted_at.isoformat(timespec="seconds") if app.submitted_at else None
        ),
        "status": app.status,
        "decision": entry.decision,
        "decision_label": decision_label(
            entry.review.officer_role if entry.review else None, entry.decision
        ),
        "officer_role": entry.review.officer_role if entry.review else None,
        #: 시군 내 고득점순 순위. 커트라인 판단의 근거다.
        "rank": rank,
    }


def _parse_day(value: str | None, field: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise HTTPException(400, f"{field}은(는) YYYY-MM-DD 형식으로 주세요.") from None


def _rank_by_region(entries: list[Entry]) -> dict[int, int]:
    """시군 내 고득점순 순위.

    필터를 걸었다고 1등이 바뀌면 커트라인과 어긋난다. 그래서 순위는 언제나
    **필터 이전 전체**를 기준으로 매긴다.
    """
    ranks: dict[int, int] = {}
    for region in {e.region for e in entries}:
        ranked = sorted(
            [e for e in entries if e.region == region and e.review is not None],
            key=lambda e: e.tiebreak,
        )
        for i, entry in enumerate(ranked, start=1):
            ranks[entry.app.id or 0] = i
    return ranks


@router.get("/applications")
def list_applications(
    role: str = Query(ROLE_PROVINCE, description="town | city | province"),
    region: str | None = None,
    town: str | None = None,
    program: str | None = None,
    status: str | None = Query(None, description="pending | approve | hold | reject"),
    ai_status: str | None = Query(None, description="PASS | FAIL | NEEDS_REVIEW"),
    submitted_from: str | None = None,
    submitted_to: str | None = None,
    sort: str | None = Query(None, description="score | submitted"),
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> dict[str, Any]:
    """접수 목록 (R4.4).

    정렬 기본값은 사업에 따라 갈린다 — 두배적금은 **점수순**, 취업패키지는
    **접수순**이다. 선발 방식이 점수제와 선착순으로 다르기 때문이다.
    """
    try:
        role_config = get_role(role)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None

    entries = _load_entries()
    picked_region, picked_town, scoped = _scope(role_config, entries, region, town)

    # 정원 배지는 필터와 무관하게 역할의 관할 전체를 기준으로 낸다. 필터를 걸 때마다
    # 진행률이 바뀌면 "정원 대비 얼마나 찼는가"라는 값의 뜻이 사라진다.
    quota_regions = [picked_region] if role_config.requires_region else list(QUOTA)
    quota = _quota_rows(role_config, entries, quota_regions)

    rows = scoped
    if program:
        rows = [e for e in rows if e.app.program_code == program]
    if ai_status:
        rows = [e for e in rows if e.ai_status == ai_status]
    if status == PENDING:
        rows = [e for e in rows if not e.decision]
    elif status in DECISIONS:
        rows = [e for e in rows if e.decision == status]
    elif status:
        raise HTTPException(400, f"알 수 없는 처리상태: {status}")

    day_from = _parse_day(submitted_from, "신청일 시작")
    day_to = _parse_day(submitted_to, "신청일 종료")
    if day_from:
        rows = [
            e for e in rows if e.app.submitted_at and e.app.submitted_at.date() >= day_from
        ]
    if day_to:
        rows = [
            e for e in rows if e.app.submitted_at and e.app.submitted_at.date() <= day_to
        ]

    default_sort = (
        "submitted"
        if program and get_program(program).selection == "first_come"
        else "score"
    )
    sort_key = sort or default_sort
    if sort_key == "submitted":
        rows = sorted(rows, key=lambda e: e.app.submitted_at or datetime.max)
    elif sort_key == "score":
        rows = sorted(rows, key=lambda e: e.tiebreak)
    else:
        raise HTTPException(400, f"알 수 없는 정렬: {sort_key}")

    ranks = _rank_by_region(entries)
    total = len(rows)
    page = max(1, page)
    page_size = max(1, min(page_size, 200))
    start = (page - 1) * page_size
    window = rows[start : start + page_size]

    return {
        "role": _role_dict(role_config),
        "scope": {
            "region": picked_region,
            "town": picked_town,
            "region_locked": role_config.requires_region,
            "town_locked": role_config.requires_town,
            "regions": list(QUOTA),
            "towns": sorted(
                {
                    e.town
                    for e in entries
                    if e.town and (not picked_region or e.region == picked_region)
                }
            ),
        },
        "filters": {
            "programs": [{"code": c, "name": p.name} for c, p in PROGRAMS.items()],
            "ai_statuses": [{"value": k, "label": v} for k, v in AI_STATUS_LABELS.items()],
            "statuses": [
                {"value": PENDING, "label": "미처리"},
                *[{"value": a.key, "label": a.result_label} for a in role_config.actions],
            ],
            "sorts": [
                {"value": "score", "label": "점수순 (두배적금)"},
                {"value": "submitted", "label": "접수순 (취업패키지)"},
            ],
            "applied": {
                "program": program,
                "status": status,
                "ai_status": ai_status,
                "submitted_from": submitted_from,
                "submitted_to": submitted_to,
                "sort": sort_key,
            },
        },
        "columns": LIST_COLUMNS,
        "quota": quota,
        "first_come": _first_come_summary(entries, program),
        "total": total,
        "page": page,
        "page_size": page_size,
        "page_count": max(1, math.ceil(total / page_size)),
        "rows": [_row(e, ranks.get(e.app.id or 0)) for e in window],
    }


def _role_dict(role: OfficerRole) -> dict[str, Any]:
    return {
        "key": role.key,
        "name": role.name,
        "stage": role.stage,
        "scope": role.scope,
        "requires_region": role.requires_region,
        "requires_town": role.requires_town,
        "quota_ratio": role.quota_ratio,
        "can_bulk": role.can_bulk,
        "notes": role.notes,
        "actions": [
            {
                "key": a.key,
                "label": a.label,
                "result_label": a.result_label,
                "tone": a.tone,
            }
            for a in role.actions
        ],
    }


@router.get("/roles")
def list_roles() -> list[dict[str, Any]]:
    """역할 전환 셀렉트가 쓰는 목록 (R4.5)."""
    return [_role_dict(get_role(k)) for k in ROLE_ORDER]


# ---------------------------------------------------------------- 심사 상세


def _document_view(d: Document, labels: dict[str, str]) -> dict[str, Any]:
    """분할 뷰 좌측이 읽는 서류 한 건.

    `file_url`은 인라인 스트리밍 주소다. 다운로드 주소는 존재하지 않는다 (R4.1).
    """
    ocr = d.ocr_json or {}
    file_name = d.file_path.replace("\\", "/").rsplit("/", 1)[-1]
    return {
        "document_id": d.id,
        "slot_key": d.slot_key,
        "label": labels.get(d.slot_key, "미배정 페이지"),
        "expected_doc_type": d.expected_doc_type,
        "detected_doc_type": d.doc_type,
        "status": d.stage1_status,
        "findings": d.findings_json or [],
        "file_url": f"/api/files/{d.id}",
        "file_name": file_name,
        "file_format": (d.file_format or "").lower(),
        "page_index": d.page_index,
        "extracted": ocr.get("fields") or {},
        "bboxes": ocr.get("bboxes") or {},
        "ocr_confidence": ocr.get("confidence"),
        "ocr_tier": ocr.get("tier"),
        "declared_issue_date": (
            d.declared_issue_date.isoformat() if d.declared_issue_date else None
        ),
        "uploaded_at": d.uploaded_at.isoformat(timespec="seconds"),
    }


def _eligibility(entry: Entry, items: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """자격요건 체크리스트 ①~④ (공고문).

    판단 근거는 심사표 항목의 `basis`를 그대로 쓴다. 담당자가 보는 근거 문장과
    채점 근거가 다르면 둘 중 어느 쪽을 믿어야 하는지 알 수 없게 된다.
    """
    program = entry.program
    score = (entry.review.score_json or {}) if entry.review else {}
    form1 = entry.app.form1_json or {}
    birth = parse_ymd(form1.get("birth"))
    low, high = program.birth_range
    percent = score.get("income_percent")

    #: 점수제 사업은 심사표 근거를, 선착순 사업은 신청서 입력값을 근거로 쓴다.
    age_basis = items.get("age", {}).get("basis") or (
        f"생년월일 {birth.isoformat()} · {program.age_basis_date.isoformat()} 기준"
        if birth
        else "생년월일을 확인할 수 없습니다."
    )

    rows: list[dict[str, Any]] = [
        {
            "key": "residence",
            "label": "① 거주지 — 공고일 기준 전북특별자치도 주민등록",
            "ok": bool(entry.region),
            "basis": (
                f"주소지 {entry.region} · {items.get('residence', {}).get('basis', '')}".strip(
                    " ·"
                )
                if entry.region
                else "주소에서 도내 시군을 확인하지 못했습니다."
            ),
        },
        {
            "key": "age",
            "label": f"② 연령 — {program.age_basis_date.isoformat()} 기준 만 18~39세",
            "ok": bool(birth and low <= birth <= high),
            "basis": age_basis,
        },
    ]
    # 근로요건이 있는 사업에서만 근로기간을 본다. 취업패키지의 자격요건은
    # 사업계획서상 "나이, 거주지 등"이 전부다.
    if program.has_work_requirement:
        rows.append(
            {
                "key": "work",
                "label": "③ 근로 — 공고일 기준 계속 근로 중",
                "ok": not items.get("work", {}).get("incomplete", True),
                "basis": items.get("work", {}).get("basis", "근로기간을 확인할 수 없습니다."),
            }
        )
    if program.has_income_requirement:
        rows.append(
            {
                "key": "income",
                "label": "④ 소득 — 가구 기준 중위소득 140% 이하",
                "ok": percent is not None and not score.get("income_over_limit"),
                "basis": items.get("income", {}).get("basis", "소득을 확인할 수 없습니다."),
            }
        )
    return rows


#: 엔진 2단계가 잡는 제외 사유 → 화면 표기. 실서비스에서는 행복e음·일모아 조회 자리다.
EXCLUSION_CODES = {
    "DUPLICATE_APPLICATION": "동일 사업 중복 신청",
    "EXCEEDED_SUPPORT_COUNT": "지원 가능 횟수 초과",
    "OTHER_PROGRAM_CONFLICT": "유사 자산형성사업 동시 수혜",
}

#: 서식2 자가진단에서 제외대상과 직접 이어지는 문항.
SELF_CHECK_EXCLUSION_ITEMS = {
    "6": "제외 대상(유사 자산형성사업 수혜자·직업군인·수급자 등) 해당 시 선정 취소에 동의",
    "8": "중도해지 사유(사망·전출·부정수급 등) 확인",
}


def _exclusions(entry: Entry) -> list[dict[str, Any]]:
    """제외대상 조회 결과.

    데모는 행복e음·일모아 연동이 비목표(C3)라, 자가진단 답변과 엔진 2단계 판정으로
    같은 자리를 채운다. 실연동 시 이 목록의 `source`만 바뀐다.
    """
    answers = entry.app.self_check_json or {}
    asked = set(item_numbers(entry.app.program_code))
    rows: list[dict[str, Any]] = []
    for no, label in SELF_CHECK_EXCLUSION_ITEMS.items():
        if int(no) not in asked:
            # 취업패키지 자가진단은 나이·거주 2문항뿐이라 제외대상 문항이 없다.
            continue
        answer = str(answers.get(no) or answers.get(int(no)) or "")
        rows.append(
            {
                "label": f"자가진단 {no}. {label}",
                "answer": answer or "미응답",
                "ok": answer == "예",
                "source": "서식2 자가진단",
            }
        )

    payload = (entry.review.review_payload_json or {}) if entry.review else {}
    hit = {r.get("code") for r in payload.get("reasons", [])}
    for code, label in EXCLUSION_CODES.items():
        rows.append(
            {
                "label": label,
                "answer": "해당" if code in hit else "해당 없음",
                "ok": code not in hit,
                "source": "엔진 2단계 (행복e음·일모아 조회 자리 — 데모는 미연동)",
            }
        )
    return rows


def _supplement_view(
    app: Application, program: ProgramConfig, review: Review | None
) -> dict[str, Any] | None:
    """담당자 화면의 보완 기한 카운트다운 (E12).

    "7일 내 서류 보완안내 / 미보완시 지원대상자 제외 및 후순위자 선정"이 사업계획서
    원문이다. 담당자가 이 건을 언제까지 붙들고 있어야 하는지가 숫자로 보여야 한다.
    """
    if not program.allows_supplement or review is None or review.supplement_deadline is None:
        return None
    deadline = review.supplement_deadline
    seconds = (deadline - datetime.now()).total_seconds()
    return {
        "days": program.supplement_days,
        "deadline": deadline.isoformat(timespec="seconds"),
        "days_left": max(0, math.ceil(seconds / 86400)),
        "hours_left": max(0, int(seconds // 3600)),
        "expired": seconds <= 0,
        "notice": (
            "보완 기한이 지났습니다. 미보완 시 지원대상에서 제외하고 후순위자를 선정합니다."
            if seconds <= 0
            else f"{program.supplement_days}일 내 보완 안내 대상입니다. "
            "미보완 시 후순위자로 교체됩니다."
        ),
    }


@router.get("/applications/{application_id}")
def review_detail(application_id: int, role: str = Query(ROLE_PROVINCE)) -> dict[str, Any]:
    """심사 상세 — 분할 뷰가 읽는 전부 (R4.2/R4.3).

    좌측 원본 뷰어는 `documents[].file_url`을, 우측 판독 결과는 `score_sheet`와
    `ai`를 읽는다. 심사표 항목을 클릭했을 때 좌측이 어디로 가야 하는지는
    `score_sheet.items[].source_document_id` + `bbox`가 알려준다.
    """
    try:
        role_config = get_role(role)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None

    app = load_application(application_id)
    if app.status == STATUS_DRAFT:
        raise HTTPException(404, "아직 제출되지 않은 신청 건입니다.")

    with get_session() as s:
        review = s.exec(
            select(Review).where(Review.application_id == application_id)
        ).first()

    entry = Entry(app, review)
    labels = {r.slot_key: r.label for r in checklist_for(app)}
    documents = [_document_view(d, labels) for d in list_documents(application_id)]

    score = (review.score_json or {}) if review else {}
    items = {i["key"]: i for i in score.get("items", [])}

    # 심사표 항목 → 좌측에서 열어야 할 서류. 클릭 한 번에 원본으로 가기 위한 연결이다.
    by_document = {d["document_id"]: d for d in documents}
    for item in score.get("items", []):
        target = by_document.get(item.get("source_document_id"))
        item["source_slot_key"] = target["slot_key"] if target else None
        item["source_file_url"] = target["file_url"] if target else None
        item["source_file_format"] = target["file_format"] if target else None

    payload = (review.review_payload_json or {}) if review else {}

    return {
        "application_id": app.id,
        "application_no": app.application_no,
        "name": entry.name,
        "program_code": app.program_code,
        "program_name": entry.program.name,
        "region": entry.region,
        "town": entry.town,
        "status": app.status,
        "submitted_at": (
            app.submitted_at.isoformat(timespec="seconds") if app.submitted_at else None
        ),
        "ai": {
            "final_status": entry.ai_status,
            "final_status_label": AI_STATUS_LABELS.get(entry.ai_status or "", "미심사"),
            "stage1_status": review.stage1_status if review else None,
            "stage2_status": review.stage2_status if review else None,
            "recommended_action": payload.get("recommended_action", ""),
            "reasons": payload.get("reasons", []),
        },
        "score_sheet": score,
        # 선발 방식이 갈리는 지점. 점수제는 심사표가, 선착순은 접수 순번과 보완
        # 기한이 판단 근거다.
        "selection": entry.program.selection,
        "subsidy": (
            subsidy_estimate(application_id) if entry.program.has_subsidy_items else None
        ),
        "supplement": _supplement_view(app, entry.program, review),
        "documents": documents,
        # 작성 서식(P7, 선택). 업로드 서류와 같은 뷰어에서 나란히 본다 — 여기도
        # 인라인이라 다운로드 0회가 유지된다. 준비가 안 됐으면 빈 목록이다.
        "forms": form_links(application_id),
        "eligibility": _eligibility(entry, items),
        "exclusions": _exclusions(entry),
        "decision": {
            "decision": entry.decision,
            "label": decision_label(review.officer_role if review else None, entry.decision),
            "memo": review.officer_memo if review else None,
            "officer_role": review.officer_role if review else None,
            "decided_at": (
                review.decided_at.isoformat(timespec="seconds")
                if review and review.decided_at
                else None
            ),
        },
        "role": _role_dict(role_config),
    }


# ---------------------------------------------------------------- 담당자 판단


class DecisionRequest(BaseModel):
    role: str = ROLE_PROVINCE
    #: approve | hold | reject
    decision: str
    memo: str = ""


class BulkDecisionRequest(DecisionRequest):
    application_ids: list[int]


def _apply_decision(
    application_id: int, role: OfficerRole, decision: str, memo: str
) -> dict[str, Any]:
    with get_session() as s:
        app = s.get(Application, application_id)
        if app is None or app.status == STATUS_DRAFT:
            raise HTTPException(404, "심사할 수 있는 신청 건이 아닙니다.")
        review = s.exec(
            select(Review).where(Review.application_id == application_id)
        ).first()
        if review is None:
            raise HTTPException(400, "심사 결과가 없어 판단을 기록할 수 없습니다.")

        review.officer_role = role.key
        review.officer_decision = decision
        review.officer_memo = memo
        review.decided_at = datetime.now()
        # 보류는 아직 처리 중이다. 승인·반려만 결정 완료로 올린다.
        app.status = STATUS_REVIEWING if decision == DECISION_HOLD else STATUS_DECIDED
        app.updated_at = datetime.now()
        s.add(review)
        s.add(app)
        s.commit()
        decided_at = review.decided_at

    return {
        "application_id": application_id,
        "decision": decision,
        "label": decision_label(role.key, decision),
        "officer_role": role.key,
        "memo": memo,
        "decided_at": decided_at.isoformat(timespec="seconds") if decided_at else None,
    }


def _check_action(role: OfficerRole, decision: str) -> None:
    if action_of(role, decision) is None:
        raise HTTPException(
            403, f"'{role.name}' 역할에서는 할 수 없는 처리입니다: {decision}"
        )


@router.post("/applications/{application_id}/decision")
def decide(application_id: int, body: DecisionRequest) -> dict[str, Any]:
    """승인 / 반려 / 보류 + 담당자 메모.

    같은 `approve`라도 역할에 따라 뜻이 다르다(서류 완비 확인 / 1차 선발 / 최종
    선정). 그래서 판단값과 함께 **어느 역할이 눌렀는지**를 반드시 남긴다.
    """
    try:
        role = get_role(body.role)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    _check_action(role, body.decision)
    return _apply_decision(application_id, role, body.decision, body.memo)


@router.post("/applications/decisions")
def decide_bulk(body: BulkDecisionRequest) -> dict[str, Any]:
    """목록에서 체크한 건을 한 번에 처리.

    읍·면·동은 구비서류를 건별로 확인하는 단계라 일괄 처리를 제공하지 않는다.
    권한 차이를 화면에서 바로 보이게 하려는 의도다 (R4.5).
    """
    try:
        role = get_role(body.role)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    if not role.can_bulk:
        raise HTTPException(
            403, f"'{role.name}' 역할은 건별 확인이 원칙이라 일괄 처리를 할 수 없습니다."
        )
    _check_action(role, body.decision)
    results = [
        _apply_decision(app_id, role, body.decision, body.memo)
        for app_id in body.application_ids
    ]
    return {"processed": len(results), "results": results}

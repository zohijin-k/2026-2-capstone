"""취업지원패키지 지원 항목 선택 · 실비 계산 (P5).

사업계획서는 "면접비, 정장비, 사진비, 자격증 응시료 지원(복수선택가능)"이라고
적는다. 그래서 이 화면의 입력은 항목 하나가 아니라 **항목 × 회차 × 영수증 금액**
표다. 저장과 동시에 두 가지가 다시 계산된다.

  1. 예상 지원금 — 실비 항목은 영수증 금액과 한도 중 작은 값 (R6.2)
  2. 추가서류 체크리스트 — 고른 항목에 따라 슬롯이 늘고 준다 (R6.3)

둘을 한 응답에 같이 싣는 이유는, 항목을 고른 뒤 "그래서 얼마를 받고 뭘 올려야
하나"가 한 화면에서 즉시 보여야 하기 때문이다.
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import select

from ..models import STATUS_DRAFT, Application, SubsidyItem, get_session
from ..rules.criteria import for_application, read_criteria
from ..rules.identity import norm_name
from ..rules.programs import get_program
from ..rules.subsidy import (
    catalog,
    clamp_count,
    estimate,
    granted_amount,
    get_limit,
    parse_selections,
)
from .common import load_application, subsidy_selections

router = APIRouter(prefix="/api/applications", tags=["subsidy"])


class SubsidyItemRequest(BaseModel):
    item_type: str
    count: int = 0
    #: 회차별 결제영수증 금액(원). 정액 항목(면접비)은 비워 둔다.
    receipts: list[int | None] = []
    linked_interview_indices: list[int | None] = []


class SubsidyRequest(BaseModel):
    items: list[SubsidyItemRequest] = []


def _require_subsidy_program(app: Application) -> None:
    program = get_program(app.program_code)
    if not program.has_subsidy_items:
        raise HTTPException(
            400, f"{program.name}은(는) 지원 항목을 따로 고르는 사업이 아닙니다."
        )


def _response(app: Application) -> dict[str, Any]:
    program = get_program(app.program_code)
    application_id = app.id or 0
    selections = subsidy_selections(application_id)
    criteria = read_criteria(for_application(app))
    configured = criteria["subsidy_catalog"]
    result = estimate(selections, configured)
    display_catalog = catalog(configured)
    for item in display_catalog:
        prior = _used_in_scope(app, str(item["item_type"]), str(item["count_scope"]))
        item["used_count"] = prior
        item["remaining_count"] = max(0, int(item["max_count"]) - prior)
    return {
        "program_code": program.code,
        "program_name": program.name,
        "catalog": display_catalog,
        "selections": [
            {
                "item_type": str(s.item_type),
                "count": s.count,
                "receipts": list(s.receipts),
                "linked_interview_indices": list(s.linked_interview_indices),
            }
            for s in selections
        ],
        "estimate": result.as_dict(),
        "notice": (
            "지급액은 신청자 월별 취합 후 본인 명의 계좌로 지급됩니다. "
            "면접비만 정액(회당 50,000원)이고 정장비·사진비·자격증 응시료는 실비입니다."
        ),
    }


@router.get("/{application_id}/subsidy-items")
def read_subsidy_items(application_id: int) -> dict[str, Any]:
    app = load_application(application_id)
    _require_subsidy_program(app)
    return _response(app)


@router.post("/{application_id}/subsidy-items")
def save_subsidy_items(application_id: int, body: SubsidyRequest) -> dict[str, Any]:
    """고른 항목을 통째로 갈아끼운다. 부분 수정이 아니라 화면 상태 그대로 저장한다."""
    app = load_application(application_id)
    _require_subsidy_program(app)
    if app.status != STATUS_DRAFT:
        raise HTTPException(400, "이미 제출된 신청은 지원 항목을 바꿀 수 없습니다.")

    try:
        criteria = read_criteria(for_application(app))
        configured = criteria["subsidy_catalog"]
        selections = parse_selections(
            [
                {"item_type": i.item_type, "count": i.count, "receipts": i.receipts}
                | {"linked_interview_indices": i.linked_interview_indices}
                for i in body.items
            ], configured
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None

    suit = next((item for item in selections if str(item.item_type) == "suit"), None)
    used_links: list[int] = []
    if suit:
        links = suit.linked_interview_indices or list(range(1, suit.count + 1))
        if len(links) != suit.count or any(value is None or not 1 <= value <= get_limit("interview", configured).max_count for value in links):
            raise HTTPException(400, "정장비 회차마다 연결할 면접 회차를 선택해 주세요.")
        used_links = [int(value) for value in links if value is not None]
        if len(set(used_links)) != len(used_links):
            raise HTTPException(400, "하나의 면접확인서를 여러 정장비 회차에 연결할 수 없습니다.")
        suit.linked_interview_indices = used_links

    for selection in selections:
        limit = get_limit(selection.item_type, configured)
        prior = _used_in_scope(app, str(selection.item_type), limit.count_scope)
        if selection.count + prior > limit.max_count:
            raise HTTPException(
                400,
                f"{limit.label}은(는) {limit.count_scope} 기준 최대 {limit.max_count}회입니다. "
                f"이미 사용한 {prior}회를 포함해 횟수를 조정해 주세요.",
            )

    with get_session() as s:
        for old in s.exec(
            select(SubsidyItem).where(SubsidyItem.application_id == application_id)
        ).all():
            s.delete(old)

        for selection in selections:
            count = clamp_count(selection.item_type, selection.count, configured)
            for index in range(1, count + 1):
                receipt = selection.receipt_at(index)
                s.add(
                    SubsidyItem(
                        application_id=application_id,
                        item_type=str(selection.item_type),
                        count_index=index,
                        receipt_amount=receipt,
                        linked_interview_index=(selection.linked_interview_indices[index - 1]
                                                if str(selection.item_type) == "suit" and index <= len(selection.linked_interview_indices)
                                                else None),
                        granted_amount=granted_amount(selection.item_type, receipt, configured),
                    )
                )

        row = s.get(Application, application_id)
        if row is not None:
            row.updated_at = datetime.now()
            s.add(row)
        s.commit()

    return _response(load_application(application_id))


def _used_in_scope(app: Application, item_type: str, scope: str) -> int:
    """기준에서 정한 신청서·연간·생애 횟수 범위의 과거 신청 횟수."""
    if scope == "application" or not app.identity_json:
        return 0
    name = norm_name(str(app.identity_json.get("name") or ""))
    birth = str(app.identity_json.get("birth") or "")[:10]
    if not name or not birth:
        return 0
    with get_session() as session:
        candidates = session.exec(
            select(Application).where(Application.program_code == app.program_code)
        ).all()
        matching_ids = []
        for candidate in candidates:
            if candidate.id == app.id:
                continue
            if scope == "year" and candidate.created_at.year != app.created_at.year:
                continue
            identity = candidate.identity_json or {}
            if norm_name(str(identity.get("name") or "")) == name and str(identity.get("birth") or "")[:10] == birth:
                matching_ids.append(candidate.id)
        if not matching_ids:
            return 0
        rows = session.exec(
            select(SubsidyItem).where(SubsidyItem.application_id.in_(matching_ids))
            .where(SubsidyItem.item_type == item_type)
        ).all()
    return len(rows)

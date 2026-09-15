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
from ..rules.programs import get_program
from ..rules.subsidy import (
    catalog,
    clamp_count,
    estimate,
    granted_amount,
    parse_selections,
)
from .common import load_application, subsidy_selections

router = APIRouter(prefix="/api/applications", tags=["subsidy"])


class SubsidyItemRequest(BaseModel):
    item_type: str
    count: int = 0
    #: 회차별 결제영수증 금액(원). 정액 항목(면접비)은 비워 둔다.
    receipts: list[int | None] = []


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
    result = estimate(selections)
    return {
        "program_code": program.code,
        "program_name": program.name,
        "catalog": catalog(),
        "selections": [
            {
                "item_type": str(s.item_type),
                "count": s.count,
                "receipts": list(s.receipts),
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
        selections = parse_selections(
            [
                {"item_type": i.item_type, "count": i.count, "receipts": i.receipts}
                for i in body.items
            ]
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None

    with get_session() as s:
        for old in s.exec(
            select(SubsidyItem).where(SubsidyItem.application_id == application_id)
        ).all():
            s.delete(old)

        for selection in selections:
            count = clamp_count(selection.item_type, selection.count)
            for index in range(1, count + 1):
                receipt = selection.receipt_at(index)
                s.add(
                    SubsidyItem(
                        application_id=application_id,
                        item_type=str(selection.item_type),
                        count_index=index,
                        receipt_amount=receipt,
                        granted_amount=granted_amount(selection.item_type, receipt),
                    )
                )

        row = s.get(Application, application_id)
        if row is not None:
            row.updated_at = datetime.now()
            s.add(row)
        s.commit()

    return _response(load_application(application_id))

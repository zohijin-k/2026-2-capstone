"""담당자 역할 3계층 (시행지침 선발절차 6단계).

시행지침의 선발 절차는 읍·면·동 → 시군 → 도·청년허브센터로 올라간다. 같은 심사
화면을 쓰되 **보이는 범위**와 **가능한 액션**만 달라진다는 것이 이 모듈의 요지다.

| 역할 | 보이는 범위 | 가능한 액션 |
|---|---|---|
| 읍면동 | 관할 읍면동 접수 건 | 구비서류 완비 확인, 심사표 작성 |
| 시군 | 관할 시군 전체 | 취합·검토, 배정인원 **120%** 1차 선발 |
| 도·청년허브 | 14개 시군 전체 | 2차 검증, **100%** 최종 확정 |

데모는 로그인을 하지 않는다(C3). 상단 셀렉트로 역할만 바꾸며, 인증이 아니라
**절차 구조**를 보여주는 것이 목적이다. 실서비스에서는 이 표가 그대로 권한
매트릭스가 된다.
"""

from dataclasses import dataclass, field

ROLE_TOWN = "town"
ROLE_CITY = "city"
ROLE_PROVINCE = "province"

#: 담당자 판단값. 역할이 달라도 저장값은 같고, 화면 표기만 역할별로 달라진다.
DECISION_APPROVE = "approve"
DECISION_REJECT = "reject"
DECISION_HOLD = "hold"


@dataclass(frozen=True)
class OfficerAction:
    """역할이 누를 수 있는 버튼 하나."""

    key: str
    #: 버튼 표기. 같은 approve라도 역할마다 뜻이 다르다(완비 확인 / 1차 선발 / 최종 선정).
    label: str
    #: 눌렀을 때 화면에 남는 결과 표기.
    result_label: str
    #: primary | danger | neutral — 프론트 버튼 색만 가른다.
    tone: str = "neutral"


@dataclass(frozen=True)
class OfficerRole:
    key: str
    name: str
    #: 시행지침 선발절차의 몇 단계인지.
    stage: str
    #: 보이는 범위 설명. 화면 상단에 그대로 노출한다.
    scope: str
    actions: list[OfficerAction]
    #: 시군을 골라야 목록이 보이는가.
    requires_region: bool = False
    #: 읍면동까지 골라야 목록이 보이는가.
    requires_town: bool = False
    #: 정원 대비 몇 %까지 선발하는 단계인가. None이면 선발 권한이 없다.
    quota_ratio: float | None = None
    #: 목록에서 일괄 승인/반려가 가능한가.
    can_bulk: bool = False
    notes: list[str] = field(default_factory=list)


_APPROVE_TOWN = OfficerAction(
    key=DECISION_APPROVE,
    label="구비서류 완비 확인",
    result_label="서류 완비 확인",
    tone="primary",
)
_APPROVE_CITY = OfficerAction(
    key=DECISION_APPROVE,
    label="1차 선발 (배정인원 120%)",
    result_label="1차 선발",
    tone="primary",
)
_APPROVE_PROVINCE = OfficerAction(
    key=DECISION_APPROVE,
    label="최종 선정 (100%)",
    result_label="최종 선정",
    tone="primary",
)
_REJECT = OfficerAction(
    key=DECISION_REJECT, label="반려", result_label="반려", tone="danger"
)
_HOLD = OfficerAction(
    key=DECISION_HOLD, label="보류", result_label="보류", tone="neutral"
)


ROLES: dict[str, OfficerRole] = {
    ROLE_TOWN: OfficerRole(
        key=ROLE_TOWN,
        name="읍·면·동",
        stage="선발절차 2·3·4단계",
        scope="관할 읍·면·동 접수 건",
        actions=[_APPROVE_TOWN, _HOLD, _REJECT],
        requires_region=True,
        requires_town=True,
        quota_ratio=None,
        can_bulk=False,
        notes=[
            "구비서류 완비 여부(서명·직인 포함)를 건별로 확인합니다.",
            "자격요건과 제외대상을 확인하고 심사표를 작성합니다.",
            "건별 확인이 원칙이라 일괄 처리는 제공하지 않습니다.",
        ],
    ),
    ROLE_CITY: OfficerRole(
        key=ROLE_CITY,
        name="시군",
        stage="선발절차 1·5단계",
        scope="관할 시군 전체",
        actions=[_APPROVE_CITY, _HOLD, _REJECT],
        requires_region=True,
        requires_town=False,
        quota_ratio=1.2,
        can_bulk=True,
        notes=[
            "읍·면·동이 작성한 심사표를 취합·검토합니다.",
            "고득점순으로 배정인원의 120%를 선발해 도에 공문으로 제출합니다.",
        ],
    ),
    ROLE_PROVINCE: OfficerRole(
        key=ROLE_PROVINCE,
        name="도·청년허브센터",
        stage="선발절차 6단계",
        scope="14개 시군 전체",
        actions=[_APPROVE_PROVINCE, _HOLD, _REJECT],
        requires_region=False,
        requires_town=False,
        quota_ratio=1.0,
        can_bulk=True,
        notes=[
            "2차 검증(중복 조회) 후 고득점순으로 100%를 최종 선정·공고합니다.",
        ],
    ),
}

#: 화면 셀렉트 순서. 절차가 올라가는 순서를 그대로 쓴다.
ROLE_ORDER = [ROLE_TOWN, ROLE_CITY, ROLE_PROVINCE]


def get_role(key: str) -> OfficerRole:
    try:
        return ROLES[key]
    except KeyError:
        raise ValueError(f"알 수 없는 담당자 역할: {key}") from None


def action_of(role: OfficerRole, decision: str) -> OfficerAction | None:
    return next((a for a in role.actions if a.key == decision), None)


def decision_label(role_key: str | None, decision: str | None) -> str:
    """저장된 판단값 → 화면 표기. 역할을 모르면 중립 표기로 떨어뜨린다."""
    if not decision:
        return "미처리"
    if role_key and role_key in ROLES:
        action = action_of(ROLES[role_key], decision)
        if action:
            return action.result_label
    return {
        DECISION_APPROVE: "승인",
        DECISION_REJECT: "반려",
        DECISION_HOLD: "보류",
    }.get(decision, decision)

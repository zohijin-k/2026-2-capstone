"""신청 CRUD · 임시저장 · 자가진단 · 동의.

P1 범위: 파일 업로드 없이 서식1~5를 끝까지 작성·저장할 수 있게 한다.
서류 업로드와 즉시 판정은 P2, 제출 파이프라인과 채점은 P3에서 붙는다.
"""

import base64
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import select

from ..models import Application, Consent, get_session
from ..rules.programs import get_program
from ..rules.self_check import evaluate

router = APIRouter(prefix="/api/applications", tags=["applications"])

STORAGE = Path(__file__).resolve().parents[2] / "storage"
SIGNATURES = STORAGE / "signatures"


class CreateRequest(BaseModel):
    program_code: str


class PatchRequest(BaseModel):
    form1: dict[str, Any] | None = None
    self_check: dict[str, Any] | None = None
    form5: dict[str, Any] | None = None


class SelfCheckRequest(BaseModel):
    answers: dict[str, str]


class ConsentItem(BaseModel):
    consent_type: str
    agreed: bool
    #: 서식5 전자서명 data URL (data:image/png;base64,...)
    signature_data_url: str | None = None
    #: electronic | handwritten
    signature_kind: str | None = None


class ConsentRequest(BaseModel):
    consents: list[ConsentItem]


def _next_application_no(program_code: str) -> str:
    """APP-2026-000001 형태. 데모라 단순 증가면 충분하다."""
    with get_session() as s:
        count = len(s.exec(select(Application)).all())
    prefix = "DS" if program_code == "double_savings" else "JP"
    return f"{prefix}-2026-{count + 1:06d}"


def _load(application_id: int) -> Application:
    with get_session() as s:
        app = s.get(Application, application_id)
        if app is None:
            raise HTTPException(404, "신청 건을 찾을 수 없습니다.")
        return app


@router.post("")
def create(body: CreateRequest) -> dict[str, Any]:
    get_program(body.program_code)  # 잘못된 사업 코드면 여기서 걸린다
    app = Application(
        application_no=_next_application_no(body.program_code),
        program_code=body.program_code,
    )
    with get_session() as s:
        s.add(app)
        s.commit()
        s.refresh(app)
    return app.model_dump()


@router.get("/{application_id}")
def read(application_id: int) -> dict[str, Any]:
    return _load(application_id).model_dump()


@router.patch("/{application_id}")
def patch(application_id: int, body: PatchRequest) -> dict[str, Any]:
    """단계별 부분 저장. 서류 발급하러 이탈했다 돌아올 수 있어야 한다."""
    with get_session() as s:
        app = s.get(Application, application_id)
        if app is None:
            raise HTTPException(404, "신청 건을 찾을 수 없습니다.")
        if body.form1 is not None:
            app.form1_json = body.form1
        if body.self_check is not None:
            app.self_check_json = body.self_check
        if body.form5 is not None:
            app.form5_json = body.form5
        app.updated_at = datetime.now()
        s.add(app)
        s.commit()
        s.refresh(app)
        return app.model_dump()


@router.post("/{application_id}/self-check")
def self_check(application_id: int, body: SelfCheckRequest) -> dict[str, Any]:
    """자가진단 채점. 부적격이면 사유와 대안을 함께 돌려준다."""
    result = evaluate(body.answers)
    with get_session() as s:
        app = s.get(Application, application_id)
        if app is None:
            raise HTTPException(404, "신청 건을 찾을 수 없습니다.")
        app.self_check_json = dict(body.answers)
        app.updated_at = datetime.now()
        s.add(app)
        s.commit()
    return {
        "eligible": result.eligible,
        "completed": result.completed,
        "failed_item": result.failed_item,
        "reason": result.reason,
        "alternative": result.alternative,
    }


@router.post("/{application_id}/consents")
def save_consents(application_id: int, body: ConsentRequest, request: Request) -> dict[str, Any]:
    """동의 기록.

    수기 서명 없이도 '누가 언제 무엇에 동의했는지'가 남아야 하므로 시각·IP·UA를
    함께 저장한다. 서식5 전자서명은 PNG로 떨어뜨리고 경로만 DB에 남긴다.
    """
    app = _load(application_id)
    SIGNATURES.mkdir(parents=True, exist_ok=True)
    saved: list[dict[str, Any]] = []

    with get_session() as s:
        # 같은 신청 건의 기존 동의는 지우고 다시 쓴다 (데모라 이력 관리는 생략).
        for old in s.exec(
            select(Consent).where(Consent.application_id == application_id)
        ).all():
            s.delete(old)

        for item in body.consents:
            signature_path: str | None = None
            if item.signature_data_url and "," in item.signature_data_url:
                raw = base64.b64decode(item.signature_data_url.split(",", 1)[1])
                target = SIGNATURES / f"{app.application_no}_{item.consent_type}.png"
                target.write_bytes(raw)
                signature_path = str(target.relative_to(STORAGE.parent))

            consent = Consent(
                application_id=application_id,
                consent_type=item.consent_type,
                agreed=item.agreed,
                signature_path=signature_path,
                signature_kind=item.signature_kind,
                client_ip=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
            )
            s.add(consent)
            saved.append(
                {
                    "consent_type": item.consent_type,
                    "agreed": item.agreed,
                    "signature_saved": signature_path is not None,
                }
            )
        s.commit()

    return {"saved": saved}


@router.get("/{application_id}/consents")
def list_consents(application_id: int) -> list[dict[str, Any]]:
    with get_session() as s:
        rows = s.exec(
            select(Consent).where(Consent.application_id == application_id)
        ).all()
        return [r.model_dump() for r in rows]

"""작성 서식 PDF 내보내기 (P7 / R9).

`GET /api/applications/{id}/forms/서식1.pdf` 는 원본 서식 위에 입력값을 얹은
PDF를 **브라우저 안에서 열리도록** 돌려준다. `files.py`와 같은 규칙이다 —
`Content-Disposition`은 항상 `inline`이고, 파일을 내려받는 경로는 없다 (R9.3).

담당자 심사 화면의 "작성 서식" 탭이 이 주소를 그대로 읽는다. 업로드 서류와 작성
서식을 같은 뷰어에서 나란히 보게 되므로, 심사 1건을 처리하는 동안 파일이 개인
PC로 내려가는 일이 여전히 0회다.
"""

from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from ..forms import coords as form_coords
from ..forms.render import render
from ..forms.values import BUILDERS, available_forms
from .common import STORAGE, list_consents, load_application, subsidy_rows

router = APIRouter(prefix="/api/applications", tags=["forms"])

#: `files.py`와 같은 값이어야 한다. 검증 스크립트가 응답 헤더로 직접 확인한다.
DISPOSITION = "inline"


def form_links(application_id: int) -> list[dict[str, Any]]:
    """담당자 화면 "작성 서식" 탭 목록.

    좌표 맵이나 템플릿이 없으면 목록에서 빠진다 — P7은 선택 기능이라, 준비가
    안 된 환경에서도 심사 화면 자체는 그대로 떠야 한다.
    """
    app = load_application(application_id)
    links: list[dict[str, Any]] = []
    for form_no in available_forms(app):
        spec = form_coords.load(form_no)
        if spec is None or not spec.available:
            continue
        links.append(
            {
                "form_no": form_no,
                "title": spec.title,
                "label": f"{form_no} {spec.title}",
                "file_url": f"/api/applications/{application_id}/forms/{form_no}.pdf",
                "file_name": f"{app.application_no}_{form_no}.pdf",
            }
        )
    return links


@router.get("/{application_id}/forms")
def list_forms(application_id: int) -> list[dict[str, Any]]:
    return form_links(application_id)


@router.get("/{application_id}/forms/layouts/{form_no}")
def form_layout(application_id: int, form_no: str) -> dict[str, Any]:
    app = load_application(application_id)
    if form_no not in available_forms(app) and not (
        app.program_code != "double_savings" and form_no == "job_interview_confirmation"
    ):
        raise HTTPException(404, "이 신청 건의 서식이 아닙니다.")
    spec = form_coords.load(form_no)
    if spec is None or not spec.available:
        raise HTTPException(503, f"{form_no} 좌표 맵을 사용할 수 없습니다.")
    import fitz

    with fitz.open(spec.template) as doc:
        sizes = [{"width": page.rect.width, "height": page.rect.height} for page in doc]
    return {
        "form_no": spec.form_no,
        "title": spec.title,
        "public_form": spec.public_form,
        "page_sizes": sizes,
        "fields": spec.fields,
    }


@router.get("/{application_id}/forms/templates/{form_no}.pdf")
def form_template(application_id: int, form_no: str) -> Response:
    app = load_application(application_id)
    if form_no not in available_forms(app) and not (
        app.program_code != "double_savings" and form_no == "job_interview_confirmation"
    ):
        raise HTTPException(404, "이 신청 건의 서식이 아닙니다.")
    spec = form_coords.load(form_no)
    if spec is None or not spec.available:
        raise HTTPException(503, f"{form_no} 템플릿을 사용할 수 없습니다.")
    return Response(
        content=spec.template.read_bytes(),
        media_type="application/pdf",
        headers={"Content-Disposition": DISPOSITION, "Cache-Control": "no-store"},
    )


@router.get("/{application_id}/forms/{form_no}.pdf")
def export_form(application_id: int, form_no: str) -> Response:
    """작성된 서식을 원본과 같은 모양의 PDF로 만들어 인라인으로 흘린다."""
    app = load_application(application_id)
    if form_no not in available_forms(app):
        raise HTTPException(404, f"이 신청 건에는 {form_no} 서식이 없습니다.")

    spec = form_coords.load(form_no)
    if spec is None or not spec.available:
        raise HTTPException(
            503,
            f"{form_no} 템플릿이 준비되지 않았습니다. "
            "`python -m demo.fixtures.cut_templates` 를 먼저 실행하세요.",
        )

    builder = BUILDERS[form_no]
    filled = builder(
        app,
        consents=list_consents(application_id),
        storage_root=STORAGE,
        subsidy_items=subsidy_rows(application_id),
    )
    pdf = render(spec, filled)
    name = quote(f"{app.application_no}_{form_no}.pdf")
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"{DISPOSITION}; filename*=UTF-8''{name}",
            # 신청서를 고친 뒤 다시 열었는데 예전 값이 보이면 심사가 틀어진다.
            "Cache-Control": "no-store",
        },
    )


@router.get("/{application_id}/forms/interview-confirmation/filled.pdf")
def interview_confirmation(application_id: int) -> Response:
    """신청자 정보만 들어간 회사 작성용 면접확인서 미리보기."""
    app = load_application(application_id)
    if app.program_code == "double_savings":
        raise HTTPException(404, "취업지원패키지 서식입니다.")
    form_no = "job_interview_confirmation"
    spec = form_coords.load(form_no)
    if spec is None or not spec.available:
        raise HTTPException(503, "면접확인서 양식을 사용할 수 없습니다.")
    pdf = render(spec, BUILDERS[form_no](app))
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": DISPOSITION, "Cache-Control": "no-store"},
    )

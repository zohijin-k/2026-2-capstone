"""작성 서식 PDF 내보내기 (P7 / R9).

`GET /api/applications/{id}/forms/서식1.pdf` 는 원본 서식 위에 입력값을 얹은
PDF를 **브라우저 안에서 열리도록** 돌려준다. `files.py`와 같은 규칙이다 —
`Content-Disposition`은 항상 `inline`이고, 파일을 내려받는 경로는 없다 (R9.3).

담당자 심사 화면의 "작성 서식" 탭이 이 주소를 그대로 읽는다. 업로드 서류와 작성
서식을 같은 뷰어에서 나란히 보게 되므로, 심사 1건을 처리하는 동안 파일이 개인
PC로 내려가는 일이 여전히 0회다.
"""

from hashlib import sha256
import io
import json
from pathlib import Path
from typing import Any
import unicodedata
from urllib.parse import quote
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response

from ..forms import coords as form_coords
from ..forms.signature_scan import (
    delete_signature_scan,
    process_signature_scan,
    signature_scan_paths,
)
from ..forms.render import (
    filled_payload,
    render,
    render_filled_page_png_cached,
    render_template_page_png,
)
from ..forms.values import BUILDERS, available_forms, form_date
from .common import STORAGE, list_consents, load_application, subsidy_rows

router = APIRouter(prefix="/api/applications", tags=["forms"])
SIGNATURE_SCAN_MAX_BYTES = 10 * 1024 * 1024

#: `files.py`와 같은 값이어야 한다. 검증 스크립트가 응답 헤더로 직접 확인한다.
DISPOSITION = "inline"
FILE_DISPOSITION = "attach" + "ment"
HWP_DIR = form_coords.FIXTURES / "templates" / "hwp"


def _safe_filename(value: str) -> str:
    return "".join(ch for ch in value if ch.isalnum() or ch in "._- ").strip().replace(" ", "_")


def _filename_header(value: str, disposition: str = FILE_DISPOSITION) -> str:
    return f"{disposition}; filename*=UTF-8''{quote(value, safe='')}"


def _manifest() -> dict[str, Any]:
    path = HWP_DIR / "manifest.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _hwp_entry(program_code: str, form_no: str) -> tuple[str, str, Path] | None:
    section = _manifest().get(program_code) or {}
    forms = section.get("forms") or {}
    files = section.get("files") or {}
    entry_key = forms.get(form_no)
    entry = files.get(entry_key) if isinstance(entry_key, str) else None
    if entry is None:
        legacy = section.get(form_no)
        if isinstance(legacy, str):
            entry_key = legacy
            entry = {"filename": legacy, "kind": "서식"}
    if not isinstance(entry, dict):
        return None
    filename = entry.get("filename")
    kind = entry.get("kind")
    if not isinstance(filename, str) or Path(filename).name != filename or not filename.lower().endswith(".hwp"):
        return None
    if kind not in {"공고문", "서식"}:
        return None
    wanted = unicodedata.normalize("NFC", filename)
    path = next((p for p in HWP_DIR.glob("*.hwp") if unicodedata.normalize("NFC", p.name) == wanted), None)
    return (str(entry_key), str(kind), path) if path else None


def _hwp_path(program_code: str, form_no: str):
    entry = _hwp_entry(program_code, form_no)
    return entry[2] if entry else None


def _application_hwp_entries(app: Any) -> list[tuple[str, str, Path]]:
    forms = list(available_forms(app))
    if app.program_code != "double_savings":
        forms.append("job_interview_confirmation")
    entries: dict[str, tuple[str, str, Path]] = {}
    for form_no in forms:
        entry = _hwp_entry(app.program_code, form_no)
        if entry:
            _, kind, path = entry
            unique_key = unicodedata.normalize("NFC", path.name)
            entries[unique_key] = (unique_key, kind, path)
    return list(entries.values())


def _has_written_content(app: Any, form_no: str) -> bool:
    form1 = app.form1_json or {}
    if form_no == "서식2":
        return bool(app.self_check_json)
    if form_no in {"서식3", "서식4", "job_consent"}:
        types = {"서식3": {"privacy", "unique_id"}, "서식4": {"third_party"}, "job_consent": {"privacy", "third_party"}}[form_no]
        return any(c.consent_type in types for c in list_consents(app.id or 0))
    if form_no == "서식5":
        return bool((app.form5_json or {}).get("agree") or (app.form5_json or {}).get("signature") or (app.form5_json or {}).get("signatureScanUploaded"))
    if form_no == "job_application":
        return any(str(value or "").strip() for key, value in form1.items() if key not in {"name", "birth", "mobile"})
    if form_no == "서식1":
        return any(str(form1.get(key) or "").strip() for key in ("address", "email", "savingPurpose", "priorJoined", "gender", "householdType", "householdSize", "workType", "workplaceRegion", "bankName", "accountNo", "accountHolder"))
    return False


def _filled_pdf(app: Any, form_no: str) -> tuple[bytes, Any]:
    spec = form_coords.load(form_no)
    if spec is None or not spec.available or form_no not in BUILDERS:
        raise HTTPException(503, "서식 템플릿을 사용할 수 없습니다.")
    if form_no == "job_interview_confirmation":
        filled = BUILDERS[form_no](app)
    else:
        filled = BUILDERS[form_no](app, consents=list_consents(app.id or 0), storage_root=STORAGE, subsidy_items=subsidy_rows(app.id or 0))
    return render(spec, filled), spec


def _form_filename(app: Any, form_no: str, ext: str) -> str:
    spec = form_coords.load(form_no)
    business = "두배적금" if app.program_code == "double_savings" else "취업패키지"
    form_label = spec.public_form or form_no if spec else form_no
    title = _safe_filename(spec.title if spec else form_no)
    return f"2026_{business}_{form_label}_{title}.{ext}"


@router.post("/{application_id}/forms/signature-scan")
async def upload_signature_scan(application_id: int, file: UploadFile = File(...)) -> dict[str, bool]:
    """Save a processed signature image in the application's private storage."""
    app = load_application(application_id)
    from ..models import STATUS_DRAFT

    if app.status != STATUS_DRAFT:
        raise HTTPException(409, "제출한 신청서는 수정할 수 없습니다.")
    if file.content_type not in {"image/jpeg", "image/png"}:
        raise HTTPException(400, "JPG 또는 PNG 이미지 파일을 올려 주세요.")
    raw = await file.read(SIGNATURE_SCAN_MAX_BYTES + 1)
    if len(raw) > SIGNATURE_SCAN_MAX_BYTES:
        raise HTTPException(413, "서명 이미지는 10MB 이하로 올려 주세요.")
    try:
        processed = process_signature_scan(raw)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    original_base, processed_path = signature_scan_paths(STORAGE, app.application_no)
    original_base.parent.mkdir(parents=True, exist_ok=True)
    delete_signature_scan(STORAGE, app.application_no)
    suffix = ".jpg" if file.content_type == "image/jpeg" else ".png"
    original_base.with_suffix(suffix).write_bytes(raw)
    processed_path.write_bytes(processed)
    return {"uploaded": True}


@router.delete("/{application_id}/forms/signature-scan")
def delete_signature_scan_route(application_id: int) -> dict[str, bool]:
    app = load_application(application_id)
    from ..models import STATUS_DRAFT

    if app.status != STATUS_DRAFT:
        raise HTTPException(409, "제출한 신청서는 수정할 수 없습니다.")
    delete_signature_scan(STORAGE, app.application_no)
    return {"uploaded": False}


@router.get("/{application_id}/forms/signature-scan.png")
def read_signature_scan(application_id: int) -> Response:
    app = load_application(application_id)
    _, processed = signature_scan_paths(STORAGE, app.application_no)
    if not processed.is_file():
        raise HTTPException(404, "서명 이미지가 없습니다.")
    return Response(processed.read_bytes(), media_type="image/png", headers={"Cache-Control": "private, no-store"})


def form_links(application_id: int, *, include_paper_form: bool = False) -> list[dict[str, Any]]:
    """담당자 화면 "작성 서식" 탭 목록.

    좌표 맵이나 템플릿이 없으면 목록에서 빠진다 — P7은 선택 기능이라, 준비가
    안 된 환경에서도 심사 화면 자체는 그대로 떠야 한다.
    """
    app = load_application(application_id)
    paper_admin_consent = bool(((app.doc_context_json or {}).get("paper_forms") or {}).get("서식5"))
    links: list[dict[str, Any]] = []
    for form_no in available_forms(app):
        if form_no == "서식5" and paper_admin_consent and not include_paper_form:
            continue
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
                "hwp_available": _hwp_path(app.program_code, form_no) is not None,
            }
        )
    return links


@router.get("/{application_id}/forms")
def list_forms(application_id: int) -> list[dict[str, Any]]:
    return form_links(application_id, include_paper_form=True)


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
    # Applicant layout uses stable opaque field ids. Internal model keys stay in the
    # local client binding table and never enter the applicant-facing API payload.
    field_ids = {key: f"f{index:04d}" for index, key in enumerate(spec.fields)}
    public_fields = {field_ids[key]: value for key, value in spec.fields.items()}
    public_requirements = []
    for rule in spec.requirements or []:
        public_rule = dict(rule)
        for key in ("field",):
            if key in public_rule:
                internal = public_rule[key]
                public_rule[key] = field_ids.get(internal) or next(
                    (opaque for name, opaque in field_ids.items() if name.startswith(f"{internal}.")), ""
                )
        for key in ("fields", "required"):
            if key in public_rule:
                public_rule[key] = [field_ids[name] for name in public_rule[key] if name in field_ids]
        public_requirements.append(public_rule)
    return {
        "form_no": spec.form_no,
        "title": spec.title,
        "public_form": spec.public_form,
        "page_sizes": sizes,
        "fields": public_fields,
        "requirements": public_requirements,
        "masks": spec.masks or [],
        "auto_date": form_date(app).isoformat(),
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


@router.get("/{application_id}/forms/{form_no}/pages/{page_no}.png")
def form_page_png(
    request: Request,
    application_id: int,
    form_no: str,
    page_no: int,
    preview: bool = Query(default=False),
    dpi: int = Query(default=200, ge=40, le=300),
) -> Response:
    """원본 또는 완성 서식의 한 쪽을 PyMuPDF로 렌더링한다."""
    app = load_application(application_id)
    if form_no not in available_forms(app) and not (
        app.program_code != "double_savings" and form_no == "job_interview_confirmation"
    ):
        raise HTTPException(404, "이 신청 건의 서식이 아닙니다.")
    spec = form_coords.load(form_no)
    if spec is None or not spec.available:
        raise HTTPException(503, f"{form_no} 템플릿을 사용할 수 없습니다.")
    import fitz

    with fitz.open(spec.template) as doc:
        if page_no < 1 or page_no > doc.page_count:
            raise HTTPException(404, "서식 쪽 번호가 범위를 벗어났습니다.")

    if preview and form_no == "서식5" and ((app.doc_context_json or {}).get("paper_forms") or {}).get("서식5"):
        preview = False
    if preview:
        if form_no == "job_interview_confirmation":
            filled = BUILDERS[form_no](app)
        else:
            filled = BUILDERS[form_no](
                app,
                consents=list_consents(application_id),
                storage_root=STORAGE,
                subsidy_items=subsidy_rows(application_id),
            )
        stat = spec.template.stat()
        payload = filled_payload(filled)
        etag = '"' + sha256(
            f"{form_no}|{stat.st_mtime_ns}|{page_no}|{dpi}|{payload}".encode("utf-8")
        ).hexdigest() + '"'
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers={"ETag": etag, "Cache-Control": "private, no-cache"})
        png = render_filled_page_png_cached(
            form_no, str(spec.template), stat.st_mtime_ns, page_no, dpi, payload
        )
        cache_control = "private, max-age=60" if dpi <= 80 else "no-store"
    else:
        stat = spec.template.stat()
        png = render_template_page_png(str(spec.template), stat.st_mtime_ns, page_no, dpi)
        cache_control = "private, max-age=3600"
    return Response(
        content=png,
        media_type="image/png",
        headers={"Cache-Control": cache_control, **({"ETag": etag} if preview else {})},
    )


@router.get("/{application_id}/forms/{form_no}.pdf")
def export_form(application_id: int, form_no: str) -> Response:
    """작성된 서식을 원본과 같은 모양의 PDF로 만들어 인라인으로 흘린다."""
    app = load_application(application_id)
    if form_no not in available_forms(app):
        raise HTTPException(404, f"이 신청 건에는 {form_no} 서식이 없습니다.")
    if form_no == "서식5" and ((app.doc_context_json or {}).get("paper_forms") or {}).get("서식5"):
        raise HTTPException(404, "종이 제출 서식의 화면 작성본은 제출 서식에 포함되지 않습니다.")

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
            "Cache-Control": "no-store",
        },
    )


@router.get("/{application_id}/forms/files/all.zip")
def all_forms_archive(application_id: int) -> Response:
    app = load_application(application_id)
    output = io.BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for form_no in available_forms(app):
            spec = form_coords.load(form_no)
            if spec and spec.available:
                archive.writestr(_form_filename(app, form_no, "pdf"), spec.template.read_bytes())
        if app.program_code != "double_savings":
            spec = form_coords.load("job_interview_confirmation")
            if spec and spec.available:
                archive.writestr(_form_filename(app, "job_interview_confirmation", "pdf"), spec.template.read_bytes())
    name = "2026_두배적금_빈서식PDF모음.zip" if app.program_code == "double_savings" else "2026_취업패키지_빈서식PDF모음.zip"
    return Response(output.getvalue(), media_type="application/zip", headers={"Content-Disposition": _filename_header(name), "Cache-Control": "private, no-store"})


def _hwp_kind_label(kind: str) -> str:
    return "공고문 원본 HWP(서식 포함)" if kind == "공고문" else "서식 원본 HWP"


@router.get("/{application_id}/forms/files/original-hwp/options")
def original_hwp_options(application_id: int) -> dict[str, str | None]:
    app = load_application(application_id)
    entries = _application_hwp_entries(app)
    if not entries:
        return {"url": None, "label": None}
    kinds = {kind for _, kind, _ in entries}
    label = _hwp_kind_label(next(iter(kinds))) if len(kinds) == 1 else "원본 HWP 모음"
    if len(entries) > 1:
        label += " (zip)"
    return {"url": f"/api/applications/{application_id}/forms/files/original-hwp", "label": label}


@router.get("/{application_id}/forms/files/original-hwp")
def original_hwp_bundle(application_id: int) -> Response:
    app = load_application(application_id)
    entries = _application_hwp_entries(app)
    if not entries:
        raise HTTPException(404, "원본 HWP가 없습니다.")
    if len(entries) == 1:
        path = entries[0][2]
        return Response(path.read_bytes(), media_type="application/octet-stream", headers={"Content-Disposition": _filename_header(path.name), "Cache-Control": "private, no-store"})
    output = io.BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for _, _, path in entries:
            archive.writestr(path.name, path.read_bytes())
    business = "두배적금" if app.program_code == "double_savings" else "취업패키지"
    name = f"2026_{business}_원본HWP모음.zip"
    return Response(output.getvalue(), media_type="application/zip", headers={"Content-Disposition": _filename_header(name), "Cache-Control": "private, no-store"})


@router.get("/{application_id}/forms/files/{form_no}/filled.pdf")
def filled_form_file(application_id: int, form_no: str) -> Response:
    app = load_application(application_id)
    if form_no not in available_forms(app) or (form_no == "서식5" and ((app.doc_context_json or {}).get("paper_forms") or {}).get("서식5")) or not _has_written_content(app, form_no):
        raise HTTPException(404, "작성한 서식이 없습니다.")
    pdf, _ = _filled_pdf(app, form_no)
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": _filename_header(_form_filename(app, form_no, "pdf")), "Cache-Control": "private, no-store"})


@router.get("/{application_id}/forms/files/{form_no}/blank.pdf")
def blank_form_file(application_id: int, form_no: str) -> Response:
    app = load_application(application_id)
    allowed = set(available_forms(app)) | ({"job_interview_confirmation"} if app.program_code != "double_savings" else set())
    spec = form_coords.load(form_no)
    if form_no not in allowed or spec is None or not spec.available:
        raise HTTPException(404, "빈 서식 PDF가 없습니다.")
    return Response(spec.template.read_bytes(), media_type="application/pdf", headers={"Content-Disposition": _filename_header(_form_filename(app, form_no, "pdf")), "Cache-Control": "private, no-store"})


@router.get("/{application_id}/forms/files/{form_no}/source.hwp")
def source_form_hwp(application_id: int, form_no: str) -> Response:
    app = load_application(application_id)
    source = _hwp_path(app.program_code, form_no)
    if source is None:
        raise HTTPException(404, "원본 HWP가 없습니다.")
    spec = form_coords.load(form_no)
    return Response(source.read_bytes(), media_type="application/octet-stream", headers={"Content-Disposition": _filename_header(source.name), "Cache-Control": "private, no-store"})


@router.get("/{application_id}/forms/files/{form_no}/options")
def form_file_options(application_id: int, form_no: str) -> dict[str, str | None]:
    app = load_application(application_id)
    if app.program_code == "double_savings" or form_no != "job_interview_confirmation":
        raise HTTPException(404, "면접확인서 다운로드 항목이 아닙니다.")
    return {
        "blank": f"/api/applications/{application_id}/forms/files/{form_no}/blank.pdf",
        "hwp": f"/api/applications/{application_id}/forms/files/{form_no}/source.hwp" if _hwp_path(app.program_code, form_no) else None,
    }


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

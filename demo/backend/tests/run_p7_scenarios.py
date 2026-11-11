"""P7 게이트 검증 — **작성 서식 PDF 내보내기**.

저장소 루트에서:

    PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python -m demo.backend.tests.run_p7_scenarios

확인하는 것:

  1. **좌표 맵이 원본에서 나온 그대로인가** — 템플릿 PDF에서 좌표를 다시 뽑아
     커밋된 JSON과 한 글자도 다르지 않은지 본다. 손으로 고친 좌표가 섞이면 여기서
     깨진다.
  2. **값 → 좌표 → 되읽기 왕복** — 내보낸 PDF를 PyMuPDF로 다시 열어, 넣은 값이
     **그 필드의 칸 안에서** 글자로 추출되는지 본다. 그려만 놓고 못 읽는 그림이
     아니라는 뜻이고, 자리도 맞다는 뜻이다.
  3. **체크는 체크한 곳에만** — 선택한 보기 좌표에 남색 채운 네모 벡터가 있고,
     미선택 보기에는 없는지 본다. 자가진단은 다시 그린 예/아니오 행을 확인한다.
  4. **겹치지 않는다** — 얹은 글자가 원본 글자·표 선과 겹치지 않는지 좌표로 본다.
     서식 위에 값을 쓰는 일의 성패가 여기에 달려 있다.
  5. **서명 합성** — 서식5 및 취업패키지 서명이 인쇄된 `(서명 또는 인)`·`(인)`과 겹치는지 본다.
  6. **신청자 API 비식별** — 레이아웃에 불투명 ID만 있고, 담당자 작성본 PDF에 값이 있는지 본다.
  7. **다운로드 0회 유지** — 응답이 전부 `inline`이다 (R9.3 / P4 DoD).

pytest 없이 돌아간다. DB와 저장소는 임시 경로에 만들고 끝나면 지운다 —
`demo/storage`·`demo/demo.db`(시연용 데이터)를 건드리지 않는다. 입력값은 전부
가짜다 (R7.1).
"""

import argparse
import io
import json
import re
import shutil
import tempfile
import zipfile
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch

from sqlmodel import create_engine

from .. import models
from ..forms import coords as form_coords
from ..rules.programs import DOUBLE_SAVINGS, JOB_PACKAGE
from ..rules.roles import ROLE_PROVINCE

DEMO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = DEMO_ROOT / "fixtures"
TEMPLATES = FIXTURES / "templates"
COORDS = FIXTURES / "form_coords"

_passed = 0
_failed: list[str] = []


def check(name: str, actual: object, expected: object) -> None:
    global _passed
    if actual == expected:
        _passed += 1
        print(f"  [OK]   {name}: {actual}")
    else:
        _failed.append(name)
        print(f"  [FAIL] {name}: 기대={expected!r} 실제={actual!r}")


def check_true(name: str, value: object) -> None:
    check(name, bool(value), True)


# ---------------------------------------------------------------- 시연 입력값


#: 전부 가짜다. 실제 신청자 정보·실물 서류는 쓰지 않는다 (R7.1).
P7_FORM1: dict[str, Any] = {
    "savingPurpose": "주거자금",
    "priorJoined": "미참여",
    "name": "홍길동",
    "birth": {"y": "1998", "m": "6", "d": "15"},
    "gender": "남",
    "address": "전북특별자치도 전주시 완산구 효자동 123",
    "mobile": "010-0000-0000",
    "email": "demo@example.com",
    "ecName": "홍부모",
    "ecRelation": "부",
    "ecContact": "010-0000-1111",
    "transferIn": {"y": "2021", "m": "11", "d": "20"},
    "householdType": "그 외 일반 가구",
    "householdSize": "4인",
    "workType": "상용직(노동계약기간 1년 이상)",
    "employedAt": {"y": "2023", "m": "1", "d": "2"},
    "workplaceRegion": "전북특별자치도 내 지역",
    "workplaceName": "(주)데모",
    "adminWorkForm": "기간제 근로자",
    "workplaceAddress": "전주시 덕진구 백제대로 1",
    "workplaceContact": "063-000-0000",
    "bankName": "농협은행",
    "accountNo": "302-0000-0000-00",
    "accountHolder": "홍길동",
    # 원본이 줄바꿈으로 'SNS'에서 끊긴 보기까지 일부러 고른다.
    "referralPaths": ["홈페이지(도, 시군, 청년센터 등)", "SNS(인스타그램)", "지인소개"],
    "writtenMonth": "11",
    "writtenDay": "30",
    "consent.form3.year": "1999",
}

P7_FORM5 = {
    "agree": "동의함",
    "name": "홍길동",
    "birth": {"y": "1998", "m": "6", "d": "15"},
    "phone": "010-0000-0000",
    # 작성일은 서버 값이어야 한다. 아래 값은 의도적으로 시계와 다르게 둔다.
    "writtenMonth": "12",
    "writtenDay": "31",
    "writtenOn": {"y": "1999", "m": "8", "d": "9"},
}

#: 서식1에서 체크되어야 할 보기 전부. 거주기간·근로기간은 날짜에서 자동으로 나온다
#: — 2021-11-20 전입 → 공고일(2026-03-03)까지 4년 3개월, 2023-01-02 취업 → 3년 2개월.
EXPECTED_CHECKS_FORM1 = {
    0: {
        "savingPurpose.주거자금",
        "priorJoined.미참여",
        "gender.남",
        "residencePeriod.4년 이상 ~ 5년 미만",
        "householdType.그 외 일반 가구",
        "householdSize.4인",
        "workType.상용직(노동계약기간 1년 이상)",
        "workPeriod.3년 이상",
        "workplaceRegion.전북특별자치도 내 지역",
        "adminWorkForm.기간제 근로자",
    },
    1: {
        "monthlyDeposit.월 10만원",
        "referralPaths.홈페이지(도, 시군, 청년센터 등)",
        "referralPaths.SNS",
        "referralPaths.지인소개",
    },
}

#: 서식1에 값 그대로 찍혀야 할 글자. (필드 키, 기대 문자열)
EXPECTED_TEXTS_FORM1 = [
    ("name", "홍길동"),
    ("birth", "1998. 6. 15."),
    ("address", "전북특별자치도 전주시 완산구 효자동 123"),
    ("mobile", "010-0000-0000"),
    ("email", "demo@example.com"),
    ("ecName", "홍부모"),
    ("ecRelation", "부"),
    ("ecContact", "010-0000-1111"),
    ("workplaceName", "(주)데모"),
    ("workplaceAddress", "전주시 덕진구 백제대로 1"),
    ("workplaceContact", "063-000-0000"),
    ("bankName", "농협은행"),
    ("accountNo", "302-0000-0000-00"),
    ("accountHolder", "홍길동"),
]

EXPECTED_TEXTS_FORM5 = [
    ("name", "홍길동"),
    ("birth", "1998. 6. 15."),
    ("phone", "010-0000-0000"),
]


def signature_png(path: Path) -> str:
    """캔버스 전자서명 대신 쓸 더미 PNG. 배경은 투명하다."""
    import base64

    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (420, 150), (0, 0, 0, 0))
    pen = ImageDraw.Draw(image)
    pen.line(
        [(20, 110), (70, 40), (110, 110), (160, 50), (210, 105), (270, 45), (340, 100), (400, 55)],
        fill=(12, 20, 90, 255),
        width=8,
    )
    image.save(path)
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


# ---------------------------------------------------------------- 좌표 도우미


def contains(box: list[float], rect: Any, slack: float = 0.6) -> bool:
    """글자 상자가 필드 칸 안에 있는가.

    세로 여유를 조금 더 주는 이유: 글자 상자는 글꼴 기준선 아래 내림 폭까지 포함해
    그려진 잉크보다 크다. 한글에는 내림이 없어 실제로는 칸 안이다. 진짜로 원본을
    덮었는지는 아래 픽셀 대조가 따로 본다.
    """
    return (
        rect.x0 >= box[0] - slack
        and rect.x1 <= box[2] + slack
        and rect.y0 >= box[1] - slack
        and rect.y1 <= box[3] + slack + 1.5
    )


def word_key(word: tuple) -> tuple:
    return (round(word[0], 1), round(word[1], 1), word[4])


def added_words(filled: Any, template: Any) -> dict[int, list[tuple]]:
    """내보낸 PDF에서 **우리가 얹은 글자만** 골라낸다.

    템플릿에 원래 있던 낱말을 빼면 남는 것이 오버레이다. 이 목록이 왕복 검증의
    출발점이다 — 넣은 값이 여기 없으면 "그렸지만 읽히지 않는" 것이다.
    """
    out: dict[int, list[tuple]] = {}
    for page_no in range(filled.page_count):
        original = {word_key(w) for w in template[page_no].get_text("words")}
        out[page_no] = [
            w for w in filled[page_no].get_text("words") if word_key(w) not in original
        ]
    return out


def _brand_square_rects(page: Any) -> list[Any]:
    """Return the navy filled-square checkbox marks, not searchable text marks."""
    import fitz

    marks = []
    for drawing in page.get_drawings():
        fill = drawing.get("fill")
        if not fill or any(abs(float(a) - b) > 0.002 for a, b in zip(fill, (0.05, 0.10, 0.45))):
            continue
        for item in drawing.get("items", []):
            if item[0] == "re":
                marks.append(fitz.Rect(item[1]))
    return marks


def checkbox_mark_errors(form_no: str, body: bytes, selected: set[str]) -> list[str]:
    """Compare blue vector squares with each selected/unselected view coordinate."""
    import fitz

    from ..forms.render import _font

    spec = json.loads((COORDS / f"{form_no}.json").read_text(encoding="utf-8"))
    errors = []
    with fitz.open(stream=body, filetype="pdf") as doc:
        for key, field in spec["fields"].items():
            if field["type"] != "check":
                continue
            page_no = int(field["page"])
            page_marks = _brand_square_rects(doc[page_no])
            if field.get("control") == "radio_text":
                x0, y0, x1, y1 = field["group_box"]
                label = field["label"]
                slot = 0 if label == "예" else 1
                width = (x1 - x0) / 2
                size = float(field.get("size", 9.5))
                square_size = size * 0.78
                label_width = _font(str(field.get("font_family", "sans"))).text_length(label, size)
                total = square_size + 3.0 + label_width
                left = x0 + slot * width + max(1.0, (width - total) / 2)
                center = fitz.Rect(left, (y0 + y1 - square_size) / 2,
                                   left + square_size, (y0 + y1 + square_size) / 2)
            else:
                x0, y0, x1, y1 = field["box"]
                size = max(x1 - x0, y1 - y0) + 3.0
                cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
                center = fitz.Rect(cx - size / 2, cy - size / 2, cx + size / 2, cy + size / 2)
            present = any(all(abs(a - b) < 0.3 for a, b in zip(mark, center)) for mark in page_marks)
            if present != (key in selected):
                errors.append(f"p{page_no}:{key} expected {'filled' if key in selected else 'empty'} square at {center}")
    return errors


def signature_overlaps_source(body: bytes, form_no: str, field_key: str, marker: str) -> bool:
    """Check that the placed signature image overlaps its printed signature phrase."""
    import fitz

    spec = json.loads((COORDS / f"{form_no}.json").read_text(encoding="utf-8"))
    template = fitz.open(TEMPLATES / f"{form_no}.pdf")
    filled = fitz.open(stream=body, filetype="pdf")
    try:
        page_no = int(spec["fields"][field_key]["page"])
        source_page = template[page_no]
        phrase_boxes = [
            fitz.Rect(word[:4]) for word in source_page.get_text("words")
            if marker.replace(" ", "") in word[4].replace(" ", "")
        ]
        image_boxes = [
            fitz.Rect(rect)
            for image in filled[page_no].get_images(full=True)
            for rect in filled[page_no].get_image_rects(image[0])
        ]
        return any(image.intersects(phrase) for image in image_boxes for phrase in phrase_boxes)
    finally:
        template.close()
        filled.close()


def ink_collision(form_no: str, body: bytes, dpi: int = 150) -> tuple[int, int]:
    """원본 잉크를 덮은 픽셀 수를 센다 — "겹쳐 봤을 때 어긋나지 않는가"의 실측.

    같은 배율로 템플릿과 내보낸 서식을 나란히 그려 픽셀을 맞대고 본다.
    달라진 픽셀(= 우리가 얹은 잉크) 가운데 **원본이 이미 검던 자리**가 있으면
    그것이 겹침이다. `✓`는 `□` 위에 찍는 것이 목적이므로 체크 칸과 서명란은 뺀다.

    반환: (덮은 픽셀 수, 얹은 픽셀 수)
    """
    import fitz
    from PIL import Image, ImageChops, ImageDraw

    spec = json.loads((COORDS / f"{form_no}.json").read_text(encoding="utf-8"))
    scale = dpi / 72.0
    covered = 0
    painted = 0

    filled = fitz.open(stream=body, filetype="pdf")
    template = fitz.open(TEMPLATES / f"{form_no}.pdf")
    for page_no in range(filled.page_count):
        before = template[page_no].get_pixmap(dpi=dpi)
        after = filled[page_no].get_pixmap(dpi=dpi)
        size = (before.width, before.height)
        a = Image.frombytes("RGB", size, before.samples).convert("L")
        b = Image.frombytes("RGB", size, after.samples).convert("L")

        changed = ImageChops.difference(a, b).point(lambda v: 255 if v > 40 else 0)
        ink = a.point(lambda v: 255 if v < 128 else 0)
        overlap = ImageChops.multiply(changed, ink)

        pen = ImageDraw.Draw(overlap)
        for field in spec["fields"].values():
            if field["page"] != page_no or field["type"] not in ("check", "image"):
                continue
            box = field["box"]
            pen.rectangle(
                [box[0] * scale - 2, box[1] * scale - 2, box[2] * scale + 2, box[3] * scale + 2],
                fill=0,
            )
        # 히스토그램으로 센다 — 픽셀을 파이썬으로 훑으면 느리고, getdata 는
        # Pillow 14에서 사라진다.
        covered += sum(overlap.histogram()[1:])
        painted += sum(changed.histogram()[1:])
    filled.close()
    template.close()
    return covered, painted


# ---------------------------------------------------------------- 1. 좌표 맵


def test_coordinate_maps() -> None:
    """좌표가 원본 PDF에서 나온 그대로인지."""
    import pymupdf as fitz

    from ...fixtures.build_form_coords import BUILDERS, _annotate_choice_geometry, read_sheet

    print("\n[1] 좌표 맵 — 원본 PDF에서 다시 뽑아 대조")

    check("템플릿 서식1 존재", (TEMPLATES / "서식1.pdf").exists(), True)
    check("템플릿 서식5 존재", (TEMPLATES / "서식5.pdf").exists(), True)

    for form_no in ("서식1", "서식2", "서식3", "서식4", "서식5", "job_application", "job_consent", "job_interview_confirmation"):
        saved = json.loads((COORDS / f"{form_no}.json").read_text(encoding="utf-8"))
        with fitz.open(TEMPLATES / f"{form_no}.pdf") as doc:
            rebuilt, masks = BUILDERS[form_no](doc)
            _annotate_choice_geometry(
                rebuilt,
                [read_sheet(page, page_no) for page_no, page in enumerate(doc)],
                form_no,
            )
            page_rects = [page.rect for page in doc]
            markers = ["".join(p["title"].split()) for p in saved["source"]["pages"]]
            found = [
                marker
                for index, marker in enumerate(markers)
                if marker in "".join(doc[index].get_text().split())
            ]
        check(f"{form_no} 실제 원본 쪽 제목", found, markers)
        # 좌표 전체를 그대로 찍으면 화면이 넘치므로 어긋난 필드 이름만 센다.
        drifted = sorted(
            key
            for key in set(rebuilt) | set(saved["fields"])
            if rebuilt.get(key) != saved["fields"].get(key)
        )
        check(f"{form_no} 필드 수", len(saved["fields"]), len(rebuilt))
        check(f"{form_no} 원본에서 다시 뽑은 좌표와 어긋난 필드", drifted, [])

        outside = [
            key
            for key, spec in saved["fields"].items()
            if not (
                0 <= spec.get("x", spec.get("box", [0])[0]) <= page_rects[spec["page"]].width
                and 0 <= spec.get("y", spec.get("box", [0, 0])[1]) <= page_rects[spec["page"]].height
            )
        ]
        check(f"{form_no} 쪽 밖으로 나간 좌표", outside, [])

    for form_no in ("서식2", "서식3", "서식4", "job_application", "job_consent", "job_interview_confirmation"):
        spec = json.loads((COORDS / f"{form_no}.json").read_text(encoding="utf-8"))
        check_true(f"{form_no} 입력 좌표 있음", spec["fields"])
        check_true(f"{form_no} 원본 위치 기록", spec["source"]["pages"])


# ---------------------------------------------------------------- 2. 내보내기


def export(client, application_id: int, form_no: str) -> tuple[Any, bytes]:
    res = client.get(f"/api/applications/{application_id}/forms/{form_no}.pdf")
    return res, res.content


def test_export_headers(client, ds_id: int, jp_id: int) -> None:
    print("\n[2] 내보내기 응답 — 인라인만, 내려받는 경로 없음")

    listed = client.get(f"/api/applications/{ds_id}/forms").json()
    public_order_internal_ids = ["서식2", "서식1", "서식3", "서식4", "서식5"]
    check("두배적금 내보낼 서식은 공고문 번호 순서", [f["form_no"] for f in listed], public_order_internal_ids)
    check("목록의 화면 번호", [f["public_form"] for f in listed], ["서식1", "서식2", "서식3", "서식4", "서식5"])
    check("목록 파일 이름의 화면 번호", [f["file_name"].rsplit("_", 1)[-1] for f in listed], ["서식1.pdf", "서식2.pdf", "서식3.pdf", "서식4.pdf", "서식5.pdf"])
    check_true("파일 주소가 서식 경로", all("/forms/" in f["file_url"] for f in listed))

    dispositions: list[str] = []
    for form_no in ("서식1", "서식2", "서식3", "서식4", "서식5"):
        res, body = export(client, ds_id, form_no)
        check(f"{form_no} 응답", res.status_code, 200)
        check(f"{form_no} 형식", res.headers["content-type"], "application/pdf")
        check(f"{form_no} PDF 헤더", body[:5], b"%PDF-")
        dispositions.append(res.headers["content-disposition"])
        public_no = {"서식1": "서식2", "서식2": "서식1", "서식3": "서식3", "서식4": "서식4", "서식5": "서식5"}[form_no]
        decoded_name = __import__("urllib.parse", fromlist=["unquote"]).unquote(res.headers["content-disposition"])
        check(f"{form_no} 개별 PDF 파일 이름은 화면 번호", f"_{public_no}.pdf" in decoded_name, True)

    check("모두 inline", [d.split(";")[0] for d in dispositions], ["inline"] * 5)
    # "내려받게 만드는 값"이 하나도 없어야 한다. 낱말을 그대로 쓰지 않으려고 쪼갠다
    # — P4의 정적 검사가 이 파일도 훑기 때문이다.
    forbidden = "attach" + "ment"
    check("내려받기 지시 0건", sum(forbidden in d for d in dispositions), 0)

    job_forms = client.get(f"/api/applications/{jp_id}/forms").json()
    check("취업패키지 신청자 서식", [f["form_no"] for f in job_forms], ["job_application", "job_consent"])
    for form_no in ("job_application", "job_consent"):
        res, body = export(client, jp_id, form_no)
        check(f"{form_no} 응답", res.status_code, 200)
        check(f"{form_no} PDF 형식", body[:5], b"%PDF-")
    check(
        "취업패키지 서식1 요청",
        client.get(f"/api/applications/{jp_id}/forms/서식1.pdf").status_code,
        404,
    )
    check("없는 서식 요청", client.get(f"/api/applications/{ds_id}/forms/서식9.pdf").status_code, 404)


def _synthetic_admin_scan(tmp: Path, *, signed: bool) -> bytes:
    import pymupdf as fitz

    from ..forms import coords as coords

    spec = coords.load("서식5")
    assert spec is not None
    doc = fitz.open(spec.template)
    page = doc[0]
    font = DEMO_ROOT / "frontend" / "src" / "assets" / "fonts" / "NotoSansKR" / "NotoSansKR-subset.ttf"
    page.insert_text((28, 28), "행정정보 공동이용 사전동의서", fontfile=str(font), fontsize=9)
    page.insert_text((28, 43), "성명: 김가상", fontfile=str(font), fontsize=9)
    page.insert_text((28, 58), "생년월일: 1998-06-15", fontfile=str(font), fontsize=9)
    consent_box = fitz.Rect(*spec.fields["agree.동의함"]["box"])
    page.draw_line((consent_box.x0 + 1, consent_box.y0 + 1), (consent_box.x1 - 1, consent_box.y1 - 1), color=(0, 0, 0), width=1.3)
    page.draw_line((consent_box.x0 + 1, consent_box.y1 - 1), (consent_box.x1 - 1, consent_box.y0 + 1), color=(0, 0, 0), width=1.3)
    if signed:
        signature = fitz.Rect(*spec.fields["signature"]["box"])
        page.draw_line((signature.x0 + 5, signature.y1 - 3), (signature.x0 + 21, signature.y0 + 4), color=(0, 0, 0), width=1.7)
        page.draw_line((signature.x0 + 21, signature.y0 + 4), (signature.x0 + 34, signature.y1 - 5), color=(0, 0, 0), width=1.7)
        page.draw_line((signature.x0 + 34, signature.y1 - 5), (signature.x0 + 50, signature.y0 + 5), color=(0, 0, 0), width=1.7)
    return doc.tobytes()


def test_form_files_and_paper_flow(client, tmp: Path) -> None:
    from ..api import forms as forms_api
    from .. import models
    from ..models import Application
    from ..api.review import _blockers
    from ..api.common import load_application
    from ..ocr.admin_consent_scan import inspect_admin_consent_scan
    from ..rules.doc_types import DocType
    from ..ocr import read_document

    print("\n[10] 서식 다운로드·스캔본 제출")
    public_order_internal_ids = ("서식2", "서식1", "서식3", "서식4", "서식5")
    criteria = client.get("/api/programs/double_savings/criteria").json()
    check("기본 스캔본 제출 허용 기준", criteria["paper_forms"].get("서식5"), True)
    check("다른 서식 기본 불허", criteria["paper_forms"].get("서식4"), False)
    app_id = client.post("/api/applications", json={"program_code": DOUBLE_SAVINGS}).json()["id"]
    check("미작성 작성본 파일 요청 거부", client.get(f"/api/applications/{app_id}/forms/files/서식5/filled.pdf").status_code, 404)

    # HWP test data is synthetic so the user-provided source contents are never opened.
    old_hwp_dir = forms_api.HWP_DIR
    fake_hwp = tmp / "hwp"
    fake_hwp.mkdir()
    fake_name = "합성_두배적금.hwp"
    (fake_hwp / fake_name).write_bytes(b"synthetic-hwp-test")
    fake_job_name = "합성_취업패키지.hwp"
    (fake_hwp / fake_job_name).write_bytes(b"synthetic-job-hwp-test")
    fake_extra_name = "합성_추가서식.hwp"
    (fake_hwp / fake_extra_name).write_bytes(b"synthetic-extra-hwp-test")
    (fake_hwp / "manifest.json").write_text(json.dumps({
        "double_savings": {
            "files": {"savings": {"filename": fake_name, "kind": "서식"}},
            "forms": {f"서식{i}": "savings" for i in range(1, 6)},
        },
        "job_package": {
            "files": {"job": {"filename": fake_job_name, "kind": "서식"}},
            "forms": {"job_application": "job", "job_consent": "job", "job_interview_confirmation": "job"},
        },
    }), encoding="utf-8")
    forms_api.HWP_DIR = fake_hwp
    try:
        forms = client.get(f"/api/applications/{app_id}/forms").json()
        check("HWP 원본 보유 표시", forms[-1]["hwp_available"], True)
        blank = client.get(f"/api/applications/{app_id}/forms/files/서식5/blank.pdf")
        check("빈 PDF 다운로드", blank.status_code, 200)
        check_true("한글 파일명 RFC 5987", "filename*=UTF-8''" in blank.headers["content-disposition"] and "2026_두배적금_서식5" in __import__("urllib.parse", fromlist=["unquote"]).unquote(blank.headers["content-disposition"]))
        hwp = client.get(f"/api/applications/{app_id}/forms/files/서식5/source.hwp")
        check("원본 HWP 다운로드", hwp.content, b"synthetic-hwp-test")
        check_true("원본 HWP 한글 filename*", "filename*=UTF-8''" in hwp.headers["content-disposition"] and "합성_두배적금.hwp" in __import__("urllib.parse", fromlist=["unquote"]).unquote(hwp.headers["content-disposition"]))
        bundle_options = client.get(f"/api/applications/{app_id}/forms/files/original-hwp/options").json()
        check("단일 HWP 메뉴 이름", bundle_options["label"], "서식 원본 HWP")
        single_hwp = client.get(bundle_options["url"])
        check("단일 원본은 HWP 직접 제공", single_hwp.content, b"synthetic-hwp-test")
        announcement_manifest = {
            "double_savings": {
                "files": {"savings": {"filename": fake_name, "kind": "공고문"}},
                "forms": {f"서식{i}": "savings" for i in range(1, 6)},
            }
        }
        (fake_hwp / "manifest.json").write_text(json.dumps(announcement_manifest), encoding="utf-8")
        announcement_options = client.get(f"/api/applications/{app_id}/forms/files/original-hwp/options").json()
        check("공고문 종류 메뉴 이름", announcement_options["label"], "공고문 원본 HWP(서식 포함)")
        written_url = f"/api/applications/{app_id}/forms/files/written.pdf"
        blank_archive = client.get(written_url)
        check("미작성 상태에서도 PDF 메뉴 제공", blank_archive.status_code, 200)
        import fitz
        with fitz.open(stream=blank_archive.content, filetype="pdf") as blank_doc:
            blank_text = " ".join(page.get_text() for page in blank_doc)
            blank_first_page = blank_doc[0].get_text()
            blank_page_count = blank_doc.page_count
        blank_expected_pages = sum(len(fitz.open(TEMPLATES / f"{form_no}.pdf")) for form_no in ("서식1", "서식2", "서식3", "서식4", "서식5"))
        check("아무것도 쓰지 않아도 다섯 서식이 포함", blank_page_count, blank_expected_pages)
        check_true("빈 서식에 신청자 입력값은 없음", "홍길동" not in blank_text)
        from ..forms.values import today
        today_value = today()
        check_true("미작성 서식에도 자동 작성일 표시", str(today_value.month) in blank_first_page and str(today_value.day) in blank_first_page)
        # Combined PDF and the applicant preview API must paint every automatic
        # default identically, even before the applicant enters form data.
        from PIL import Image
        preview_pages_match = True
        page_offset = 0
        with fitz.open(stream=blank_archive.content, filetype="pdf") as blank_doc:
            for form_no in public_order_internal_ids:
                with fitz.open(TEMPLATES / f"{form_no}.pdf") as template_doc:
                    for page_no in range(1, template_doc.page_count + 1):
                        preview = client.get(
                            f"/api/applications/{app_id}/forms/{form_no}/pages/{page_no}.png",
                            params={"preview": "true", "dpi": 72},
                        )
                        pdf_png = blank_doc[page_offset].get_pixmap(matrix=fitz.Matrix(1, 1), alpha=False).tobytes("png")
                        preview_image = Image.open(io.BytesIO(preview.content)).convert("RGB")
                        pdf_image = Image.open(io.BytesIO(pdf_png)).convert("RGB")
                        preview_pages_match = preview_pages_match and preview.status_code == 200 and preview_image.size == pdf_image.size and preview_image.tobytes() == pdf_image.tobytes()
                        page_offset += 1
        check("미작성 합본 PDF의 기본값은 화면용 미리보기 API와 같음", preview_pages_match, True)

        # Identity values are prefilled by verification, with no other form
        # entry. The on-screen preview and combined PDF still use the same values.
        with models.get_session() as session:
            row = session.get(Application, app_id)
            row.identity_json = {"name": "가나다", "birth": "1992-03-04", "phone": "010-****-1234"}
            row.form1_json = {"name": "가나다", "birth": {"y": "1992", "m": "03", "d": "04"}, "mobile": "010-1234-1234"}
            session.add(row)
            session.commit()
        identity_archive = client.get(written_url)
        identity_pages_match = True
        page_offset = 0
        with fitz.open(stream=identity_archive.content, filetype="pdf") as identity_doc:
            for form_no in public_order_internal_ids:
                with fitz.open(TEMPLATES / f"{form_no}.pdf") as template_doc:
                    for page_no in range(1, template_doc.page_count + 1):
                        preview = client.get(
                            f"/api/applications/{app_id}/forms/{form_no}/pages/{page_no}.png",
                            params={"preview": "true", "dpi": 72},
                        )
                        pdf_png = identity_doc[page_offset].get_pixmap(matrix=fitz.Matrix(1, 1), alpha=False).tobytes("png")
                        preview_image = Image.open(io.BytesIO(preview.content)).convert("RGB")
                        pdf_image = Image.open(io.BytesIO(pdf_png)).convert("RGB")
                        identity_pages_match = identity_pages_match and preview.status_code == 200 and preview_image.size == pdf_image.size and preview_image.tobytes() == pdf_image.tobytes()
                        page_offset += 1
        check("본인인증 미리 채운 값도 합본 PDF와 화면용 API가 같음", identity_pages_match, True)
        identity_builder = forms_api.BUILDERS["서식1"](load_application(app_id))
        check_true("미작성 신청서의 월 10만원 자동 선택", "monthlyDeposit.월 10만원" in identity_builder.checks)
        client.patch(f"/api/applications/{app_id}", json={"form1": {"address": "부분 입력 주소"}})
        partial_pdf = client.get(written_url)
        with fitz.open(stream=partial_pdf.content, filetype="pdf") as partial_doc:
            # Public form 1 (internal form2/self-check) is first; the application
            # form (internal form1/public form2) follows it.
            partial_form1_text = partial_doc[1].get_text()
        check_true("부분 작성 서식에는 저장한 값 포함", "부분 입력 주소" in partial_form1_text)
        check_true("부분 작성 서식에 입력하지 않은 연락처는 없음", "010-0000-0000" not in partial_form1_text)
        other_id = client.post("/api/applications", json={"program_code": DOUBLE_SAVINGS}).json()["id"]
        other_token = client.cookies.get(f"applicant_access_{other_id}")
        denied_archive = client.get(
            f"/api/applications/{app_id}/forms/files/written.pdf",
            headers={"cookie": f"applicant_access_{app_id}={other_token}"},
        )
        check("다른 신청자 토큰으로 작성본 PDF 접근 거부", denied_archive.status_code, 403)

        archive_signature = signature_png(tmp / "archive-signature.png")
        with models.get_session() as session:
            row = session.get(Application, app_id)
            row.self_check_json = {str(index): ("예" if index % 2 else "아니오") for index in range(1, 9)}
            row.form1_json = P7_FORM1.copy()
            row.form5_json = {**P7_FORM5, "signature": archive_signature}
            session.add(row)
            session.add(models.Consent(application_id=app_id, consent_type="admin_info", agreed=True))
            session.commit()
        archive = client.get(f"/api/applications/{app_id}/forms/files/written.pdf")
        check("작성본 PDF 응답", archive.status_code, 200)
        check("작성본 PDF 형식", archive.headers.get("content-type"), "application/pdf")
        check("작성본 PDF no-store", archive.headers.get("cache-control"), "no-store")
        application_no = load_application(app_id).application_no
        expected_filename = f"2026_두배적금_신청서식_{application_no}.pdf"
        decoded_header = __import__("urllib.parse", fromlist=["unquote"]).unquote(archive.headers.get("content-disposition", ""))
        check_true("작성본 PDF 한글 filename*", "filename*=UTF-8''" in archive.headers.get("content-disposition", "") and expected_filename in decoded_header)
        import fitz
        with fitz.open(stream=archive.content, filetype="pdf") as combined:
            combined_texts = [page.get_text() for page in combined]
            combined_page_count = combined.page_count
        completed_form_nos = tuple(public_order_internal_ids)
        source_page_counts = {}
        expected_texts = []
        for form_no in completed_form_nos:
            source_pdf, _ = forms_api._filled_pdf(load_application(app_id), form_no)
            with fitz.open(stream=source_pdf, filetype="pdf") as source_doc:
                source_page_counts[form_no] = source_doc.page_count
                expected_texts.extend(page.get_text() for page in source_doc)
        check("작성 완료 서식 쪽 수 합산", combined_page_count, sum(source_page_counts.values()))
        check("작성본 PDF는 공고문 서식 번호 순서", combined_texts, expected_texts)
        form2_start = 0
        with fitz.open(stream=archive.content, filetype="pdf") as combined:
            form2_doc = fitz.open()
            form2_doc.insert_pdf(combined, from_page=form2_start, to_page=form2_start + source_page_counts["서식2"] - 1)
            form2_pdf = form2_doc.tobytes()
            form5_start = sum(source_page_counts[f"서식{i}"] for i in range(1, 5))
            form5_doc = fitz.open()
            form5_doc.insert_pdf(combined, from_page=form5_start, to_page=form5_start + source_page_counts["서식5"] - 1)
            form5_pdf = form5_doc.tobytes()
        check_true("작성본 PDF의 선택 보기 보존", not checkbox_mark_errors("서식2", form2_pdf, {f"self_check.{index}.{('예' if index % 2 else '아니오')}" for index in range(1, 9)}))
        check_true("작성본 PDF에 이름·서명 포함", "홍길동" in combined_texts[form5_start] and signature_overlaps_source(form5_pdf, "서식5", "signature", "인"))
        with models.get_session() as session:
            for consent_type in ("privacy", "unique_id", "third_party"):
                session.add(models.Consent(application_id=app_id, consent_type=consent_type, agreed=True))
            session.commit()
        all_pdf = client.get(written_url)
        with fitz.open(stream=all_pdf.content, filetype="pdf") as combined:
            all_page_count = combined.page_count
        all_source_pages = 0
        for form_no in ("서식1", "서식2", "서식3", "서식4", "서식5"):
            source_pdf, _ = forms_api._filled_pdf(load_application(app_id), form_no)
            with fitz.open(stream=source_pdf, filetype="pdf") as source_doc:
                all_source_pages += source_doc.page_count
        check("전부 완료 PDF 쪽 수는 다섯 서식의 합", all_page_count, all_source_pages)
        multi_manifest = {
            "double_savings": {
                "files": {
                    "savings": {"filename": fake_name, "kind": "서식"},
                    "savings_extra": {"filename": fake_extra_name, "kind": "서식"},
                },
                "forms": {"서식1": "savings", "서식2": "savings", "서식3": "savings", "서식4": "savings_extra", "서식5": "savings"},
            },
            "job_package": {
                "files": {"job": {"filename": fake_job_name, "kind": "서식"}},
                "forms": {"job_application": "job", "job_consent": "job", "job_interview_confirmation": "job"},
            },
        }
        (fake_hwp / "manifest.json").write_text(json.dumps(multi_manifest), encoding="utf-8")
        multi_options = client.get(f"/api/applications/{app_id}/forms/files/original-hwp/options").json()
        check("여러 HWP 메뉴는 zip", multi_options["label"], "서식 원본 HWP (zip)")
        multi_hwp = client.get(multi_options["url"])
        with zipfile.ZipFile(io.BytesIO(multi_hwp.content)) as bundle:
            multi_names = bundle.namelist()
        check("여러 원본 HWP zip 구성", multi_names, [fake_name, fake_extra_name])
        job_id = client.post("/api/applications", json={"program_code": JOB_PACKAGE}).json()["id"]
        interview_options = client.get(f"/api/applications/{job_id}/forms/files/job_interview_confirmation/options").json()
        check_true("면접확인서 다운로드 메뉴에 PDF·HWP", interview_options["blank"].endswith("blank.pdf") and interview_options["hwp"].endswith("source.hwp"))
        interview_blank = client.get(interview_options["blank"])
        check("면접확인서 빈 PDF 다운로드", interview_blank.status_code, 200)
        job_blank = client.get(f"/api/applications/{job_id}/forms/files/written.pdf")
        check("취업패키지 미작성도 PDF 제공", job_blank.status_code, 200)
        with fitz.open(stream=job_blank.content, filetype="pdf") as document:
            check("취업패키지 미작성 서식 모두 포함", document.page_count, 2)
        check("예전 zip 작성본 API 제거", client.get(f"/api/applications/{job_id}/forms/files/written.zip").status_code, 404)
        job_bundle_options = client.get(f"/api/applications/{job_id}/forms/files/original-hwp/options").json()
        check("취업패키지 단일 HWP 메뉴 이름", job_bundle_options["label"], "서식 원본 HWP")
        check("취업패키지 단일 HWP 직접 제공", client.get(job_bundle_options["url"]).content, b"synthetic-job-hwp-test")
        (fake_hwp / "manifest.json").write_text(json.dumps({"double_savings": {"files": {}, "forms": {}}}), encoding="utf-8")
        missing = client.get(f"/api/applications/{app_id}/forms").json()
        missing_options = client.get(f"/api/applications/{app_id}/forms/files/original-hwp/options").json()
        check("HWP가 없을 때 카드 링크 숨김", missing[-1]["hwp_available"], False)
        check("HWP가 없을 때 상단 메뉴 숨김", missing_options["url"], None)
    finally:
        forms_api.HWP_DIR = old_hwp_dir

    changed = client.put(f"/api/applications/{app_id}/doc-context", json={"paper_forms": {"서식5": True}})
    check("스캔본 제출 기준 선택", changed.status_code, 200)
    denied = client.put(f"/api/applications/{app_id}/doc-context", json={"paper_forms": {"서식4": True}})
    check("기준이 불허한 서식은 스캔본 제출 불가", denied.status_code, 400)
    with models.get_session() as session:
        row = session.get(Application, app_id)
        row.form1_json = P7_FORM1.copy()
        session.add(row)
        session.commit()
    no_scan_pdf = client.get(f"/api/applications/{app_id}/forms/files/written.pdf")
    with fitz.open(stream=no_scan_pdf.content, filetype="pdf") as no_scan_doc:
        no_scan_page_count = no_scan_doc.page_count
        no_scan_text = " ".join(page.get_text() for page in no_scan_doc)
        form5_start = sum(len(fitz.open(TEMPLATES / f"{form_no}.pdf")) for form_no in ("서식1", "서식2", "서식3", "서식4"))
        paper_form5 = no_scan_doc[form5_start]
        paper_form5_text = paper_form5.get_text()
        paper_form5_checks = _brand_square_rects(paper_form5)
        paper_form5_images = paper_form5.get_images(full=True)
    expected_no_scan_pages = 0
    for form_no in ("서식1", "서식2", "서식3", "서식4", "서식5"):
        if form_no == "서식5":
            source_pdf = forms_api._blank_form_pdf(load_application(app_id), form_no)
        else:
            source_pdf, _ = forms_api._filled_pdf(load_application(app_id), form_no)
        with fitz.open(stream=source_pdf, filetype="pdf") as source_doc:
            expected_no_scan_pages += source_doc.page_count
    check("스캔본 미업로드면 저장값이 든 서식5까지 모두 포함", no_scan_page_count, expected_no_scan_pages)
    check_true("스캔본 전 서식5 입력값은 남음", "홍길동" in paper_form5_text and "010-0000-0000" in paper_form5_text)
    check("스캔본 전 서식5 동의 체크·서명은 비움", (len(paper_form5_checks), len(paper_form5_images)), (0, 0))
    checklist = client.get(f"/api/applications/{app_id}/required-documents").json()
    paper = next((row for row in checklist["items"] if row["slot_key"] == "admin_info_consent"), None)
    check_true("서식5 스캔 칸 필수 추가", paper and paper["upload"] and paper["required"] and not paper["check_declared_date"])
    check_true("미업로드면 제출 차단 사유에 포함", any(item.get("target") == "admin_info_consent" for item in _blockers(load_application(app_id))))
    saved = client.patch(f"/api/applications/{app_id}", json={"form5": {"agree": "동의함", "signature": "kept-online-value"}})
    check("온라인 값 저장", saved.status_code, 200)
    back = client.put(f"/api/applications/{app_id}/doc-context", json={"paper_forms": {"서식5": False}})
    check("온라인 작성으로 복귀", back.status_code, 200)
    check("온라인 작성값 보존", client.get(f"/api/applications/{app_id}").json()["form5_json"].get("signature"), "kept-online-value")

    client.put(f"/api/applications/{app_id}/doc-context", json={"paper_forms": {"서식5": True}})
    with models.get_session() as session:
        application = session.get(Application, app_id)
        application.identity_json = {"name": "김가상", "birth": "1998-06-15"}
        session.add(application)
        session.commit()

    signed_path = tmp / "synthetic-admin-signed.pdf"
    signed_path.write_bytes(_synthetic_admin_scan(tmp, signed=True))
    unsigned_path = tmp / "synthetic-admin-unsigned.pdf"
    unsigned_path.write_bytes(_synthetic_admin_scan(tmp, signed=False))
    signed_observations = inspect_admin_consent_scan(str(signed_path))
    unsigned_observations = inspect_admin_consent_scan(str(unsigned_path))
    check("합성 스캔의 동의 표시 판독", signed_observations["동의여부"], "동의함")
    check("합성 스캔의 서명 잉크 판독", signed_observations["서명잉크확인"], "있음")
    check("서명 없는 합성 스캔은 불확실", unsigned_observations["서명잉크확인"], "확인필요")
    recognized = read_document(str(signed_path), DocType.ADMIN_INFO_CONSENT)
    check("스캔 본문으로 서식 종류 판별", recognized.detected_doc_type, DocType.ADMIN_INFO_CONSENT)
    signed_response = client.post(
        f"/api/applications/{app_id}/documents",
        files={"file": ("synthetic-signed.pdf", signed_path.read_bytes(), "application/pdf")},
        data={"slot_key": "admin_info_consent"},
    )
    check("합성 종이 서식 종류 판별", signed_response.json().get("detected_doc_type"), str(DocType.ADMIN_INFO_CONSENT))
    unsigned_response = client.post(
        f"/api/applications/{app_id}/documents",
        files={"file": ("synthetic-unsigned.pdf", unsigned_path.read_bytes(), "application/pdf")},
        data={"slot_key": "admin_info_consent"},
    )
    check("서명 없는 스캔은 담당자 확인", unsigned_response.json().get("status"), "NEEDS_REVIEW")
    check_true("서명 판독 불확실 사유", any(f.get("code") == "ADMIN_CONSENT_SIGNATURE_UNREADABLE" for f in unsigned_response.json().get("findings", [])))

    flow_id, _ = seed(client, tmp)
    context = client.put(f"/api/applications/{flow_id}/doc-context", json={
        "work_category": "직장가입자", "workplace_count": 1,
        "paper_forms": {"서식5": True},
    })
    check("스캔본 제출 방식이 신청 플로우에 저장", context.status_code, 200)
    _submit(client, flow_id, DS_UPLOADS, {"admin_info_consent": _synthetic_admin_scan(tmp, signed=True)})
    check("제출 뒤 작성 방식 변경 잠금", client.put(f"/api/applications/{flow_id}/doc-context", json={"paper_forms": {"서식5": False}}).status_code, 409)
    frozen = client.get(f"/api/applications/{flow_id}/forms/files/written.pdf")
    check("제출 후 작성본 PDF 응답", frozen.status_code, 200)
    check("제출 후 작성본 PDF no-store", frozen.headers.get("cache-control"), "no-store")
    check_true("스캔본 제출이 합친 PDF에 포함", frozen.content.startswith(b"%PDF-") and len(frozen.content) > 1000)
    scan_document = forms_api._paper_consent_document(load_application(flow_id))
    with fitz.open(stream=frozen.content, filetype="pdf") as frozen_pdf:
        frozen_scan_pixels = frozen_pdf[-1].get_pixmap(matrix=fitz.Matrix(1, 1)).samples
    with fitz.open(stream=forms_api._scan_pdf(scan_document), filetype="pdf") as source_scan:
        uploaded_scan_pixels = source_scan[0].get_pixmap(matrix=fitz.Matrix(1, 1)).samples
    check_true("제출 후 PDF 마지막 쪽은 올린 스캔본", frozen_scan_pixels == uploaded_scan_pixels)
    frozen_order_matches = True
    frozen_page_index = 0
    with fitz.open(stream=frozen.content, filetype="pdf") as frozen_pdf:
        frozen_page_count = frozen_pdf.page_count
        for form_no in public_order_internal_ids:
            if form_no == "서식5":
                expected_pdf = forms_api._scan_pdf(scan_document)
            else:
                expected_pdf, _ = forms_api._filled_pdf(load_application(flow_id), form_no)
            with fitz.open(stream=expected_pdf, filetype="pdf") as expected_doc:
                for expected_page in expected_doc:
                    if frozen_page_index >= frozen_pdf.page_count:
                        frozen_order_matches = False
                        break
                    actual_pixels = frozen_pdf[frozen_page_index].get_pixmap(matrix=fitz.Matrix(1, 1)).samples
                    expected_pixels = expected_page.get_pixmap(matrix=fitz.Matrix(1, 1)).samples
                    frozen_order_matches = frozen_order_matches and actual_pixels == expected_pixels
                    frozen_page_index += 1
    check("제출 고정 PDF도 공고문 번호 순서", frozen_order_matches and frozen_page_index == frozen_page_count, True)
    archive_path = load_application(flow_id).written_forms_archive_path
    saved_archive = (forms_api.STORAGE.parent / archive_path).read_bytes()
    with models.get_session() as session:
        from sqlmodel import select
        current = load_application(flow_id)
        versions = session.exec(select(models.ProgramCriteriaVersion).where(models.ProgramCriteriaVersion.program_code == current.program_code)).all()
        latest = max(versions, key=lambda item: item.version)
        changed_criteria = dict(latest.criteria_json)
        changed_criteria["notice_date"] = "2099-01-01"
        session.add(models.ProgramCriteriaVersion(program_code=current.program_code, version=latest.version + 1, criteria_json=changed_criteria, changed_role="province"))
        session.commit()
    coord_path = COORDS / "서식5.json"
    coord_original = coord_path.read_bytes()
    try:
        coord_data = json.loads(coord_original)
        coord_data["title"] = "변경된 테스트 템플릿 좌표"
        coord_path.write_text(json.dumps(coord_data, ensure_ascii=False), encoding="utf-8")
        check_true("제출 후 좌표 맵 변경에도 PDF 고정", client.get(f"/api/applications/{flow_id}/forms/files/written.pdf").content == saved_archive)
    finally:
        coord_path.write_bytes(coord_original)


# ---------------------------------------------------------------- 3. 왕복 검증


def roundtrip(form_no: str, body: bytes, expected_texts, expected_checks) -> None:
    """내보낸 PDF를 다시 열어 값·체크를 좌표로 확인한다."""
    import fitz

    spec = json.loads((COORDS / f"{form_no}.json").read_text(encoding="utf-8"))
    fields = spec["fields"]

    filled = fitz.open(stream=body, filetype="pdf")
    template = fitz.open(TEMPLATES / f"{form_no}.pdf")
    check(f"{form_no} 쪽 수 유지", filled.page_count, template.page_count)

    added = added_words(filled, template)

    # --- (a) 넣은 값이 그 필드의 칸 안에서 글자로 되읽힌다 (값 → 좌표 → 재추출)
    #        칸 안에 있는 글자만 모아 읽는다. 자리가 틀리면 글자가 모이지 않으므로
    #        되읽기와 자리 검증이 한 번에 된다.
    wrong: list[str] = []
    for key, text in expected_texts:
        field = fields[key]
        inside = [
            w
            for w in added[field["page"]]
            if contains(field["box"], fitz.Rect(w[:4]))
        ]
        read = " ".join(w[4] for w in sorted(inside, key=lambda w: w[0]))
        if read.replace(" ", "") != text.replace(" ", ""):
            wrong.append(f"{key}: 기대={text!r} 칸에서 읽은 값={read!r}")
    check(f"{form_no} 값 왕복 실패", wrong, [])

    # 어느 필드 칸에도 속하지 않는 글자가 남으면 자리를 벗어난 것이다.
    # `✓`는 `□` 글자 상자보다 한 뼘 넓게 찍히므로 여기서 빼고, 아래 (b)에서 따로 본다.
    homeless: list[str] = []
    for page_no, words in added.items():
        for word in words:
            if "✓" in word[4]:
                continue
            rect = fitz.Rect(word[:4])
            if any(
                field["page"] == page_no and contains(field["box"], rect)
                for field in fields.values()
            ):
                continue
            homeless.append(f"p{page_no}:{word[4]}")
    check(f"{form_no} 칸 밖으로 나간 글자", homeless, [])

    # --- (b) Selected views have navy filled-square vector marks; others stay empty.
    expected_all = {key for keys in expected_checks.values() for key in keys}
    check(f"{form_no} 채운 네모의 선택 위치·미선택 보기", checkbox_mark_errors(form_no, body, expected_all), [])

    filled.close()
    template.close()

    # --- (c) 얹은 잉크가 원본 잉크를 덮지 않는다 (픽셀 실측)
    covered, painted = ink_collision(form_no, body)
    print(f"       얹은 잉크 {painted:,}px 중 원본을 덮은 것 {covered}px")
    check_true(f"{form_no} 오버레이가 실제로 찍혔다", painted > 1000)
    # 150dpi 래스터 경계에서 1px 이하의 획 접촉은 anti-aliasing 차이로 센다.
    check_true(f"{form_no} 원본 글자·선과 실질 겹침 없음", covered <= 5)


def test_form1_roundtrip(client, ds_id: int) -> None:
    print("\n[3] 서식1 왕복 — 값 → 좌표 → 되읽기")
    _, body = export(client, ds_id, "서식1")
    roundtrip("서식1", body, EXPECTED_TEXTS_FORM1, EXPECTED_CHECKS_FORM1)


def test_email_format_validation(client, ds_id: int) -> None:
    print("\n[이메일] 전각 입력 정리와 형식 검증")
    fullwidth = dict(P7_FORM1, email="　ｄｅｍｏ＠ｅｘａｍｐｌｅ．ｃｏｍ　")
    saved = client.patch(f"/api/applications/{ds_id}", json={"form1": fullwidth})
    check("전각 이메일·앞뒤 공백 정리 저장", saved.status_code, 200)
    check("정규화 이메일 값", saved.json().get("form1_json", {}).get("email"), "demo@example.com")

    for value in ("ㅎㅎ", "user@", "user@domain"):
        invalid = dict(P7_FORM1, email=value)
        response = client.patch(f"/api/applications/{ds_id}", json={"form1": invalid})
        check(f"잘못된 이메일 거부 ({value})", response.status_code, 400)
        check(f"잘못된 이메일 안내 ({value})", response.json().get("detail"), "이메일 형식을 확인해 주세요.")


def test_self_check_marks(client, ds_id: int) -> None:
    print("\n[3-1] 자가진단 8행 — 다시 그린 예/아니오 칸의 벡터 네모")
    _, body = export(client, ds_id, "서식2")
    selected = {f"self_check.{row}.예" for row in range(1, 9)}
    check("자가진단 1~8행 채운 네모·미선택 보기", checkbox_mark_errors("서식2", body, selected), [])


def test_form5_roundtrip(client, ds_id: int, clock_day: date) -> None:
    print("\n[4] 서식5 왕복 — 값·동의 체크")
    _, body = export(client, ds_id, "서식5")
    expected = [
        *EXPECTED_TEXTS_FORM5[:3],
        ("writtenMonth", str(clock_day.month)),
        ("writtenDay", str(clock_day.day)),
    ]
    roundtrip("서식5", body, expected, {0: {"agree.동의함"}})


def test_submitted_date_fixed(client, ds_id: int, clock_day: date) -> None:
    print("\n[4-1] 작성일 시계 주입·제출 뒤 고정")
    app_path = f"/api/applications/{ds_id}"
    with patch("demo.backend.forms.values.today", return_value=clock_day):
        draft_layout = client.get(f"{app_path}/forms/layouts/서식5").json()
        check("작성 중 화면 API 날짜", draft_layout["auto_date"], clock_day.isoformat())
        _submit(client, ds_id, DS_UPLOADS)

    stored = client.get(app_path).json()
    date_keys = {"writtenMonth", "writtenDay", "writtenOn", "consent.form3.year"}
    check_true(
        "클라이언트 작성일 값은 신청서에 저장되지 않음",
        not (date_keys & set(stored.get("form1_json") or {}))
        and not (date_keys & set(stored.get("form5_json") or {})),
    )

    later_day = clock_day + timedelta(days=19)
    with patch("demo.backend.forms.values.today", return_value=later_day):
        layout = client.get(f"{app_path}/forms/layouts/서식5").json()
        check("제출 뒤 화면 API 작성일 고정", layout["auto_date"], clock_day.isoformat())
        _, body = export(client, ds_id, "서식5")
        expected = [("writtenMonth", str(clock_day.month)), ("writtenDay", str(clock_day.day))]
        roundtrip("서식5", body, expected, {0: {"agree.동의함"}})


# ---------------------------------------------------------------- 4. 전자서명


def test_signature(client, ds_id: int) -> None:
    """서식5 서명란에 이미지가 실제로 들어갔는가 (R9.2)."""
    import fitz

    print("\n[5] 서식5 전자서명 합성")
    _, body = export(client, ds_id, "서식5")
    doc = fitz.open(stream=body, filetype="pdf")
    page = doc[0]

    images = page.get_images(full=True)
    check("서명 이미지 개수", len(images), 1)

    spec = json.loads((COORDS / "서식5.json").read_text(encoding="utf-8"))
    box = fitz.Rect(*spec["fields"]["signature"]["box"])
    placed = page.get_image_rects(images[0][0])
    check_true("이미지가 쪽에 배치됨", placed)
    # 부동소수 끝자리(1e-5) 때문에 정확히 같은 값도 contains 가 어긋난다.
    box = fitz.Rect(box.x0 - 0.1, box.y0 - 0.1, box.x1 + 0.1, box.y1 + 0.1)
    inside = all(box.contains(fitz.Rect(r)) for r in placed)
    check("서명이 서명란 좌표 안", inside, True)

    # The image must cover the printed signature phrase as an actual stamp would.
    check("서명 이미지가 (서명 또는 인) 문구와 겹침", signature_overlaps_source(body, "서식5", "signature", "서명또는인"), True)

    # 서명이 없는 신청 건은 이미지도 없어야 한다 — 빈 자리에 아무거나 찍지 않는다.
    doc.close()


def test_signature_scan(client) -> None:
    """Scanned signature is cleaned, shown in the form, and counted as complete."""
    import fitz
    import io
    from PIL import Image, ImageDraw

    print("\n[5b] 자필 스캔 서명 배경 제거·렌더·필수 충족")
    app_id = client.post("/api/applications", json={"program_code": DOUBLE_SAVINGS}).json()["id"]
    client.patch(f"/api/applications/{app_id}", json={"form5": {
        "agree": "동의함", "signature": "", "signatureScanUploaded": False,
    }})

    # Synthetic white paper with a dark horizontal signature and EXIF orientation 6.
    canvas = Image.new("RGB", (120, 240), "white")
    draw = ImageDraw.Draw(canvas)
    draw.line([(60, 20), (40, 70), (68, 105), (42, 145), (60, 220)], fill=(10, 10, 10), width=6)
    exif = Image.Exif()
    exif[274] = 6
    source = io.BytesIO()
    canvas.save(source, format="JPEG", exif=exif)
    raw = source.getvalue()
    blank = io.BytesIO()
    Image.new("RGB", (60, 30), "white").save(blank, format="PNG")
    faint = client.post(
        f"/api/applications/{app_id}/forms/signature-scan",
        files={"file": ("blank.png", blank.getvalue(), "image/png")},
    )
    check("잉크가 없는 이미지 안내", faint.status_code, 400)
    check("잉크가 없는 이미지 안내 문구", faint.json()["detail"], "서명이 잘 보이지 않습니다. 흰 종이에 진하게 쓴 서명을 다시 올려 주세요.")
    response = client.post(
        f"/api/applications/{app_id}/forms/signature-scan",
        files={"file": ("synthetic-signature.jpg", raw, "image/jpeg")},
    )
    check("합성 서명 업로드", response.status_code, 200)
    saved = client.patch(f"/api/applications/{app_id}", json={"form5": {
        "agree": "동의함", "signature": "", "signatureScanUploaded": True,
    }})
    check("서명 스캔이 필수 항목을 충족", saved.json()["form5_json"]["signatureScanUploaded"], True)
    scan_response = client.get(f"/api/applications/{app_id}/forms/signature-scan.png")
    check("처리 이미지 API", scan_response.status_code, 200)
    cleaned = Image.open(io.BytesIO(scan_response.content)).convert("RGBA")
    check("종이 모서리가 투명", cleaned.getpixel((0, 0))[3], 0)
    check_true("EXIF 방향을 적용해 서명 획을 가로로 표시", cleaned.width > cleaned.height)

    from ..forms.signature_scan import signature_scan_paths
    from ..api import forms as forms_api
    original, processed = signature_scan_paths(
        forms_api.STORAGE, client.get(f"/api/applications/{app_id}").json()["application_no"]
    )
    expected_private_dir = forms_api.STORAGE / "signatures" / client.get(f"/api/applications/{app_id}").json()["application_no"]
    check_true("원본·처리 이미지는 신청 건별 비공개 저장소에 보관", any(expected_private_dir.glob("scan-original.*")) and processed.is_file() and original.parent == expected_private_dir and processed.parent == expected_private_dir)
    pdf = client.get(f"/api/applications/{app_id}/forms/서식5.pdf")
    check("스캔 서명이 포함된 PDF", pdf.status_code, 200)
    check("스캔 이미지가 서명 문구와 겹침", signature_overlaps_source(pdf.content, "서식5", "signature", "서명또는인"), True)
    with fitz.open(stream=pdf.content, filetype="pdf") as doc:
        check("PDF의 서명 이미지", len(doc[0].get_images(full=True)), 1)
    consent_response = client.post(f"/api/applications/{app_id}/consents", json={"consents": [
        {"consent_type": "admin_info", "agreed": True, "signature_kind": "handwritten"},
    ]})
    check("자필 서명을 동의 기록에 연결", consent_response.status_code, 200)
    check("동의 기록에 서명 이미지 저장됨", consent_response.json()["saved"][0]["signature_saved"], True)
    applicant_consents = client.get(f"/api/applications/{app_id}/consents").text
    check_true("신청자 응답은 서명 저장 경로를 감춤", "scan-processed.png" not in applicant_consents and "scan-original" not in applicant_consents)
    check("서명 스캔 삭제", client.delete(f"/api/applications/{app_id}/forms/signature-scan").status_code, 200)
    after_delete = client.patch(f"/api/applications/{app_id}", json={"form5": {
        "agree": "동의함", "signature": "", "signatureScanUploaded": True,
    }})
    check("삭제 후 필수 서명 상태", after_delete.json()["form5_json"]["signatureScanUploaded"], False)
    check("삭제 후 처리 이미지 비공개", client.get(f"/api/applications/{app_id}/forms/signature-scan.png").status_code, 404)


def test_without_signature(client) -> None:
    import fitz

    print("\n[6] 서명 없는 건 — 빈 서명란")
    app_id = client.post("/api/applications", json={"program_code": DOUBLE_SAVINGS}).json()["id"]
    client.patch(f"/api/applications/{app_id}", json={"form1": {"name": "김서명없음"}})
    client.post(
        f"/api/applications/{app_id}/consents",
        json={
            "consents": [
                {"consent_type": "privacy", "agreed": True},
                {"consent_type": "unique_id", "agreed": True},
                {"consent_type": "third_party", "agreed": True},
                {"consent_type": "admin_info", "agreed": False},
            ]
        },
    )
    res, body = export(client, app_id, "서식5")
    check("서명 없어도 내보내진다", res.status_code, 200)
    doc = fitz.open(stream=body, filetype="pdf")
    check("서명 이미지 없음", len(doc[0].get_images()), 0)
    check(
        "서명 없는 건도 동의하지 않음 채운 네모 위치",
        checkbox_mark_errors("서식5", body, {"agree.동의하지 않음"}),
        [],
    )
    doc.close()


# ---------------------------------------------------------------- 5. 담당자 화면


def test_officer_tab(client, ds_id: int, jp_id: int) -> None:
    """담당자 심사 화면에 "작성 서식" 탭이 붙고, 거기서도 다운로드가 0회인가."""
    print("\n[7] 담당자 화면 '작성 서식' 탭")

    detail = client.get(
        f"/api/officer/applications/{ds_id}", params={"role": ROLE_PROVINCE}
    ).json()
    check("서식 탭 수", len(detail["forms"]), 5)
    check("서식 탭 순서는 공고문 번호", [f["form_no"] for f in detail["forms"]], ["서식2", "서식1", "서식3", "서식4", "서식5"])
    check("서식 탭 표기는 공고문 번호", [f["public_form"] for f in detail["forms"]], ["서식1", "서식2", "서식3", "서식4", "서식5"])
    check_true("서식 탭 설명도 공고문 번호로 시작", all(f["label"].startswith(f["public_form"]) for f in detail["forms"]))
    check_true("업로드 서류 탭도 그대로", detail["documents"])

    for form in detail["forms"]:
        res = client.get(form["file_url"])
        check(f"{form['form_no']} 탭에서 열림", res.status_code, 200)
        check(
            f"{form['form_no']} 인라인",
            res.headers["content-disposition"].split(";")[0],
            "inline",
        )

    applicant_form = next(form for form in detail["forms"] if form["form_no"] == "서식1")
    officer_pdf = client.get(applicant_form["file_url"])
    import fitz
    with fitz.open(stream=officer_pdf.content, filetype="pdf") as document:
        officer_text = " ".join(page.get_text() for page in document)
    check_true("담당자 작성본 API가 신청자 이름 값을 PDF에 제공", P7_FORM1["name"] in officer_text)
    check_true("담당자 작성본 API가 은행 값을 PDF에 제공", P7_FORM1["bankName"] in officer_text)

    check("취업패키지 신청자 서식(목록 API)", [item["form_no"] for item in client.get(f"/api/applications/{jp_id}/forms").json()], ["job_application", "job_consent"])


def test_layout_and_interview_form(client, jp_id: int, ds_id: int, tmp: Path) -> None:
    from ..api.common import load_application

    print("\n[8] 취업패키지 좌표 응답·면접확인서 미리 채움")
    client.patch(f"/api/applications/{jp_id}", json={"form1": {
        "name": "김가상", "birth": {"y": "1999", "m": "1", "d": "1"},
        "address": "전북특별자치도 전주시", "mobile": "010-1111-2222", "email": "test@example.com",
        "bankName": "가상은행", "accountNo": "111-222-333",
        "job.signature": signature_png(tmp / "job-application-signature.png"),
    }})
    layout = client.get(f"/api/applications/{jp_id}/forms/layouts/job_application")
    check("레이아웃 응답", layout.status_code, 200)
    layout_data = layout.json()
    serialized_layout = json.dumps(layout_data, ensure_ascii=False)
    check_true("신청자 레이아웃은 불투명 필드 ID만 사용", bool(layout_data["fields"]) and all(re.fullmatch(r"f\d{4}", key) for key in layout_data["fields"]))
    check("신청자 레이아웃 내부 키 노출", re.findall(r'"(?:name|bankName|self_check\.\d+)"\s*:', serialized_layout), [])
    savings_layouts = [
        client.get(f"/api/applications/{ds_id}/forms/layouts/{form_no}").json()
        for form_no in ("서식1", "서식2")
    ]
    check_true(
        "두배적금 신청서·자가진단 레이아웃 내부 키 없음",
        all(all(re.fullmatch(r"f\d{4}", key) for key in item["fields"]) and not re.search(r'"(?:name|bankName|self_check\.\d+)"\s*:', json.dumps(item, ensure_ascii=False)) for item in savings_layouts),
    )
    template = client.get(f"/api/applications/{jp_id}/forms/templates/job_application.pdf")
    check("원본 템플릿 응답", template.status_code, 200)
    check("원본 템플릿 PDF", template.content[:5], b"%PDF-")
    background = client.get(f"/api/applications/{jp_id}/forms/job_application/pages/1.png")
    check("PyMuPDF 원본 배경 PNG", background.status_code, 200)
    check("배경 PNG MIME", background.headers.get("content-type"), "image/png")
    check("원본 PNG 캐시", background.headers.get("cache-control"), "private, max-age=3600")
    import pymupdf
    image = pymupdf.Pixmap(background.content)
    check_true("배경 PNG 약 200dpi", 1650 <= image.width <= 1660 and 2335 <= image.height <= 2345)
    preview_png = client.get(f"/api/applications/{jp_id}/forms/job_application/pages/1.png?preview=true&v=1")
    check("완성 미리보기 PNG", preview_png.status_code, 200)
    check("완성 PNG 캐시 금지", preview_png.headers.get("cache-control"), "no-store")
    check_true("완성 PNG는 원본 배경과 다름", preview_png.content != background.content)
    app_pdf = client.get(f"/api/applications/{jp_id}/forms/job_application.pdf")
    with pymupdf.open(stream=app_pdf.content, filetype="pdf") as document:
        app_text = " ".join(page.get_text() for page in document)
    check_true("신청자 API 입력값이 PDF 내보내기에 왕복", "김가상" in app_text and "가상은행" in app_text and "111-222-333" in app_text)
    check("취업패키지 신청서 서명이 인쇄된 (인)과 겹침", signature_overlaps_source(app_pdf.content, "job_application", "job.signature", "(인)"), True)
    interview_png = client.get(f"/api/applications/{jp_id}/forms/job_interview_confirmation/pages/1.png")
    check("면접확인서 원본 PNG", interview_png.status_code, 200)
    filled = client.get(f"/api/applications/{jp_id}/forms/interview-confirmation/filled.pdf")
    check("면접확인서 응답", filled.status_code, 200)
    check("면접확인서 PDF", filled.content[:5], b"%PDF-")
    with pymupdf.open(stream=filled.content, filetype="pdf") as document:
        text = " ".join(page.get_text() for page in document)
    check_true("신청인 성명 미리 채움", "김가상" in text)
    check_true("회사 정보는 회사 작성 칸으로 남음", "면접기업" in text or "회사명" in text)

    client.patch(f"/api/applications/{jp_id}", json={"form1": {
        "name": "김가상", "birth": {"y": "1999", "m": "1", "d": "1"},
        "address": "전북특별자치도 전주시", "mobile": "010-1111-2222", "email": "test@example.com",
        "bankName": "가상은행", "accountNo": "111-222-333",
        "consent.job.signature": signature_png(tmp / "job-consent-signature.png"),
        "job.suit.1.company": "가상정장회사", "job.suit.1.location": "전북특별자치도 전주시",
        "job.suit.1.date": "2026. 3. 5.",
        "job.signature": signature_png(tmp / "job-application-signature.png"),
    }})
    consent_pdf = client.get(f"/api/applications/{jp_id}/forms/job_consent.pdf")
    with pymupdf.open(stream=consent_pdf.content, filetype="pdf") as document:
        check("취업패키지 동의서 서명 이미지", len(document[0].get_images()), 1)
    check("취업패키지 동의서 서명이 인쇄된 (인)과 겹침", signature_overlaps_source(consent_pdf.content, "job_consent", "consent.job.signature", "(인)"), True)

    written = client.get(f"/api/applications/{jp_id}/forms/files/written.pdf")
    check("취업패키지 작성한 서식 응답", written.status_code, 200)
    app_no = load_application(jp_id).application_no
    content_disposition = written.headers.get("content-disposition", "")
    decoded_disposition = __import__("urllib.parse", fromlist=["unquote"]).unquote(content_disposition)
    check_true("취업패키지 신청서식 파일명", f"2026_취업지원패키지_신청서식_{app_no}.pdf" in decoded_disposition and "filename*=UTF-8''" in content_disposition)
    with pymupdf.open(stream=written.content, filetype="pdf") as combined:
        combined_pages = [page.get_text() for page in combined]
    expected_pages = []
    for form_no in ("job_application", "job_consent"):
        response = client.get(f"/api/applications/{jp_id}/forms/{form_no}.pdf")
        with pymupdf.open(stream=response.content, filetype="pdf") as source:
            expected_pages.extend(page.get_text() for page in source)
    check("취업패키지 작성본 PDF 순서", combined_pages, expected_pages)

    suit_only = client.post(f"/api/applications/{jp_id}/subsidy-items", json={"items": [
        {"item_type": "suit", "count": 1, "receipts": [30000], "linked_interview_indices": [1]},
    ]})
    check("면접비 없이 정장비만 선택", suit_only.status_code, 200)
    suit_pdf = client.get(f"/api/applications/{jp_id}/forms/job_application.pdf")
    with pymupdf.open(stream=suit_pdf.content, filetype="pdf") as document:
        check_true("정장비 단독 신청 정보를 서식에 표시", "가상정장회사" in " ".join(page.get_text() for page in document))

    linked = client.post(f"/api/applications/{jp_id}/subsidy-items", json={"items": [
        {"item_type": "interview", "count": 1, "receipts": [None]},
        {"item_type": "suit", "count": 1, "receipts": [30000], "linked_interview_indices": [1]},
    ]})
    check("정장비-면접 회차 연결 선택", linked.status_code, 200)
    client.patch(f"/api/applications/{jp_id}", json={"form1": {
        "job.interview.1.company": "가상면접회사",
        "job.interview.1.location": "전북특별자치도 익산시",
        "job.interview.1.date": "2026. 3. 6.",
    }})
    linked_pdf = client.get(f"/api/applications/{jp_id}/forms/job_application.pdf")
    with pymupdf.open(stream=linked_pdf.content, filetype="pdf") as document:
        text = " ".join(page.get_text() for page in document)
    check_true("연결된 면접기업 정보를 정장비 회차에 채움", text.count("가상면접회사") >= 2)
    check_true("연결된 면접 소재지를 정장비 회차에 채움", text.count("익산시") >= 2)


def test_submitted_forms_locked(client, ds_id: int) -> None:
    print("\n[9] 제출 후 서식 수정 API 잠금")
    check("제출 후 신청서 수정 거부", client.patch(f"/api/applications/{ds_id}", json={"form1": {"name": "변경 시도"}}).status_code, 409)
    check("제출 후 자가진단 수정 거부", client.post(f"/api/applications/{ds_id}/self-check", json={"answers": {"1": "예"}}).status_code, 409)
    check("제출 후 동의 수정 거부", client.post(f"/api/applications/{ds_id}/consents", json={"consents": []}).status_code, 409)


# ---------------------------------------------------------------- 진입점


def seed(client, tmp: Path) -> tuple[int, int]:
    """두배적금 1건(서명까지) + 취업패키지 1건."""
    sig = signature_png(tmp / "signature.png")

    ds_id = client.post("/api/applications", json={"program_code": DOUBLE_SAVINGS}).json()["id"]
    client.patch(f"/api/applications/{ds_id}", json={"form1": P7_FORM1, "form5": P7_FORM5})
    client.post(
        f"/api/applications/{ds_id}/consents",
        json={
            "consents": [
                {"consent_type": "privacy", "agreed": True},
                {"consent_type": "unique_id", "agreed": True},
                {"consent_type": "third_party", "agreed": True},
                {
                    "consent_type": "admin_info",
                    "agreed": True,
                    "signature_kind": "electronic",
                    "signature_data_url": sig,
                },
            ]
        },
    )
    client.put(
        f"/api/applications/{ds_id}/doc-context",
        json={"work_category": "직장가입자", "workplace_count": 1},
    )
    client.post(f"/api/applications/{ds_id}/self-check", json={"answers": {str(i): "예" for i in range(1, 9)}})

    jp_id = client.post("/api/applications", json={"program_code": JOB_PACKAGE}).json()["id"]
    client.patch(f"/api/applications/{jp_id}", json={"form1": {"name": "최청년"}})
    client.post(
        f"/api/applications/{jp_id}/consents",
        json={
            "consents": [
                {"consent_type": "privacy", "agreed": True},
                {"consent_type": "third_party", "agreed": True},
            ]
        },
    )
    return ds_id, jp_id


def _isolate(tmp: Path) -> None:
    """DB와 저장소를 임시 경로로 갈아끼운다. 시연용 데이터를 건드리지 않는다."""
    from ..api import applications as applications_api
    from ..api import documents as documents_api
    from ..api import files as files_api
    from ..api import forms as forms_api

    models.engine = create_engine(
        f"sqlite:///{tmp / 'p7.db'}", connect_args={"check_same_thread": False}
    )
    storage = tmp / "storage"
    documents_api.STORAGE = storage
    documents_api.DOCUMENTS = storage / "documents"
    applications_api.STORAGE = storage
    applications_api.SIGNATURES = storage / "signatures"
    files_api.STORAGE = storage
    forms_api.STORAGE = storage


#: 제출까지 가려면 체크리스트를 채워야 한다. P6 시연 fixture를 그대로 쓴다.
DS_UPLOADS = {
    "resident_abstract": "S2_주민등록초본_적합.pdf",
    "nhis_payment": "S2_건강보험료납부확인서_적합.pdf",
    "nhis_qualification": "S2_건강보험자격확인서_적합.pdf",
    "nhis_acquisition_loss": "S2_건강보험자격득실확인서_적합.pdf",
    "work_proof": "S2_4대보험가입내역확인서_적합.pdf",
}


def _submit(client, application_id: int, uploads: dict[str, str], extra_uploads: dict[str, bytes] | None = None) -> None:
    """심사 화면에 뜨려면 제출 상태여야 한다.

    작성 서식 탭은 **업로드 서류 탭과 나란히** 있어야 의미가 있으므로, 서류도
    실제로 올린 뒤 제출한다.
    """
    samples = FIXTURES / "samples"
    for slot, filename in uploads.items():
        with (samples / filename).open("rb") as fh:
            client.post(
                f"/api/applications/{application_id}/documents",
                files={"file": (filename, fh, "application/pdf")},
                data={"slot_key": slot, "declared_issue_date": "2026-03-05"},
            )
    for slot, content in (extra_uploads or {}).items():
        response = client.post(
            f"/api/applications/{application_id}/documents",
            files={"file": ("synthetic-paper-form.pdf", content, "application/pdf")},
            data={"slot_key": slot},
        )
        check(f"종이 서식 업로드 {slot}", response.status_code, 200)
    res = client.post(f"/api/applications/{application_id}/submit")
    check(f"제출 {application_id}", res.status_code, 200)


def main(clock_day: date | None = None) -> int:
    from fastapi.testclient import TestClient

    from ..main import app

    tmp = Path(tempfile.mkdtemp(prefix="p7-scenarios-"))
    clock_day = clock_day or date(2026, 3, 4)
    _isolate(tmp)
    form_coords.load.cache_clear()

    try:
        test_coordinate_maps()
        with TestClient(app) as client:
            ds_id, jp_id = seed(client, tmp)
            test_export_headers(client, ds_id, jp_id)
            test_form_files_and_paper_flow(client, tmp)
            test_form1_roundtrip(client, ds_id)
            test_email_format_validation(client, ds_id)
            test_self_check_marks(client, ds_id)
            test_form5_roundtrip(client, ds_id, clock_day)
            test_signature(client, ds_id)
            test_signature_scan(client)
            test_without_signature(client)
            test_submitted_date_fixed(client, ds_id, clock_day)
            test_layout_and_interview_form(client, jp_id, ds_id, tmp)
            test_submitted_forms_locked(client, ds_id)
            test_officer_tab(client, ds_id, jp_id)
    finally:
        models.engine.dispose()
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n통과 {_passed} / 실패 {len(_failed)}")
    if _failed:
        for name in _failed:
            print(f"  - {name}")
    return 1 if _failed else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--today", type=date.fromisoformat, default=date(2026, 3, 4))
    args = parser.parse_args()
    with patch("demo.backend.forms.values.today", return_value=args.today):
        raise SystemExit(main(args.today))

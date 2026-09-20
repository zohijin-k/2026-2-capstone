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
  3. **체크는 체크한 곳에만** — `✓`가 체크한 보기의 `□` 자리에만 찍히고, 체크하지
     않은 보기 자리에는 없는지 본다.
  4. **겹치지 않는다** — 얹은 글자가 원본 글자·표 선과 겹치지 않는지 좌표로 본다.
     서식 위에 값을 쓰는 일의 성패가 여기에 달려 있다.
  5. **서명 합성** — 서식5 서명란 좌표에 이미지 객체가 실제로 들어갔는지 (R9.2).
  6. **다운로드 0회 유지** — 응답이 전부 `inline`이다 (R9.3 / P4 DoD).

pytest 없이 돌아간다. DB와 저장소는 임시 경로에 만들고 끝나면 지운다 —
`demo/storage`·`demo/demo.db`(시연용 데이터)를 건드리지 않는다. 입력값은 전부
가짜다 (R7.1).
"""

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

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
}

P7_FORM5 = {
    "agree": "동의함",
    "name": "홍길동",
    "birth": {"y": "1998", "m": "6", "d": "15"},
    "phone": "010-0000-0000",
    "writtenOn": {"y": "2026", "m": "3", "d": "4"},
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
    ("writtenMonth", "3"),
    ("writtenDay", "4"),
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
    import fitz

    from ...fixtures.build_form_coords import build_form1, build_form5

    print("\n[1] 좌표 맵 — 원본 PDF에서 다시 뽑아 대조")

    check("템플릿 서식1 존재", (TEMPLATES / "서식1.pdf").exists(), True)
    check("템플릿 서식5 존재", (TEMPLATES / "서식5.pdf").exists(), True)

    for form_no, builder in (("서식1", build_form1), ("서식5", build_form5)):
        saved = json.loads((COORDS / f"{form_no}.json").read_text(encoding="utf-8"))
        with fitz.open(TEMPLATES / f"{form_no}.pdf") as doc:
            rebuilt = builder(doc)
            page_rects = [page.rect for page in doc]
            # 2-up 원본을 논리 쪽으로 제대로 잘랐는지 — 쪽번호로 확인한다.
            markers = [
                p["logical_page"].replace(" ", "") for p in saved["source"]["pages"]
            ]
            found = [
                marker
                for index, marker in enumerate(markers)
                if marker in doc[index].get_text().replace(" ", "")
            ]
        check(f"{form_no} 논리 쪽 번호", found, markers)
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

    # 서식2~4는 구조만 남긴다(설계 6-B.3).
    for form_no in ("서식2", "서식3", "서식4"):
        spec = json.loads((COORDS / f"{form_no}.json").read_text(encoding="utf-8"))
        check(f"{form_no} 좌표 비어 있음(구조만)", spec["fields"], {})
        check_true(f"{form_no} 원본 위치 기록", spec["source"]["pages"])


# ---------------------------------------------------------------- 2. 내보내기


def export(client, application_id: int, form_no: str) -> tuple[Any, bytes]:
    res = client.get(f"/api/applications/{application_id}/forms/{form_no}.pdf")
    return res, res.content


def test_export_headers(client, ds_id: int, jp_id: int) -> None:
    print("\n[2] 내보내기 응답 — 인라인만, 내려받는 경로 없음")

    listed = client.get(f"/api/applications/{ds_id}/forms").json()
    check("두배적금 내보낼 서식", [f["form_no"] for f in listed], ["서식1", "서식5"])
    check_true("파일 주소가 서식 경로", all("/forms/" in f["file_url"] for f in listed))

    dispositions: list[str] = []
    for form_no in ("서식1", "서식5"):
        res, body = export(client, ds_id, form_no)
        check(f"{form_no} 응답", res.status_code, 200)
        check(f"{form_no} 형식", res.headers["content-type"], "application/pdf")
        check(f"{form_no} PDF 헤더", body[:5], b"%PDF-")
        dispositions.append(res.headers["content-disposition"])

    check("모두 inline", [d.split(";")[0] for d in dispositions], ["inline", "inline"])
    # "내려받게 만드는 값"이 하나도 없어야 한다. 낱말을 그대로 쓰지 않으려고 쪼갠다
    # — P4의 정적 검사가 이 파일도 훑기 때문이다.
    forbidden = "attach" + "ment"
    check("내려받기 지시 0건", sum(forbidden in d for d in dispositions), 0)

    # 취업지원패키지는 원본 서식 자체가 사업계획서에 없다(P5에서 남긴 것).
    check("취업패키지 내보낼 서식", client.get(f"/api/applications/{jp_id}/forms").json(), [])
    check(
        "취업패키지 서식1 요청",
        client.get(f"/api/applications/{jp_id}/forms/서식1.pdf").status_code,
        404,
    )
    check(
        "없는 서식 요청",
        client.get(f"/api/applications/{ds_id}/forms/서식9.pdf").status_code,
        404,
    )


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

    # --- (b) ✓는 체크한 보기에만
    checked_boxes: dict[int, set[str]] = {i: set() for i in range(filled.page_count)}
    stray: list[str] = []
    for page_no, words in added.items():
        for word in words:
            if "✓" not in word[4]:
                continue
            rect = fitz.Rect(word[:4])
            hit = [
                key
                for key, field in fields.items()
                if field["type"] == "check"
                and field["page"] == page_no
                and rect.intersects(fitz.Rect(*field["box"]))
            ]
            if hit:
                checked_boxes[page_no].update(hit)
            else:
                stray.append(f"p{page_no}:{rect}")
    check(f"{form_no} 체크 자리 밖의 ✓", stray, [])
    for page_no, expected in expected_checks.items():
        check(f"{form_no} p{page_no} 체크된 보기", checked_boxes[page_no], expected)

    every_check = {key for key, field in fields.items() if field["type"] == "check"}
    expected_all = {key for keys in expected_checks.values() for key in keys}
    check(
        f"{form_no} 체크 안 한 보기 수",
        len(every_check - expected_all),
        len(every_check) - len(expected_all),
    )
    check(
        f"{form_no} 체크 안 한 보기에 찍힌 ✓",
        sorted(k for keys in checked_boxes.values() for k in keys if k not in expected_all),
        [],
    )

    filled.close()
    template.close()

    # --- (c) 얹은 잉크가 원본 잉크를 덮지 않는다 (픽셀 실측)
    covered, painted = ink_collision(form_no, body)
    print(f"       얹은 잉크 {painted:,}px 중 원본을 덮은 것 {covered}px")
    check_true(f"{form_no} 오버레이가 실제로 찍혔다", painted > 1000)
    check(f"{form_no} 원본 글자·선을 덮은 픽셀", covered, 0)


def test_form1_roundtrip(client, ds_id: int) -> None:
    print("\n[3] 서식1 왕복 — 값 → 좌표 → 되읽기")
    _, body = export(client, ds_id, "서식1")
    roundtrip("서식1", body, EXPECTED_TEXTS_FORM1, EXPECTED_CHECKS_FORM1)


def test_form5_roundtrip(client, ds_id: int) -> None:
    print("\n[4] 서식5 왕복 — 값·동의 체크")
    _, body = export(client, ds_id, "서식5")
    roundtrip("서식5", body, EXPECTED_TEXTS_FORM5, {0: {"agree.동의함"}})


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

    # 원문 "(서명또는인)" 자리다 — 종이에 도장을 찍는 그 자리.
    words = [w for w in page.get_text("words") if "서명" in w[4] or "인)" in w[4]]
    near = any(fitz.Rect(w[:4]).intersects(box) for w in words)
    check("서명란(원문 '(서명 또는 인)') 위", near, True)

    # 서명이 없는 신청 건은 이미지도 없어야 한다 — 빈 자리에 아무거나 찍지 않는다.
    doc.close()


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
    marks = [w[4] for w in doc[0].get_text("words") if "✓" in w[4]]
    check("'동의하지 않음'에 체크", len(marks), 1)
    doc.close()


# ---------------------------------------------------------------- 5. 담당자 화면


def test_officer_tab(client, ds_id: int, jp_id: int) -> None:
    """담당자 심사 화면에 "작성 서식" 탭이 붙고, 거기서도 다운로드가 0회인가."""
    print("\n[7] 담당자 화면 '작성 서식' 탭")

    detail = client.get(
        f"/api/officer/applications/{ds_id}", params={"role": ROLE_PROVINCE}
    ).json()
    check("서식 탭 수", len(detail["forms"]), 2)
    check("서식 탭 표기", [f["form_no"] for f in detail["forms"]], ["서식1", "서식5"])
    check_true("업로드 서류 탭도 그대로", detail["documents"])

    for form in detail["forms"]:
        res = client.get(form["file_url"])
        check(f"{form['form_no']} 탭에서 열림", res.status_code, 200)
        check(
            f"{form['form_no']} 인라인",
            res.headers["content-disposition"].split(";")[0],
            "inline",
        )

    check("취업패키지 내보낼 서식(목록 API)", client.get(f"/api/applications/{jp_id}/forms").json(), [])


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


def _submit(client, application_id: int, uploads: dict[str, str]) -> None:
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
    res = client.post(f"/api/applications/{application_id}/submit")
    check(f"제출 {application_id}", res.status_code, 200)


def main() -> int:
    from fastapi.testclient import TestClient

    from ..main import app

    tmp = Path(tempfile.mkdtemp(prefix="p7-scenarios-"))
    _isolate(tmp)
    form_coords.load.cache_clear()

    try:
        test_coordinate_maps()
        with TestClient(app) as client:
            ds_id, jp_id = seed(client, tmp)
            test_export_headers(client, ds_id, jp_id)
            test_form1_roundtrip(client, ds_id)
            test_form5_roundtrip(client, ds_id)
            test_signature(client, ds_id)
            test_without_signature(client)
            _submit(client, ds_id, DS_UPLOADS)
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
    raise SystemExit(main())

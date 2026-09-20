"""서식 템플릿 PDF → 필드 좌표 맵 JSON (P7).

저장소 루트에서:

    PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python -m demo.fixtures.build_form_coords

이 파일의 원칙 하나: **좌표를 사람이 적지 않는다.**

값을 넣을 자리는 전부 원본 PDF에서 뽑는다. 뽑는 근거는 둘뿐이다.

  1. **표 선(벡터)** — `page.get_drawings()`로 수직·수평선을 모아 격자를 만들고,
     "라벨 칸의 바로 오른쪽 칸"처럼 표 구조로 자리를 지목한다.
  2. **글자 위치** — `page.get_text("rawdict")`의 글자별 `bbox`·`origin`(기준선).
     `□` 글자의 원점에 `✓`를 얹고, "은행명 :" 다음 빈자리에 값을 쓴다.

사람이 적는 것은 **앵커 문구**(원문에 있는 말)와 여백 상수(3pt)뿐이다. 그래서
원본 PDF가 개정돼 표가 밀려도 이 스크립트를 다시 돌리면 좌표가 따라온다.

산출물은 `form_coords/서식1.json`·`서식5.json`이고, 서식2~4는 원본 위치만 적힌
빈 좌표 맵을 남긴다(설계 6-B.3 — 데모 구현 대상은 2종).
"""

import json
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from .cut_templates import DEFERRED, GUIDELINE, TEMPLATES_SPEC

FIXTURES = Path(__file__).resolve().parent
TEMPLATES = FIXTURES / "templates"
COORDS = FIXTURES / "form_coords"

#: 값 글자와 칸 선 사이 여백. 유일한 사람 손 상수다.
PAD = 3.0
#: 칸 안에서 쓸 수 있는 글자 크기 범위. 원본 서식 글자(7.8~10pt)에 맞춘다.
MIN_SIZE, MAX_SIZE = 7.0, 10.0

#: 가운뎃점 이형(원문은 ·, ･, ․ 가 섞여 있다)과 괄호를 한 글자로 모은다.
_MIDDOTS = "·･․‧⋅∙・"


def norm(text: str) -> str:
    """앵커 비교용 정규화 — 공백 제거 + 가운뎃점 통일 + 전각 정리."""
    flat = unicodedata.normalize("NFKC", text)
    flat = re.sub(r"\s+", "", flat)
    return "".join("·" if c in _MIDDOTS else c for c in flat)


# ---------------------------------------------------------------- 쪽 한 장 읽기


@dataclass
class Char:
    c: str
    x0: float
    y0: float
    x1: float
    y1: float
    ox: float
    oy: float
    size: float


@dataclass
class Line:
    chars: list[Char]
    text: str = ""
    #: 정규화 문자열의 i번째 글자가 `chars`의 몇 번째인지
    index: list[int] = field(default_factory=list)

    def build(self) -> "Line":
        parts: list[str] = []
        idx: list[int] = []
        for i, ch in enumerate(self.chars):
            piece = norm(ch.c)
            for _ in piece:
                idx.append(i)
            parts.append(piece)
        self.text = "".join(parts)
        self.index = idx
        return self

    @property
    def baseline(self) -> float:
        return max(c.oy for c in self.chars)


@dataclass
class Sheet:
    """템플릿 한 쪽의 글자와 표 선."""

    number: int
    width: float
    height: float
    lines: list[Line]
    vlines: list[tuple[float, float, float]]  # (x, y0, y1)
    hlines: list[tuple[float, float, float]]  # (y, x0, x1)

    # -- 글자 -------------------------------------------------------------
    def find(self, anchor: str, y_hint: float | None = None) -> tuple[Line, int, int]:
        """앵커 문구가 있는 줄과 글자 구간을 찾는다."""
        needle = norm(anchor)
        hits: list[tuple[float, Line, int, int]] = []
        for line in self.lines:
            start = line.text.find(needle)
            while start >= 0:
                end = start + len(needle) - 1
                distance = 0.0 if y_hint is None else abs(line.baseline - y_hint)
                hits.append((distance, line, line.index[start], line.index[end]))
                start = line.text.find(needle, start + 1)
        if not hits:
            raise LookupError(f"앵커를 찾지 못했습니다: {anchor!r} (쪽 {self.number})")
        hits.sort(key=lambda h: h[0])
        if y_hint is None and len(hits) > 1:
            raise LookupError(
                f"앵커가 여러 곳에 있습니다: {anchor!r} — y_hint 를 주세요 "
                f"(후보 y={[round(h[1].baseline, 1) for h in hits]})"
            )
        _, line, first, last = hits[0]
        return line, first, last

    def boxes(self) -> list[tuple[Char, str]]:
        """`□` 글자와 그 뒤에 붙은 보기 문구."""
        out: list[tuple[Char, str]] = []
        for line in self.lines:
            for i, ch in enumerate(line.chars):
                if ch.c != "□":
                    continue
                label: list[str] = []
                for nxt in line.chars[i + 1 :]:
                    if nxt.c == "□":
                        break
                    label.append(nxt.c)
                out.append((ch, "".join(label).strip()))
        return out

    # -- 표 격자 -----------------------------------------------------------
    def cell_at(self, x: float, y: float) -> tuple[float, float, float, float]:
        """점 (x, y)를 둘러싼 표 칸. 선이 없으면 쪽 경계를 쓴다."""
        tol = 0.6
        left = max(
            [vx for vx, y0, y1 in self.vlines if vx <= x + tol and y0 - tol <= y <= y1 + tol],
            default=0.0,
        )
        right = min(
            [vx for vx, y0, y1 in self.vlines if vx >= x - tol and y0 - tol <= y <= y1 + tol],
            default=self.width,
        )
        top = max(
            [hy for hy, x0, x1 in self.hlines if hy <= y + tol and x0 - tol <= x <= x1 + tol],
            default=0.0,
        )
        bottom = min(
            [hy for hy, x0, x1 in self.hlines if hy >= y - tol and x0 - tol <= x <= x1 + tol],
            default=self.height,
        )
        return (left, top, right, bottom)


def read_sheet(page: Any, number: int) -> Sheet:
    raw = page.get_text("rawdict")
    everything: list[Char] = []
    for block in raw["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                for c in span["chars"]:
                    bbox = c["bbox"]
                    everything.append(
                        Char(
                            c=c["c"],
                            x0=bbox[0],
                            y0=bbox[1],
                            x1=bbox[2],
                            y1=bbox[3],
                            ox=c["origin"][0],
                            oy=c["origin"][1],
                            size=span["size"],
                        )
                    )

    # 추출기는 가로 간격이 넓으면 같은 줄을 여러 조각으로 쪼갠다("2026 년" / "월" /
    # "일"). 서식은 빈칸이 곧 기입란이라 그 조각들이 한 줄로 보여야 앵커도 맞고
    # "다음 글자 앞까지"라는 폭 제한도 맞는다. 기준선이 같으면 한 줄로 묶는다.
    lines: list[Line] = []
    bucket: list[Char] = []
    for ch in sorted(everything, key=lambda c: (c.oy, c.ox)):
        if bucket and abs(ch.oy - bucket[0].oy) > 1.0:
            lines.append(Line(sorted(bucket, key=lambda c: c.ox)).build())
            bucket = []
        bucket.append(ch)
    if bucket:
        lines.append(Line(sorted(bucket, key=lambda c: c.ox)).build())

    vlines: set[tuple[float, float, float]] = set()
    hlines: set[tuple[float, float, float]] = set()
    rect = page.rect
    for drawing in page.get_drawings():
        # 원문의 노란 형광 표시가 '선 4개로 닫힌 채움(fill)' 도형이라 그대로 두면
        # 글자 높이짜리 가짜 세로선이 표 격자에 섞인다. 표 선은 전부 획(stroke)이다.
        if "s" not in drawing["type"]:
            continue
        for item in drawing["items"]:
            segments = []
            if item[0] == "l":
                segments.append((item[1], item[2]))
            elif item[0] == "re":
                r = item[1]
                segments += [
                    ((r.x0, r.y0), (r.x1, r.y0)),
                    ((r.x1, r.y0), (r.x1, r.y1)),
                    ((r.x1, r.y1), (r.x0, r.y1)),
                    ((r.x0, r.y1), (r.x0, r.y0)),
                ]
            for a, b in segments:
                ax, ay = (a.x, a.y) if hasattr(a, "x") else a
                bx, by = (b.x, b.y) if hasattr(b, "x") else b
                if not (rect.x0 - 2 <= ax <= rect.x1 + 2 and rect.x0 - 2 <= bx <= rect.x1 + 2):
                    continue  # 자른 쪽 바깥(옆 논리 쪽)의 선은 버린다
                if abs(ax - bx) < 0.6 and abs(ay - by) > 1:
                    vlines.add((round(ax, 2), round(min(ay, by), 2), round(max(ay, by), 2)))
                elif abs(ay - by) < 0.6 and abs(ax - bx) > 1:
                    hlines.add((round(ay, 2), round(min(ax, bx), 2), round(max(ax, bx), 2)))

    return Sheet(
        number=number,
        width=rect.width,
        height=rect.height,
        lines=lines,
        vlines=sorted(vlines),
        hlines=sorted(hlines),
    )


# ---------------------------------------------------------------- 필드 규격


Align = Literal["left", "center"]


@dataclass(frozen=True)
class TextField:
    """값을 적어 넣을 자리 하나."""

    key: str
    anchor: str
    #: cell_right = 앵커가 든 칸의 바로 오른쪽 칸 / after = 같은 줄 앵커 바로 뒤 빈자리
    mode: Literal["cell_right", "after"] = "cell_right"
    y_hint: float | None = None
    align: Align = "left"
    note: str = ""


@dataclass(frozen=True)
class CheckGroup:
    """체크박스 한 묶음. 앵커가 든 칸의 오른쪽 칸 안에 있는 `□`만 본다."""

    key: str
    anchor: str
    options: tuple[str, ...]
    y_hint: float | None = None
    #: 앵커 칸 자체에 체크박스가 있는 경우(라벨과 보기가 한 칸)
    same_cell: bool = False


@dataclass(frozen=True)
class ImageField:
    """이미지를 얹을 자리(서식5 전자서명)."""

    key: str
    anchor: str
    y_hint: float | None = None
    #: 앵커 글자 영역을 기준으로 한 확장 여백 (좌, 상, 우, 하)
    grow: tuple[float, float, float, float] = (0, 0, 0, 0)
    note: str = ""


# ---- 서식1 -----------------------------------------------------------------
# y_hint 는 원본에서 그 문구가 실제로 놓인 줄의 기준선이다(템플릿 좌표).
# 같은 낱말이 여러 줄에 나오는 경우(이름·연락처·기간)를 가르는 데만 쓴다.

FORM1_TEXTS_P0 = (
    TextField("priorName", "(사업명:", mode="after", y_hint=177.3),
    TextField("priorPeriod", "기간:", mode="after", y_hint=177.3),
    TextField("priorAmount", "수령액:", mode="after", y_hint=177.3),
    TextField("name", "신청자 이름", y_hint=210.7),
    TextField("birth", "생년월일", y_hint=210.7),
    TextField("address", "주 소", y_hint=232.1),
    TextField("mobile", "휴대폰", y_hint=253.3),
    TextField("email", "이메일", y_hint=253.3),
    TextField("ecName", "이 름", y_hint=278.4),
    TextField("ecRelation", "관 계", y_hint=278.4),
    TextField("ecContact", "연락처", y_hint=278.4),
    TextField("workplaceName", "근무처 명 :", mode="after", y_hint=499.6),
    TextField("workplaceAddress", "근무처 주소 :", mode="after", y_hint=530.1),
    TextField("workplaceContact", "근무처 연락처 :", mode="after", y_hint=540.3),
)

FORM1_CHECKS_P0 = (
    CheckGroup(
        "savingPurpose",
        "다음 중 1항목 선택",
        (
            "주거자금",
            "창업자금",
            "본인 및 자녀의 교육·훈련비",
            "대출상환",
            "결혼자금",
            "기타 꿈을 위한 준비자금",
        ),
        same_cell=True,
    ),
    CheckGroup("priorJoined", "유사 자산형성사업 참여 여부", ("미참여", "참여")),
    CheckGroup("gender", "성 별", ("남", "여")),
    CheckGroup(
        "residencePeriod",
        "거주기간",
        (
            "1년 미만",
            "1년 이상 ~ 2년 미만",
            "2년 이상 ~ 3년 미만",
            "3년 이상 ~ 4년 미만",
            "4년 이상 ~ 5년 미만",
            "5년 이상",
        ),
        y_hint=320.2,
    ),
    CheckGroup(
        "householdType",
        "가구 특성",
        ("기초생활보장급여 수급 가구", "법정 차상위계층 가구", "그 외 일반 가구"),
    ),
    CheckGroup(
        "householdSize",
        "가구원 수",
        ("1인", "2인", "3인", "4인", "5인", "6인", "7인", "8인", "9인", "10인 이상"),
        y_hint=375.6,
    ),
    CheckGroup(
        "workType",
        "근로유형",
        (
            "상용직(노동계약기간 1년 이상)",
            "임시직(노동계약기간 1개월 이상 1년 미만)",
            "일용직(노동계약기간 1개월 미만)",
            "기타(상용직, 임시직, 일용직 혼합)",
        ),
    ),
    CheckGroup(
        "workPeriod",
        "근로기간",
        ("1년 미만", "1년 이상 ~ 2년 미만", "2년 이상 ~ 3년 미만", "3년 이상"),
        y_hint=470.4,
    ),
    CheckGroup(
        "workplaceRegion",
        "근 무 처",
        ("전북특별자치도 내 지역", "전북특별자치도 외 지역"),
        y_hint=520.0,
    ),
    CheckGroup(
        "adminWorkForm",
        "근 무 처",
        ("무기계약 근로자", "기간제 근로자"),
        y_hint=520.0,
    ),
)

FORM1_TEXTS_P1 = (
    TextField("bankName", "(은행명 :", mode="after", y_hint=103.7),
    TextField("accountNo", "계좌번호 :", mode="after", y_hint=103.7),
    TextField("accountHolder", "예금주 :", mode="after", y_hint=103.7),
    TextField(
        "writtenMonth", "2026.", mode="after", y_hint=297.4, align="center",
        note="원문 '2026. . .' 의 첫 빈칸(월)",
    ),
    TextField(
        "writtenDay", "2026..", mode="after", y_hint=297.4, align="center",
        note="원문 '2026. . .' 의 둘째 빈칸(일)",
    ),
)

FORM1_CHECKS_P1 = (
    CheckGroup("monthlyDeposit", "납입금액", ("월 10만원",)),
    CheckGroup(
        "referralPaths",
        "기타사항",
        (
            "TV 자막광고·신문 등 방송매체",
            "홈페이지(도, 시군, 청년센터 등)",
            "SNS",
            "현수막",
            "전광판, 버스 등 옥외매체",
            "지인소개",
            "기타",
        ),
    ),
)

# ---- 서식5 -----------------------------------------------------------------

FORM5_TEXTS = (
    TextField("writtenMonth", "2026 년", mode="after", align="center"),
    TextField("writtenDay", "2026 년 월", mode="after", align="center"),
    TextField("name", "성 명:", mode="after"),
    TextField("birth", "생년월일:", mode="after"),
    TextField("phone", "전화번호:", mode="after"),
)

FORM5_CHECKS = (
    # 보기 두 개가 질문 아래 별도 칸에 있다. 질문 칸 기준으로 오른쪽을 보면 빗나가므로
    # 보기 문구 자체를 앵커로 삼아 그 칸을 집는다.
    CheckGroup("agree", "동의함", ("동의함", "동의하지 않음"), same_cell=True),
)

FORM5_IMAGES = (
    ImageField(
        "signature",
        "(서명또는인)",
        grow=(0, 10, 0, 6),
        note=(
            "원문의 '(서명 또는 인)' 자리에 캔버스 전자서명을 얹는다. 종이에 도장을 "
            "찍는 자리와 같다 — 배경이 투명한 PNG라 원문 글자가 비쳐 보인다."
        ),
    ),
)


# ---------------------------------------------------------------- 좌표 뽑기


def _text_field(sheet: Sheet, spec: TextField) -> dict[str, Any]:
    line, first, last = sheet.find(spec.anchor, spec.y_hint)
    head, tail = line.chars[first], line.chars[last]
    baseline = tail.oy
    size = min(max(tail.size, MIN_SIZE), MAX_SIZE)

    if spec.mode == "cell_right":
        # 앵커가 든 칸 → 그 오른쪽 칸. 표 구조가 자리를 지목한다.
        label_cell = sheet.cell_at((head.x0 + tail.x1) / 2, baseline - size * 0.3)
        probe_x = label_cell[2] + 1.0
        cell = sheet.cell_at(probe_x, baseline - size * 0.3)
        box = (cell[0] + PAD, cell[1] + 1.0, cell[2] - PAD, cell[3] - 1.0)
        # 칸 한가운데 기준선. 칸이 여러 줄이면 첫 줄 기준선을 쓴다.
        y = (cell[1] + cell[3]) / 2 + size * 0.35
    else:  # after — 같은 줄 앵커 바로 뒤
        after = [c for c in line.chars[last + 1 :] if c.c.strip()]
        cell = sheet.cell_at(tail.x1 + 1.0, baseline - size * 0.3)
        limit = min(after[0].x0 - 1.0, cell[2] - PAD) if after else cell[2] - PAD
        box = (tail.x1 + PAD, min(tail.y0, baseline - size), limit, max(tail.y1, baseline + 1))
        y = baseline

    if box[2] - box[0] < 8:
        raise ValueError(f"{spec.key}: 값을 넣을 폭이 너무 좁습니다 ({box})")

    return {
        "type": "text",
        "page": sheet.number,
        "x": round(box[0], 2),
        "y": round(y, 2),
        "size": round(size, 2),
        "align": spec.align,
        "box": [round(v, 2) for v in box],
        "anchor": spec.anchor,
        "mode": spec.mode,
        **({"note": spec.note} if spec.note else {}),
    }


def _check_group(sheet: Sheet, spec: CheckGroup) -> dict[str, dict[str, Any]]:
    line, first, last = sheet.find(spec.anchor, spec.y_hint)
    head, tail = line.chars[first], line.chars[last]
    probe_y = tail.oy - tail.size * 0.3
    cell = sheet.cell_at((head.x0 + tail.x1) / 2, probe_y)
    if not spec.same_cell:
        cell = sheet.cell_at(cell[2] + 1.0, probe_y)

    inside = [
        (ch, label)
        for ch, label in sheet.boxes()
        if cell[0] - 0.5 <= ch.x0 and ch.x1 <= cell[2] + 0.5
        and cell[1] - 0.5 <= ch.y0 and ch.y1 <= cell[3] + 0.5
    ]
    if not inside:
        raise LookupError(f"{spec.key}: 칸 {cell} 안에 체크박스가 없습니다")

    out: dict[str, dict[str, Any]] = {}
    for option in spec.options:
        target = norm(option)
        matches = [
            (len(norm(label)), ch, label)
            for ch, label in inside
            if norm(label).startswith(target)
        ]
        if not matches:
            raise LookupError(
                f"{spec.key}: 보기 {option!r}에 해당하는 체크박스가 없습니다. "
                f"칸 안 보기 = {[label for _, label in inside]}"
            )
        matches.sort(key=lambda m: m[0])  # 가장 짧게 들어맞는 것이 제 짝이다
        _, ch, label = matches[0]
        out[f"{spec.key}.{option}"] = {
            "type": "check",
            "page": sheet.number,
            "x": round(ch.ox, 2),
            "y": round(ch.oy, 2),
            "size": round(ch.size, 2),
            "box": [round(ch.x0, 2), round(ch.y0, 2), round(ch.x1, 2), round(ch.y1, 2)],
            "label": label,
        }
    return out


def _image_field(sheet: Sheet, spec: ImageField) -> dict[str, Any]:
    line, first, last = sheet.find(spec.anchor, spec.y_hint)
    head, tail = line.chars[first], line.chars[last]
    left, top, right, bottom = spec.grow
    box = (head.x0 - left, head.y0 - top, tail.x1 + right, tail.y1 + bottom)
    return {
        "type": "image",
        "page": sheet.number,
        "box": [round(v, 2) for v in box],
        "anchor": spec.anchor,
        **({"note": spec.note} if spec.note else {}),
    }


def build_form1(doc: Any) -> dict[str, Any]:
    p0 = read_sheet(doc[0], 0)
    p1 = read_sheet(doc[1], 1)
    fields: dict[str, Any] = {}
    for spec in FORM1_TEXTS_P0:
        fields[spec.key] = _text_field(p0, spec)
    for group in FORM1_CHECKS_P0:
        fields.update(_check_group(p0, group))
    for spec in FORM1_TEXTS_P1:
        fields[spec.key] = _text_field(p1, spec)
    for group in FORM1_CHECKS_P1:
        fields.update(_check_group(p1, group))
    return fields


def build_form5(doc: Any) -> dict[str, Any]:
    p0 = read_sheet(doc[0], 0)
    fields: dict[str, Any] = {}
    for spec in FORM5_TEXTS:
        fields[spec.key] = _text_field(p0, spec)
    for group in FORM5_CHECKS:
        fields.update(_check_group(p0, group))
    for spec in FORM5_IMAGES:
        fields[spec.key] = _image_field(p0, spec)
    return fields


BUILDERS = {"서식1": build_form1, "서식5": build_form5}


def build_all(out_dir: Path = COORDS) -> list[Path]:
    import fitz

    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for spec in TEMPLATES_SPEC:
        template = TEMPLATES / f"{spec.form_no}.pdf"
        if not template.exists():
            raise FileNotFoundError(
                f"템플릿이 없습니다: {template}\n"
                "먼저 `python -m demo.fixtures.cut_templates` 를 돌리세요."
            )
        with fitz.open(template) as doc:
            fields = BUILDERS[spec.form_no](doc)
            payload = {
                "form_no": spec.form_no,
                "title": spec.title,
                "template": f"templates/{spec.form_no}.pdf",
                "source": {
                    "file": spec.source,
                    "layout": "2-up (물리 1쪽 = 논리 2쪽)",
                    "pages": [
                        {
                            "physical_page": cut.physical_page,
                            "half": "오른쪽" if cut.half else "왼쪽",
                            "logical_page": cut.marker,
                        }
                        for cut in spec.cuts
                    ],
                },
                "generated_by": "demo/fixtures/build_form_coords.py",
                "note": (
                    "좌표는 원본 PDF의 표 선(get_drawings)과 글자 원점"
                    "(get_text('rawdict'))에서 뽑았다. 손으로 적은 값이 아니다."
                ),
                "fields": fields,
            }
        target = out_dir / f"{spec.form_no}.json"
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        written.append(target)
        checks = sum(1 for f in fields.values() if f["type"] == "check")
        texts = sum(1 for f in fields.values() if f["type"] == "text")
        images = sum(1 for f in fields.values() if f["type"] == "image")
        print(f"  {spec.form_no}: 글자 {texts} · 체크 {checks} · 이미지 {images} → {target}")

    for form_no, cut in DEFERRED.items():
        target = out_dir / f"{form_no}.json"
        payload = {
            "form_no": form_no,
            "template": None,
            "source": {
                "file": GUIDELINE,
                "layout": "2-up (물리 1쪽 = 논리 2쪽)",
                "pages": [
                    {
                        "physical_page": cut.physical_page,
                        "half": "오른쪽" if cut.half else "왼쪽",
                        "logical_page": cut.marker,
                    }
                ],
            },
            "note": (
                "데모의 PDF 내보내기 대상은 서식1·서식5 2종이다(설계 6-B.3). "
                "이 서식은 구조만 남겨 두었고 좌표는 비어 있다. 채우려면 "
                "cut_templates.TEMPLATES_SPEC 에 위 원본 위치를 추가한 뒤 "
                "build_form_coords.py 에 앵커 규격을 적으면 된다."
            ),
            "fields": {},
        }
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        written.append(target)
        print(f"  {form_no}: 빈 좌표 맵(구조만) → {target}")

    return written


def main() -> int:
    print("서식 좌표 맵 만들기 (원본 표 선·글자 원점에서 추출)")
    build_all()
    return 0


if __name__ == "__main__":
    sys.exit(main())

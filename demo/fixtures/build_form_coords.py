"""원본 서식 PDF → 필드 좌표 맵 JSON.

저장소 루트에서:

    PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python -m demo.fixtures.build_form_coords

이 파일의 원칙 하나: **좌표를 사람이 적지 않는다.**

값을 넣을 자리는 전부 원본 PDF에서 뽑는다. 뽑는 근거는 둘뿐이다.

  1. **표 선(벡터)** — `page.get_drawings()`로 수직·수평선을 모아 격자를 만들고,
     "라벨 칸의 바로 오른쪽 칸"처럼 표 구조로 자리를 지목한다.
    2. **글자 위치** — `page.get_text("rawdict")`의 글자별 `bbox`·`origin`(기준선).
     "예"와 "아니오" 텍스트 자체를 라디오 선택 영역으로 쓰고, 선택 시 글자 둘레에
     타원을 그린다. "은행명 :" 다음 빈자리에 값을 쓴다.

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

from .cut_templates import TEMPLATES_SPEC

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
    font: str


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

    def option_boxes(self) -> list[tuple[Char, str, list[Char]]]:
        """`□` 글자와 다음 보기 전까지의 글자·문구 bbox를 반환한다."""
        out: list[tuple[Char, str, list[Char]]] = []
        for line in self.lines:
            for i, ch in enumerate(line.chars):
                if ch.c not in {"□", "☐"}:
                    continue
                label_chars: list[Char] = []
                for nxt in line.chars[i + 1 :]:
                    if nxt.c in {"□", "☐"}:
                        break
                    label_chars.append(nxt)
                visible_chars = [char for char in label_chars if char.c.strip()]
                out.append((ch, "".join(char.c for char in label_chars).strip(), visible_chars))
        return out

    def boxes(self) -> list[tuple[Char, str]]:
        """`□` 글자와 그 뒤에 붙은 보기 문구."""
        return [(char, label) for char, label, _ in self.option_boxes()]

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
                            font=span.get("font", ""),
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


def font_family(font_name: str) -> str:
    lowered = font_name.lower()
    return "serif" if any(part in lowered for part in ("batang", "myeongjo", "명조", "song", "serif")) else "sans"


@dataclass(frozen=True)
class TextField:
    """값을 적어 넣을 자리 하나."""

    key: str
    anchor: str
    #: cell_right = 앵커가 든 칸의 바로 오른쪽 칸 / after = 같은 줄 앵커 바로 뒤 빈자리
    mode: Literal["cell_right", "after"] = "cell_right"
    y_hint: float | None = None
    align: Align = "left"
    format: Literal["yyyy", "yy", "none"] | None = None
    auto_date_part: Literal["year", "month", "day"] | None = None
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
    TextField("priorName", "사업명 :", mode="after", y_hint=243.5),
    TextField("priorPeriod", "기간 :", mode="after", y_hint=243.5),
    TextField("priorAmount", "수령액 :", mode="after", y_hint=243.5),
    TextField("name", "신청자 이름", y_hint=296.6),
    TextField("birth", "생년월일", y_hint=296.7),
    TextField("address", "주   소", y_hint=326.6),
    TextField("mobile", "휴대폰", y_hint=356.6),
    TextField("email", "이메일", y_hint=356.6),
    TextField("ecName", "이  름", y_hint=391.8),
    TextField("ecRelation", "관  계", y_hint=391.8),
    TextField("ecContact", "연락처", y_hint=391.8),
    TextField("workplaceName", "근무처 명 :", mode="after", y_hint=703.0),
    TextField("workplaceAddress", "근무처 주소 :", mode="after", y_hint=744.39),
    TextField("workplaceContact", "근무처 연락처 :", mode="after", y_hint=758.65),
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
        y_hint=427.7,
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
        y_hint=533.2,
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
        y_hint=647.5,
    ),
    CheckGroup(
        "workplaceRegion",
        "근 무 처",
        ("전북특별자치도 내 지역", "전북특별자치도 외 지역"),
        y_hint=688.6,
    ),
    CheckGroup(
        "adminWorkForm",
        "근 무 처",
        ("무기계약 근로자", "기간제 근로자"),
        y_hint=731.5,
    ),
)

FORM1_TEXTS_P1 = (
    TextField("bankName", "은행명 :", mode="after", y_hint=146.0),
    TextField("accountNo", "계좌번호 :", mode="after", y_hint=146.0),
    TextField("accountHolder", "예금주 :", mode="after", y_hint=146.0),
    TextField(
        "writtenMonth", "2026.", mode="after", y_hint=418.5, align="center", format="none", auto_date_part="month",
        note="원문 '2026. . .' 의 첫 빈칸(월)",
    ),
    TextField(
        "writtenDay", "2026..", mode="after", y_hint=418.5, align="center", format="none", auto_date_part="day",
        note="원문 '2026. . .' 의 둘째 빈칸(일)",
    ),
)

FORM1_CHECKS_P1 = (
    CheckGroup("monthlyDeposit", "납입금액", ("월 10만원",), same_cell=True),
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
    TextField("writtenMonth", "2026 년", mode="after", y_hint=568.0, align="center", format="none", auto_date_part="month"),
    TextField("writtenDay", "2026 년 월", mode="after", y_hint=568.0, align="center", format="none", auto_date_part="day"),
    TextField("name", "성 명:", mode="after", y_hint=620.0),
    TextField("birth", "생년월일:", mode="after", y_hint=668.0),
    TextField("phone", "전화번호:", mode="after", y_hint=694.0),
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

    if box[2] - box[0] < 8 and spec.mode == "after":
        # 원문에서 라벨 칸과 입력 칸이 별도 셀인 경우, 라벨 뒤의 첫 칸이 좁을 수
        # 있다. 다음 실제 격자 칸을 값 칸으로 잡는다.
        boundary = cell[2]
        next_cell = sheet.cell_at(boundary + 1.0, baseline - size * 0.3)
        if next_cell[2] - next_cell[0] >= 8:
            box = (next_cell[0] + PAD, next_cell[1] + 1.0,
                   next_cell[2] - PAD, next_cell[3] - 1.0)
            y = (next_cell[1] + next_cell[3]) / 2 + size * 0.35
    if box[2] - box[0] < 8:
        raise ValueError(f"{spec.key}: 값을 넣을 폭이 너무 좁습니다 ({box})")

    result = {
        "type": "text",
        "page": sheet.number,
        "x": round(box[0], 2),
        "y": round(y, 2),
        "size": round(size, 2),
        "align": spec.align,
        "font_family": font_family(tail.font),
        "box": [round(v, 2) for v in box],
        "anchor": spec.anchor,
        "mode": spec.mode,
        **({"format": spec.format} if spec.format is not None else {}),
        **({"auto_date": True, "date_part": spec.auto_date_part} if spec.auto_date_part else {}),
        **({"note": spec.note} if spec.note else {}),
    }
    if spec.auto_date_part:
        marker = {"year": "년", "month": "월", "day": "일"}[spec.auto_date_part]
        candidates = [ch for row in sheet.lines for ch in row.chars if ch.c == marker and abs(ch.oy - baseline) <= 3.5]
        if not candidates:
            # 두배적금 신청서 날짜는 `2026. . .` 형태다. 점보다 연도 숫자 스팬의
            # 크기·기준선을 기준으로 써, 좁은 점 bbox가 숫자를 축소하지 않게 한다.
            candidates = [ch for row in sheet.lines for ch in row.chars if ch.c.isdigit() and abs(ch.oy - baseline) <= 3.5]
        if candidates:
            reference = min(candidates, key=lambda ch: abs(ch.ox - (box[0] + box[2]) / 2))
            render_baseline = reference.oy + (0.72 if not reference.c.isdigit() else 0.0)
            if spec.key == "consent.form4.year":
                # The printed year marker has a taller lower ink edge than the
                # Noto numerals; a 0.36pt optical lift aligns their 200dpi baselines.
                render_baseline -= 0.36
            result["date_reference"] = {
                "size": round(reference.size, 2), "baseline": round(reference.oy, 2),
                "character": reference.c,
                "render_size_scale": 1.0 if reference.c.isdigit() else 1.1,
                "render_baseline": round(render_baseline, 2),
                "font_family": font_family(reference.font), "glyph_box": [round(reference.x0, 2), round(reference.y0, 2), round(reference.x1, 2), round(reference.y1, 2)],
            }
            # Automatic dates use the adjacent printed glyph's baseline and size.
            # The embedded CJK font's extracted glyph box is slightly taller than
            # the source character span, so reserve vertical ink room without
            # changing the baseline or the narrow month/day column.
            result["box"] = [
                round(box[0], 2), round(box[1] - 2.0, 2),
                round(box[2], 2), round(box[3] + 2.0, 2),
            ]
    return result


def _check_group(sheet: Sheet, spec: CheckGroup) -> dict[str, dict[str, Any]]:
    line, first, last = sheet.find(spec.anchor, spec.y_hint)
    baseline = line.chars[last].oy
    candidates = sheet.option_boxes()
    out: dict[str, dict[str, Any]] = {}
    for option in spec.options:
        target = norm(option)
        matches = [
            (len(norm(label)), ch, label, label_chars)
            for ch, label, label_chars in candidates
            if norm(label).startswith(target)
        ]
        if not matches:
            raise LookupError(f"{spec.key}: 보기 {option!r} 체크 위치를 찾지 못했습니다.")
        matches.sort(key=lambda m: (abs(m[1].oy - (spec.y_hint or baseline)), m[0]))
        _, ch, label, label_chars = matches[0]
        label_box = None
        if label_chars:
            label_box = [
                round(min(char.x0 for char in label_chars), 2),
                round(min(char.y0 for char in label_chars), 2),
                round(max(char.x1 for char in label_chars), 2),
                round(max(char.y1 for char in label_chars), 2),
            ]
        out[f"{spec.key}.{option}"] = {
            "type": "check",
            "page": sheet.number,
            "x": round(ch.ox, 2),
            "y": round(ch.oy, 2),
            "size": round(ch.size, 2),
            "box": [round(ch.x0, 2), round(ch.y0, 2), round(ch.x1, 2), round(ch.y1, 2)],
            **({"label_box": label_box} if label_box else {}),
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


def _choice_line(sheet: Sheet, key: str, y_hint: float) -> dict[str, dict[str, Any]]:
    boxes = [item for item in sheet.option_boxes() if abs(item[0].oy - y_hint) <= 5.0]
    out = {}
    for option in ("동의함", "동의하지 않음"):
        hit = next(((char, label, label_chars) for char, label, label_chars in boxes
                    if norm(label).startswith(norm(option))), None)
        if hit is None:
            raise LookupError(f"{key}: '{option}' 선택 위치를 못 찾았습니다.")
        char, label, label_chars = hit
        out[f"{key}.{option}"] = {
            "type": "check", "page": sheet.number, "x": round(char.ox, 2),
            "y": round(char.oy, 2), "size": round(char.size, 2),
            "box": [round(char.x0, 2), round(char.y0, 2), round(char.x1, 2), round(char.y1, 2)],
            "label_box": [
                round(min(c.x0 for c in label_chars), 2),
                round(min(c.y0 for c in label_chars), 2),
                round(max(c.x1 for c in label_chars), 2),
                round(max(c.y1 for c in label_chars), 2),
            ] if label_chars else None,
            "label": label,
        }
    return out


def _radio_pair(sheet: Sheet, key: str, y_hint: float) -> dict[str, dict[str, Any]]:
    line, first, last = sheet.find("예, 아니오", y_hint)
    anchor_index = next((i for i, char_index in enumerate(line.index) if char_index == first), 0)
    baseline = line.chars[last].oy
    out = {}
    all_chars = line.chars[first:last + 1]
    group_cell = sheet.cell_at((min(ch.x0 for ch in all_chars) + max(ch.x1 for ch in all_chars)) / 2, baseline - 2)
    group_box = [round(group_cell[0] + 2, 2), round(min(ch.y0 for ch in all_chars) - 1, 2),
                 round(group_cell[2] - 2, 2), round(max(ch.y1 for ch in all_chars) + 1, 2)]
    for label in ("예", "아니오"):
        at = line.text.find(norm(label), anchor_index)
        if at < 0:
            raise LookupError(f"{key}: '{label}' 위치를 못 찾았습니다.")
        selected = [line.chars[i] for i in line.index[at : at + len(norm(label))]]
        box = [
            min(ch.x0 for ch in selected), min(ch.y0 for ch in selected),
            max(ch.x1 for ch in selected), max(ch.y1 for ch in selected),
        ]
        out[f"{key}.{label}"] = {
            "type": "check", "control": "radio_text", "page": sheet.number,
            "x": round(box[0], 2), "y": round(box[3], 2),
            "size": round(max(ch.size for ch in selected), 2),
            "box": [round(value, 2) for value in box],
            "label": label,
            "group_box": group_box,
            "font_family": font_family(selected[0].font),
        }
    return out


def _text_fields(sheet: Sheet, specs: tuple[TextField, ...]) -> dict[str, dict[str, Any]]:
    return {spec.key: _text_field(sheet, spec) for spec in specs}


def _mask_text(sheet: Sheet, marker: str, occurrence: int = 0) -> list[float]:
    needle = norm(marker)
    hits = []
    for line in sheet.lines:
        start = line.text.find(needle)
        while start >= 0:
            end = start + len(needle) - 1
            hits.append([line.chars[line.index[i]] for i in range(start, end + 1)])
            start = line.text.find(needle, start + 1)
    if occurrence >= len(hits):
        raise LookupError(f"가림 영역 문구 위치를 못 찾았습니다: {marker}")
    chars = hits[occurrence]
    return [round(min(c.x0 for c in chars) - .4, 2), round(min(c.y0 for c in chars) - .3, 2),
            round(max(c.x1 for c in chars) + .4, 2), round(max(c.y1 for c in chars) + .3, 2)]


def _build_self_check(doc: Any):
    sheet = read_sheet(doc[0], 0)
    fields = {}
    for number, y in enumerate((193.9, 221.7, 256.9, 292.3, 320.0, 480.1, 640.1, 691.9), 1):
        fields.update(_radio_pair(sheet, f"self_check.{number}", y))
    return fields, []


def _build_form3(doc: Any):
    sheet = read_sheet(doc[0], 0)
    fields = {}
    fields.update(_choice_line(sheet, "consent.privacy", 494.6))
    fields.update(_choice_line(sheet, "consent.uniqueId", 598.8))
    fields.update(_text_fields(sheet, (
        TextField("consent.form3.year", "20", mode="after", y_hint=740.1, format="yy", auto_date_part="year"),
        TextField("consent.form3.month", "년", mode="after", y_hint=740.1, align="center", format="none", auto_date_part="month"),
        TextField("consent.form3.day", "년 월", mode="after", y_hint=740.1, align="center", format="none", auto_date_part="day"),
    )))
    return fields, []


def _build_form4(doc: Any):
    sheet = read_sheet(doc[0], 0)
    fields = _choice_line(sheet, "consent.thirdParty", 545.8)
    fields.update(_text_fields(sheet, (
        TextField("consent.form4.year", "20", mode="after", y_hint=602.5, format="yy", auto_date_part="year"),
        TextField("consent.form4.month", "년", mode="after", y_hint=602.5, align="center", format="none", auto_date_part="month"),
        TextField("consent.form4.day", "년 월", mode="after", y_hint=602.5, align="center", format="none", auto_date_part="day"),
    )))
    return fields, []


def _build_form5(doc: Any):
    sheet = read_sheet(doc[0], 0)
    fields = _text_fields(sheet, FORM5_TEXTS)
    fields.update(_choice_line(sheet, "agree", 442.8))
    fields["signature"] = _image_field(sheet, ImageField("signature", "(서명또는인)", y_hint=615.5, grow=(1.5, 1.5, 1.5, 1.5)))
    fields["name"]["box"][2] = round(fields["signature"]["box"][0] - 2.0, 2)
    return fields, []


def _build_job_application(doc: Any):
    sheet = read_sheet(doc[0], 0)
    specs = (
        TextField("name", "성  명", y_hint=139.1), TextField("birth", "생년월일", y_hint=139.1),
        TextField("address", "주  소", y_hint=170.7), TextField("mobile", "연락처", y_hint=189.3),
        TextField("email", "이메일", y_hint=189.3),
        TextField("bankName", "계좌번호(", mode="after", y_hint=210.1),
        TextField("accountNo", "은행)", mode="after", y_hint=210.1),
        TextField("job.photo.paymentDate", "결 제 일", y_hint=282.0),
        TextField("job.photo.cost", "사진비용", y_hint=282.0),
    )
    fields = {spec.key: _text_field(sheet, spec) for spec in specs}
    for item, rows, detail_rows, detail_label in (
        ("interview", (310.9, 358.5), (329.7, 377.2), "응시직군"),
        ("suit", (405.9, 453.5), (424.6, 472.2), "대여비용"),
    ):
        for turn in (1, 2):
            prefix = f"job.{item}.{turn}"
            for field_key, anchor, y in (("company", "면접기업", rows[turn - 1]),
                                         ("location", "소재지", rows[turn - 1]),
                                         ("date", "면접일", detail_rows[turn - 1]),
                                         ("detail", detail_label, detail_rows[turn - 1])):
                key = f"{prefix}.{field_key}"
                field = _text_field(sheet, TextField(key, anchor, y_hint=y))
                if field_key == "location":
                    sample = _mask_text(sheet, "OO시/군", (turn - 1) + (2 if item == "suit" else 0))
                    field["box"][0] = sample[0]
                    field["x"] = sample[0]
                fields[key] = field
    for turn, row_y, detail_y in ((1, 501.0, 519.7), (2, 548.5, 567.3)):
        prefix = f"job.certificate.{turn}"
        for field_key, anchor, y in (("exam", "시험명", row_y), ("organizer", "시행처", row_y),
                                     ("date", "응시일", detail_y), ("cost", "시험비용", detail_y)):
            key = f"{prefix}.{field_key}"
            field = _text_field(sheet, TextField(key, anchor, y_hint=y))
            if field_key == "organizer":
                sample = _mask_text(sheet, "한국교통안전공단" if turn == 1 else "한국산업인력공단", 0)
                field["box"][0] = sample[0]
                field["x"] = sample[0]
            fields[key] = field
    fields.update(_text_fields(sheet, (
        TextField("job.applicationMonth", "2026년", mode="after", y_hint=647.0, align="center", format="none", auto_date_part="month"),
        TextField("job.applicationDay", "2026년 월", mode="after", y_hint=647.0, align="center", format="none", auto_date_part="day"),
    )))
    fields["job.signature"] = _image_field(sheet, ImageField(
        "job.signature", "(인)", y_hint=688.6, grow=(1.5, 1.5, 1.5, 1.5)))
    for key, option in zip(("subsidy.interview", "subsidy.suit", "subsidy.photo", "subsidy.certificate"),
                           ("면접비", "면접정장비", "면접사진촬영비", "자격증 응시료")):
        fields.update(_check_group(sheet, CheckGroup(key, "신청분야", (option,), same_cell=True)))
    masks = []
    for marker, count in (("OO시/군", 4), ("한국교통안전공단", 1), ("한국산업인력공단", 1)):
        masks.extend({"page": sheet.number, "marker": marker, "box": _mask_text(sheet, marker, i)}
                     for i in range(count))
    return fields, masks


def _build_job_consent(doc: Any):
    sheet = read_sheet(doc[0], 0)
    fields = {}
    fields.update(_choice_line(sheet, "consent.privacy", 298.9))
    fields.update(_choice_line(sheet, "consent.thirdParty", 439.5))
    fields.update(_text_fields(sheet, (
        TextField("consent.job.month", "2026년", mode="after", y_hint=664.0, align="center", format="none", auto_date_part="month"),
        TextField("consent.job.day", "2026년 월", mode="after", y_hint=664.0, align="center", format="none", auto_date_part="day"),
        TextField("name", "신청인 :", mode="after", y_hint=705.4),
    )))
    fields["name"]["box"][2] = 445.0
    fields["consent.job.signature"] = _image_field(
        sheet, ImageField("consent.job.signature", "(인)", y_hint=705.4, grow=(1.5, 1.5, 1.5, 1.5))
    )
    return fields, []


def _build_job_interview(doc: Any):
    sheet = read_sheet(doc[0], 0)
    specs = (TextField("name", "성  명", y_hint=173.3), TextField("birth", "생년월일", y_hint=173.3),
             TextField("address", "주  소", y_hint=205.9), TextField("mobile", "연락처", y_hint=238.5),
             TextField("email", "이메일", y_hint=238.5))
    return {spec.key: _text_field(sheet, spec) for spec in specs}, []


BUILDERS = {"서식1": lambda doc: (_build_form1_fields(doc), []), "서식2": _build_self_check,
            "서식3": _build_form3, "서식4": _build_form4, "서식5": _build_form5,
            "job_application": _build_job_application, "job_consent": _build_job_consent,
            "job_interview_confirmation": _build_job_interview}

REQUIREMENTS = {
    "서식1": [
        {"kind": "all_or_none", "fields": ["ecName", "ecRelation", "ecContact"]},
        {"kind": "when_choice", "field": "priorJoined", "equals": "참여", "required": ["priorName", "priorPeriod", "priorAmount"]},
        {"kind": "when_choice", "field": "householdSize", "equals": "10인 이상", "required": ["householdSizeCount"]},
    ],
}


def _choice_group(key: str) -> str:
    parts = key.split(".")
    return ".".join(parts[:2]) if parts[0] in {"self_check", "consent", "subsidy"} else parts[0]


def _annotate_choice_geometry(fields: dict[str, dict[str, Any]], sheets: list[Sheet], form_no: str) -> None:
    """Store the clickable and required-outline bounds for every printed choice."""
    conditional_fields: dict[tuple[str, str], list[str]] = {}
    for rule in REQUIREMENTS.get(form_no, []):
        if rule.get("kind") == "when_choice":
            conditional_fields[(rule["field"], rule["equals"])] = rule["required"]

    for key, field in fields.items():
        if field.get("type") != "check":
            continue
        if field.get("control") == "radio_text":
            field["label_box"] = field["box"]
            field["choice_box"] = field.get("group_box", field["box"])
            field["click_box"] = field.get("group_box", field["box"])
            continue
        label_box = field.get("label_box")
        if not label_box:
            raise LookupError(f"{form_no}.{key}: 보기 글자 좌표를 찾지 못했습니다.")
        prefix = _choice_group(key)
        option = key[len(prefix) + 1:]
        related_keys = conditional_fields.get((prefix, option), [])
        boxes = [field["box"], label_box]
        click_boxes = list(boxes)
        boxes.extend(fields[name]["box"] for name in related_keys if name in fields)
        xs = [box[0] for box in boxes] + [box[2] for box in boxes]
        ys = [box[1] for box in boxes] + [box[3] for box in boxes]
        raw = [min(xs), min(ys), max(xs), max(ys)]
        sheet = sheets[field["page"]]
        cells = []
        for box in boxes:
            cells.append(sheet.cell_at((box[0] + box[2]) / 2, (box[1] + box[3]) / 2))
        allowed = [min(cell[0] for cell in cells), min(cell[1] for cell in cells),
                   max(cell[2] for cell in cells), max(cell[3] for cell in cells)]
        field["cell_box"] = [round(value, 2) for value in allowed]
        margin = 2.5
        click_cells = [sheet.cell_at((box[0] + box[2]) / 2, (box[1] + box[3]) / 2) for box in click_boxes]
        click_allowed = [min(cell[0] for cell in click_cells), min(cell[1] for cell in click_cells),
                         max(cell[2] for cell in click_cells), max(cell[3] for cell in click_cells)]
        field["click_box"] = [
            round(max(click_allowed[0], min(box[0] for box in click_boxes)), 2),
            round(max(click_allowed[1], min(box[1] for box in click_boxes)), 2),
            round(min(click_allowed[2], max(box[2] for box in click_boxes)), 2),
            round(min(click_allowed[3], max(box[3] for box in click_boxes)), 2),
        ]
        cell_inset = 0.2
        field["choice_box"] = [
            round(max(allowed[0] + cell_inset, raw[0] - margin), 2),
            round(max(allowed[1] + cell_inset, raw[1] - margin), 2),
            round(min(allowed[2] - cell_inset, raw[2] + margin), 2),
            round(min(allowed[3] - cell_inset, raw[3] + margin), 2),
        ]

    # Adjacent label hit areas meet at the midpoint between checkboxes. This keeps
    # each printed word clickable without letting a long label select its neighbor.
    checks = [(key, field) for key, field in fields.items()
              if field.get("type") == "check" and field.get("control") != "radio_text"]
    for _ in range(len(checks) + 1):
        changed = False
        for index, (_, first) in enumerate(checks):
            a = first["click_box"]
            for _, second in checks[index + 1:]:
                if first["page"] != second["page"]:
                    continue
                b = second["click_box"]
                if not (a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]):
                    continue
                acx = (first["box"][0] + first["box"][2]) / 2
                acy = (first["box"][1] + first["box"][3]) / 2
                bcx = (second["box"][0] + second["box"][2]) / 2
                bcy = (second["box"][1] + second["box"][3]) / 2
                if abs(acx - bcx) >= abs(acy - bcy):
                    midpoint = (acx + bcx) / 2
                    if acx <= bcx:
                        a[2], b[0] = min(a[2], midpoint), max(b[0], midpoint)
                    else:
                        a[0], b[2] = max(a[0], midpoint), min(b[2], midpoint)
                else:
                    midpoint = (acy + bcy) / 2
                    if acy <= bcy:
                        a[3], b[1] = min(a[3], midpoint), max(b[1], midpoint)
                    else:
                        a[1], b[3] = max(a[1], midpoint), min(b[3], midpoint)
                first["click_box"] = [round(value, 2) for value in a]
                second["click_box"] = [round(value, 2) for value in b]
                changed = True
        if not changed:
            break

    by_group: dict[tuple[int, str], list[dict[str, Any]]] = {}
    for key, field in fields.items():
        if field.get("type") == "check":
            by_group.setdefault((field["page"], _choice_group(key)), []).append(field)
    for siblings in by_group.values():
        boxes = [field.get("choice_box", field["box"]) for field in siblings]
        union = [round(min(box[0] for box in boxes), 2), round(min(box[1] for box in boxes), 2),
                 round(max(box[2] for box in boxes), 2), round(max(box[3] for box in boxes), 2)]
        for field in siblings:
            field["choice_group_box"] = union


def _build_form1_fields(doc: Any):
    p0, p1 = read_sheet(doc[0], 0), read_sheet(doc[1], 1)
    fields = {spec.key: _text_field(p0, spec) for spec in FORM1_TEXTS_P0}
    for group in FORM1_CHECKS_P0:
        fields.update(_check_group(p0, group))
    fields["householdSizeCount"] = _text_field(
        p0, TextField("householdSizeCount", "10인 이상(", mode="after", y_hint=538.0, align="center")
    )
    fields.update({spec.key: _text_field(p1, spec) for spec in FORM1_TEXTS_P1})
    for group in FORM1_CHECKS_P1:
        fields.update(_check_group(p1, group))
    return fields


def build_all(out_dir: Path = COORDS) -> list[Path]:
    import pymupdf
    from ..form_numbers import internal_form_no, order_form_numbers
    from .cut_templates import TEMPLATES_SPEC

    out_dir.mkdir(parents=True, exist_ok=True)
    specs = {spec.key: spec for spec in TEMPLATES_SPEC}
    written = []
    for key in order_form_numbers(BUILDERS):
        builder = BUILDERS[key]
        spec = specs[key]
        template = TEMPLATES / f"{key}.pdf"
        if not template.exists():
            raise FileNotFoundError(f"템플릿이 없습니다: {template}")
        with pymupdf.open(template) as doc:
            fields, masks = builder(doc)
            sheets = [read_sheet(page, page_no) for page_no, page in enumerate(doc)]
            _annotate_choice_geometry(fields, sheets, key)
            payload = {
                "form_no": key, "title": spec.title, "template": f"templates/{key}.pdf",
                "public_form": spec.public_form,
                "internal_form": internal_form_no(spec.public_form) if spec.public_form else None,
                "source": {"file": spec.source,
                           "pages": [{"page": page.source_page, "title": page.title_marker}
                                     for page in spec.pages]},
                "generated_by": "demo/fixtures/build_form_coords.py",
                "note": "좌표는 공식 원본 PDF 문자 위치와 벡터 표 선에서 추출했습니다.",
                "fields": fields, "masks": masks,
                "requirements": REQUIREMENTS.get(key, []),
            }
        target = out_dir / f"{key}.json"
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written.append(target)
        print(f"  {key}: {len(fields)} 위치, {len(masks)} 가림 영역")
    return written


def main() -> int:
    print("공식 원본에서 서식 좌표 맵 만들기 (문자 위치·표 선 기반)")
    build_all()
    return 0


if __name__ == "__main__":
    sys.exit(main())

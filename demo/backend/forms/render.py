"""원본 서식 PDF 위에 입력값을 얹는다 (R9).

설계 6-B.1의 **A안(원본 PDF 오버레이)**이다. 화면을 인쇄하는 B안과 달리 결과물이
원본과 구분되지 않는다 — 이 데모의 논점이 "행정 서식을 디지털로 옮겨도 서류로서
성립하는가"이므로, 결과물이 기존 서식과 같아야 그 논점이 선다.

얹는 것은 셋뿐이다.

  * 글자 — 칸 안에 들어가도록 폭을 재서 넣는다. 넘치면 글자를 줄이지, 칸 밖으로
    나가지 않는다. 원본 선·글자를 침범하는 순간 서식이 아니라 낙서가 된다.
  * `✓`  — `□` 글자의 원점에 같은 크기로 얹는다. 좌표를 따로 재지 않는다.
  * 이미지 — 서식5 서명란에 캔버스 전자서명 PNG (R9.2).
"""

from pathlib import Path
from typing import Any

from .coords import FormCoords
from .values import FilledForm

#: 기입값 색. 원본 인쇄는 검정이라, 사람이 채운 부분이 한눈에 갈리도록 짙은 남색을
#: 쓴다. 종이 서식에 파란 볼펜으로 쓴 것과 같은 관습이다.
INK = (0.05, 0.10, 0.45)

#: 칸을 넘칠 때 줄일 수 있는 최소 글자 크기.
MIN_SIZE = 5.0


def _font() -> Any:
    import fitz

    # 내장 CJK 폰트. 한글·✓ 모두 이 하나로 찍는다(별도 폰트 파일 의존이 없다).
    return fitz.Font("cjk")


def fit_size(font: Any, text: str, size: float, max_width: float) -> float:
    """칸 폭에 맞게 줄인 글자 크기."""
    while size > MIN_SIZE and font.text_length(text, size) > max_width:
        size -= 0.25
    return size


def render(coords: FormCoords, filled: FilledForm) -> bytes:
    """템플릿 + 입력값 → 완성된 서식 PDF 바이트."""
    import fitz

    if not coords.available:
        raise FileNotFoundError(
            f"{coords.form_no} 템플릿이나 좌표 맵이 없습니다. "
            "`python -m demo.fixtures.cut_templates` 와 "
            "`python -m demo.fixtures.build_form_coords` 를 먼저 돌리세요."
        )

    font = _font()
    doc = fitz.open(coords.template)
    writers: dict[int, Any] = {}

    def writer(page_no: int) -> Any:
        if page_no not in writers:
            writers[page_no] = fitz.TextWriter(doc[page_no].rect)
        return writers[page_no]

    # --- 글자 ---------------------------------------------------------
    for key, text in filled.texts.items():
        spec = coords.field(key)
        if spec is None or spec["type"] != "text" or not text:
            continue
        box = spec["box"]
        width = box[2] - box[0]
        size = fit_size(font, text, float(spec["size"]), width)
        x = float(spec["x"])
        if spec.get("align") == "center":
            x = box[0] + (width - font.text_length(text, size)) / 2
        writer(int(spec["page"])).append((x, float(spec["y"])), text, font=font, fontsize=size)

    # --- 체크 ---------------------------------------------------------
    for key in filled.checks:
        spec = coords.resolve_check(key)
        if spec is None or spec["type"] != "check":
            # 화면 보기 문구와 원본이 어긋난 경우다. 조용히 넘기면 체크가 사라진
            # 줄 모르니 남긴다 — 다만 선택 기능이라 예외로 세우지는 않는다.
            continue
        box = spec["box"]
        size = float(box[2] - box[0])  # ✓ 한 글자 폭 = 1em 이라 □ 폭과 같게 잡는다
        mark_width = font.text_length("✓", size)
        x = (box[0] + box[2]) / 2 - mark_width / 2
        writer(int(spec["page"])).append((x, float(spec["y"])), "✓", font=font, fontsize=size)

    for page_no, text_writer in writers.items():
        text_writer.write_text(doc[page_no], color=INK)

    # --- 이미지 (서식5 전자서명) ---------------------------------------
    for key, image_path in filled.images.items():
        spec = coords.field(key)
        if spec is None or spec["type"] != "image":
            continue
        source = Path(image_path)
        if not source.exists():
            continue
        rect = fitz.Rect(*spec["box"])
        doc[int(spec["page"])].insert_image(
            rect, filename=str(source), keep_proportion=True, overlay=True
        )

    # 내장 CJK 폰트를 통째로 싣면 서식 한 장이 1.8MB가 된다. 실제로 찍은 글자만
    # 남기면 200KB대로 떨어진다 — 심사 화면에서 탭을 옮길 때마다 받는 파일이다.
    doc.subset_fonts(verbose=False)
    out = doc.tobytes(garbage=3, deflate=True)
    doc.close()
    return bytes(out)

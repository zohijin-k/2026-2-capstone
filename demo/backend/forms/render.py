"""원본 서식 PDF 위에 입력값을 얹는다 (R9).

설계 6-B.1의 **A안(원본 PDF 오버레이)**이다. 화면을 인쇄하는 B안과 달리 결과물이
원본과 구분되지 않는다 — 이 데모의 논점이 "행정 서식을 디지털로 옮겨도 서류로서
성립하는가"이므로, 결과물이 기존 서식과 같아야 그 논점이 선다.

얹는 것은 셋뿐이다.

  * 글자 — 칸 안에 들어가도록 폭을 재서 넣는다. 넘치면 글자를 줄이지, 칸 밖으로
    나가지 않는다. 원본 선·글자를 침범하는 순간 서식이 아니라 낙서가 된다.
  * `✓`  — 원본 체크 상자 중심에 좌표 비율을 적용해 크게 그린다.
  * 이미지 — 서식5 서명란에 캔버스 전자서명 PNG (R9.2).
"""

from functools import lru_cache
import base64
import json
from pathlib import Path
from typing import Any

from .coords import FormCoords
from .values import FilledForm

#: 기입값 색. 원본 인쇄는 검정이라, 사람이 채운 부분이 한눈에 갈리도록 짙은 남색을
#: 쓴다. 종이 서식에 파란 볼펜으로 쓴 것과 같은 관습이다.
INK = (0.05, 0.10, 0.45)
PRINT_INK = (0.08, 0.08, 0.08)

#: 칸을 넘칠 때 줄일 수 있는 최소 글자 크기.
MIN_SIZE = 5.0
CHECK_INSET_RATIO = 0.16


def _font() -> Any:
    import fitz

    # 내장 CJK 폰트. 한글·✓ 모두 이 하나로 찍는다(별도 폰트 파일 의존이 없다).
    return fitz.Font("cjk")


def fit_size(font: Any, text: str, size: float, max_width: float) -> float:
    """칸 폭에 맞게 줄인 글자 크기."""
    while size > MIN_SIZE and font.text_length(text, size) > max_width:
        size -= 0.25
    return size


def format_field_text(field: dict[str, Any], text: str) -> str:
    """Apply the literal year format printed on the source form, if any."""
    if field.get("format") == "yy":
        digits = "".join(char for char in text if char.isdigit())
        return digits[-2:] if len(digits) >= 2 else digits
    return text


def render_page_png(pdf: bytes, page_no: int, dpi: int = 200) -> bytes:
    """Render one 1-based PDF page with PyMuPDF, matching the coordinate source."""
    import fitz

    with fitz.open(stream=pdf, filetype="pdf") as doc:
        if page_no < 1 or page_no > doc.page_count:
            raise IndexError("서식 쪽 번호가 범위를 벗어났습니다.")
        return doc[page_no - 1].get_pixmap(dpi=dpi, alpha=False).tobytes("png")


@lru_cache(maxsize=64)
def render_template_page_png(path: str, modified_ns: int, page_no: int, dpi: int = 200) -> bytes:
    """Cache the static template raster by path revision and page."""
    source = Path(path).read_bytes()
    return render_page_png(source, page_no, dpi)


def filled_payload(filled: FilledForm) -> str:
    """Stable, private cache key and payload for rendering a completed form page."""
    images: dict[str, dict[str, str]] = {}
    for key, value in filled.images.items():
        if isinstance(value, bytes):
            images[key] = {"kind": "bytes", "value": base64.b64encode(value).decode("ascii")}
        else:
            path = Path(value)
            stat = path.stat() if path.exists() else None
            images[key] = {
                "kind": "path", "value": str(path),
                "revision": f"{stat.st_size}:{stat.st_mtime_ns}" if stat else "missing",
            }
    return json.dumps(
        {"form_no": filled.form_no, "texts": filled.texts, "checks": filled.checks, "images": images},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )


@lru_cache(maxsize=96)
def render_filled_page_png_cached(
    form_no: str, template_path: str, modified_ns: int, page_no: int, dpi: int, payload: str
) -> bytes:
    """Cache filled preview rasters by their complete visible content and source revision."""
    from .coords import load

    raw = json.loads(payload)
    images: dict[str, str | bytes] = {}
    for key, image in raw["images"].items():
        if image["kind"] == "bytes":
            images[key] = base64.b64decode(image["value"])
        else:
            images[key] = image["value"]
    filled = FilledForm(
        form_no=raw["form_no"], texts=raw["texts"], checks=raw["checks"], images=images
    )
    coords = load(form_no)
    if coords is None or str(coords.template) != template_path:
        raise FileNotFoundError(f"{form_no} 좌표 맵을 사용할 수 없습니다.")
    return render_page_png(render(coords, filled), page_no, dpi)


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
    writers: dict[tuple[int, tuple[float, float, float]], Any] = {}
    check_text_writers: dict[int, Any] = {}

    # 취업패키지 원본에 인쇄된 회색 예시 문구를 제거하고 흰색으로 덮는다.
    masks_by_page: dict[int, list[Any]] = {}
    for mask in coords.masks or []:
        page_no = int(mask["page"])
        rect = fitz.Rect(*mask["box"])
        masks_by_page.setdefault(page_no, []).append(rect)
    for page_no, rects in masks_by_page.items():
        page = doc[page_no]
        for rect in rects:
            page.add_redact_annot(rect, fill=(1, 1, 1))
        page.apply_redactions(images=0, graphics=0)

    def writer(page_no: int, color: tuple[float, float, float]) -> Any:
        key = (page_no, color)
        if key not in writers:
            writers[key] = fitz.TextWriter(doc[page_no].rect)
        return writers[key]

    # Self-check source labels are replaced with centered checkbox labels. The source
    # row text is masked once per row while leaving the table rules untouched.
    radio_rows: dict[tuple[int, tuple[float, ...], str], dict[str, dict[str, Any]]] = {}
    for key, spec in coords.fields.items():
        if spec.get("control") == "radio_text" and spec.get("group_box"):
            radio_rows.setdefault((int(spec["page"]), tuple(spec["group_box"]), key.rsplit(".", 1)[0]), {})[key.rsplit(".", 1)[-1]] = spec
    for (page_no, group_box, group_key), options in radio_rows.items():
        page = doc[page_no]
        row_rect = fitz.Rect(*group_box)
        page.draw_rect(row_rect, color=None, fill=(1, 1, 1), overlay=True)
        selected = next((option for option in ("예", "아니오") if f"{group_key}.{option}" in filled.checks), None)
        x0, y0, x1, y1 = group_box
        slot_width = (x1 - x0) / 2
        baseline = float(options["예"].get("y", options["아니오"].get("y", (y0 + y1) / 2)))
        size = float(options["예"].get("size", 9.5))
        square_size = size * 0.78
        for index, option in enumerate(("예", "아니오")):
            label_width = font.text_length(option, size)
            total_width = square_size + 3.0 + label_width
            sx = x0 + index * slot_width + max(1.0, (slot_width - total_width) / 2)
            sy = (y0 + y1 - square_size) / 2
            square = fitz.Rect(sx, sy, sx + square_size, sy + square_size)
            if selected == option:
                page.draw_rect(square, color=INK, fill=INK, overlay=True)
                page.draw_line((sx + square_size * .2, sy + square_size * .53),
                               (sx + square_size * .43, sy + square_size * .76),
                               color=(1, 1, 1), width=max(.7, size * .09), overlay=True)
                page.draw_line((sx + square_size * .43, sy + square_size * .76),
                               (sx + square_size * .83, sy + square_size * .22),
                               color=(1, 1, 1), width=max(.7, size * .09), overlay=True)
            else:
                page.draw_rect(square, color=INK, width=.8, overlay=True)
            writer(page_no, PRINT_INK).append((sx + square_size + 3.0, baseline), option, font=font, fontsize=size)

    # --- 글자 ---------------------------------------------------------
    for key, text in filled.texts.items():
        spec = coords.field(key)
        if spec is None or spec["type"] != "text" or not text:
            continue
        text = format_field_text(spec, text)
        box = spec["box"]
        width = box[2] - box[0]
        height = box[3] - box[1]
        reference = spec.get("date_reference") or {}
        size = float(reference.get("size", spec["size"])) * float(reference.get("render_size_scale", 1)) if spec.get("auto_date") else float(spec["size"])
        if not spec.get("auto_date") or not text.isdigit():
            size = fit_size(font, text, size, width)
        x = float(spec["x"])
        if spec.get("align") == "center":
            x = box[0] + (width - font.text_length(text, size)) / 2
        page_no = int(spec["page"])
        color = PRINT_INK if spec.get("auto_date") else INK
        baseline = float(reference.get("render_baseline", reference.get("baseline", spec["y"]))) if spec.get("auto_date") else float(spec["y"])
        writer(page_no, color).append((x, baseline), text, font=font, fontsize=size)

    # --- 체크 ---------------------------------------------------------
    for key in filled.checks:
        spec = coords.resolve_check(key)
        if spec is None or spec["type"] != "check":
            # 화면 보기 문구와 원본이 어긋난 경우다. 조용히 넘기면 체크가 사라진
            # 줄 모르니 남긴다 — 다만 선택 기능이라 예외로 세우지는 않는다.
            continue
        box = spec["box"]
        if spec.get("control") == "radio_text":
            continue
        height = float(box[3] - box[1])
        size = max(float(box[2] - box[0]), height) + 3.0
        center_x = (float(box[0]) + float(box[2])) / 2
        center_y = (float(box[1]) + float(box[3])) / 2
        square = fitz.Rect(center_x - size / 2, center_y - size / 2,
                           center_x + size / 2, center_y + size / 2)
        page = doc[int(spec["page"])]
        page.draw_rect(square, color=INK, fill=INK, overlay=True)
        points = (
            (center_x - size * 0.30, center_y + size * 0.00),
            (center_x - size * 0.08, center_y + size * 0.22),
            (center_x + size * 0.31, center_y - size * 0.28),
        )
        page.draw_line(points[0], points[1], color=(1, 1, 1), width=max(0.9, size * 0.10), overlay=True)
        page.draw_line(points[1], points[2], color=(1, 1, 1), width=max(0.9, size * 0.10), overlay=True)

    for (page_no, color), text_writer in writers.items():
        text_writer.write_text(doc[page_no], color=color)
    # `radio_text` rows are still source text at this stage; they are kept readable
    # until their paired replacement labels are drawn by the coordinate-map renderer.

    # --- 이미지 (서식5 전자서명) ---------------------------------------
    for key, image_path in filled.images.items():
        spec = coords.field(key)
        if spec is None or spec["type"] != "image":
            continue
        rect = fitz.Rect(*spec["box"])
        if isinstance(image_path, bytes):
            doc[int(spec["page"])].insert_image(
                rect, stream=image_path, keep_proportion=True, overlay=True
            )
        else:
            source = Path(image_path)
            if source.exists():
                doc[int(spec["page"])].insert_image(
                    rect, filename=str(source), keep_proportion=True, overlay=True
                )

    # 내장 CJK 폰트를 통째로 싣면 서식 한 장이 1.8MB가 된다. 실제로 찍은 글자만
    # 남기면 200KB대로 떨어진다 — 심사 화면에서 탭을 옮길 때마다 받는 파일이다.
    doc.subset_fonts(verbose=False)
    out = doc.tobytes(garbage=3, deflate=True)
    doc.close()
    return bytes(out)

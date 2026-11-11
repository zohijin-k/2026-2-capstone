"""서식5 종이 스캔에서 인쇄 대비 잉크 흔적을 확인한다."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageChops, ImageOps

from ..forms import coords as form_coords


def _page_image(path: Path, width: int) -> Image.Image:
    if path.suffix.lower() == ".pdf":
        import fitz

        with fitz.open(path) as pdf:
            page = pdf[0]
            pix = page.get_pixmap(matrix=fitz.Matrix(width / page.rect.width, width / page.rect.width), alpha=False)
            return Image.open(BytesIO(pix.tobytes("png"))).convert("L")
    with Image.open(path) as image:
        return ImageOps.exif_transpose(image).convert("L").copy()


def _extra_ink_ratio(scan: Image.Image, template: Image.Image, box: list[float], page_width: float, page_height: float) -> float:
    x0, y0, x1, y1 = box
    sx, sy = scan.width / page_width, scan.height / page_height
    crop = (max(0, int(x0 * sx)), max(0, int(y0 * sy)), min(scan.width, int(x1 * sx)), min(scan.height, int(y1 * sy)))
    scan_part, template_part = scan.crop(crop), template.crop(crop)
    diff = ImageChops.difference(scan_part, template_part)
    # Ink added to a blank template is darker than the corresponding printed template pixel.
    dark = sum(1 for value in diff.getdata() if value > 45)
    return dark / max(1, diff.width * diff.height)


def inspect_admin_consent_scan(path_value: str) -> dict[str, str]:
    """Return safe checklist observations only; never stores an image or OCR value."""
    spec = form_coords.load("서식5")
    if spec is None or not spec.available:
        return {"동의여부": "확인필요", "서명잉크확인": "확인필요"}
    import fitz

    with fitz.open(spec.template) as template_pdf:
        page = template_pdf[0]
        page_width, page_height = page.rect.width, page.rect.height
        width = 1200
        pix = page.get_pixmap(matrix=fitz.Matrix(width / page_width, width / page_width), alpha=False)
        template_image = Image.open(BytesIO(pix.tobytes("png"))).convert("L")
    try:
        scan = _page_image(Path(path_value), width)
        scan = scan.resize(template_image.size)
    except Exception:
        return {"동의여부": "확인필요", "서명잉크확인": "확인필요"}

    selected = []
    for key, label in (("agree.동의함", "동의함"), ("agree.동의하지 않음", "동의하지 않음")):
        field = spec.fields.get(key)
        if field and _extra_ink_ratio(scan, template_image, field["box"], page_width, page_height) > 0.035:
            selected.append(label)
    signature = spec.fields.get("signature")
    signed = bool(signature and _extra_ink_ratio(scan, template_image, signature["box"], page_width, page_height) > 0.012)
    return {
        "동의여부": selected[0] if len(selected) == 1 else "확인필요",
        "서명잉크확인": "있음" if signed else "확인필요",
    }

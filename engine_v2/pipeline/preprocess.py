"""전처리: 업로드 파일 → 페이지별 OCR 입력 이미지.

실측(2026-11-10, 브라우저 인쇄 초본 PDF) 기준 설계
- 텍스트 레이어 없음. 페이지마다 전체를 덮는 본문 이미지 1장(250dpi)
  + 하단 가로 띠(바코드 추정) + 우상단 작은 마크가 **별도 이미지**로 들어 있다.
- 그래서 페이지를 통째로 렌더링하지 않고 **본문 이미지만 원본 해상도로 꺼낸다.**
  → 재샘플링 손실 없음, 바코드·마크가 OCR 입력에서 자동으로 빠짐.

경로 우선순위 (페이지별)
  1. text_layer : 텍스트가 충분하면 OCR 생략 (정부24 원본 PDF 등)
  2. embedded   : 페이지를 거의 덮는 이미지가 있으면 그것만 추출
  3. render     : 그 외(조각난 구성 등)는 페이지 전체를 렌더링
  업로드가 이미지 파일(jpg/png)이면 upload 경로.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import pymupdf
from .privacy import mask_rrn

TEXT_LAYER_MIN_CHARS = 50      # 이 이상이면 텍스트 레이어 신뢰
MAIN_IMAGE_MIN_COVERAGE = 0.90  # 페이지 면적의 90% 이상 덮으면 본문 이미지로 간주
RENDER_DPI = 300
MIN_OCR_DPI = 200               # 이보다 낮으면 low_resolution 경고


class PageSource(str, Enum):
    TEXT_LAYER = "text_layer"
    EMBEDDED = "embedded"
    RENDER = "render"
    UPLOAD = "upload"


class AuxRole(str, Enum):
    FOOTER_STRIP = "footer_strip"  # 하단 가로 띠 (바코드 추정)
    CORNER_MARK = "corner_mark"    # 모서리 작은 정사각형 (QR·보안마크 추정)
    OTHER = "other"


@dataclass
class AuxRegion:
    """본문 외 부가 이미지. OCR에서는 빼고, 위치만 기록 (추후 진위확인 등에 활용 가능)."""
    role: AuxRole
    bbox_pt: tuple[float, float, float, float]
    xref: int


@dataclass
class PageImage:
    page: int
    source: PageSource
    page_size_pt: tuple[float, float]
    png: bytes | None = None            # OCR 입력 (text_layer면 None)
    pixel_size: tuple[int, int] | None = None
    dpi: float | None = None
    text: str | None = None             # text_layer일 때 본문
    aux: list[AuxRegion] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def px_to_pt(self, x: float, y: float) -> tuple[float, float]:
        """OCR 좌표(픽셀) → PDF 좌표(pt). 근거 하이라이트 bbox 변환용."""
        if not self.pixel_size:
            return x, y
        sx = self.page_size_pt[0] / self.pixel_size[0]
        sy = self.page_size_pt[1] / self.pixel_size[1]
        return x * sx, y * sy


def _classify_aux(bbox, page_w, page_h) -> AuxRole:
    x0, y0, x1, y1 = bbox
    w, h = x1 - x0, y1 - y0
    if w > page_w * 0.6 and h < page_h * 0.15 and y0 > page_h * 0.7:
        return AuxRole.FOOTER_STRIP
    if w < page_w * 0.15 and h < page_h * 0.15 and abs(w - h) < max(w, h) * 0.3:
        return AuxRole.CORNER_MARK
    return AuxRole.OTHER


def _process_pdf_page(doc: pymupdf.Document, i: int) -> PageImage:
    page = doc[i]
    pw, ph = page.rect.width, page.rect.height
    result = PageImage(page=i, source=PageSource.RENDER, page_size_pt=(pw, ph))

    # 1) 텍스트 레이어
    text = mask_rrn(page.get_text("text")).strip()
    if len(text) >= TEXT_LAYER_MIN_CHARS:
        result.source = PageSource.TEXT_LAYER
        result.text = text
        return result

    # 2) 본문 이미지 찾기
    infos = page.get_image_info(xrefs=True)
    main = None
    for info in infos:
        x0, y0, x1, y1 = info["bbox"]
        coverage = (x1 - x0) * (y1 - y0) / (pw * ph)
        if coverage >= MAIN_IMAGE_MIN_COVERAGE and info.get("xref"):
            if main is None or info["width"] * info["height"] > main["width"] * main["height"]:
                main = info

    for info in infos:
        if main is not None and info is main:
            continue
        if info.get("xref"):
            result.aux.append(AuxRegion(
                role=_classify_aux(info["bbox"], pw, ph),
                bbox_pt=tuple(round(v, 1) for v in info["bbox"]),
                xref=info["xref"],
            ))

    if main is not None:
        pix = pymupdf.Pixmap(doc, main["xref"])
        if pix.alpha or pix.n - pix.alpha != 3:
            pix = pymupdf.Pixmap(pymupdf.csRGB, pix)  # RGB로 통일
        result.source = PageSource.EMBEDDED
        result.png = pix.tobytes("png")
        result.pixel_size = (pix.width, pix.height)
        result.dpi = pix.width / ((main["bbox"][2] - main["bbox"][0]) / 72)
    else:
        # 3) 렌더링 폴백
        pix = page.get_pixmap(dpi=RENDER_DPI)
        result.source = PageSource.RENDER
        result.png = pix.tobytes("png")
        result.pixel_size = (pix.width, pix.height)
        result.dpi = RENDER_DPI
        result.warnings.append("본문 이미지를 찾지 못해 페이지 전체 렌더링 (바코드 등 포함 가능)")

    if result.dpi and result.dpi < MIN_OCR_DPI:
        result.warnings.append(f"low_resolution: {result.dpi:.0f}dpi")
    return result


def preprocess(file_path: str | Path) -> list[PageImage]:
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        doc = pymupdf.open(path)
        if doc.needs_pass:
            raise ValueError("암호가 걸린 PDF")
        return [_process_pdf_page(doc, i) for i in range(doc.page_count)]

    if suffix in {".png", ".jpg", ".jpeg", ".heic", ".webp", ".bmp", ".tif", ".tiff"}:
        pix = pymupdf.Pixmap(str(path))
        if pix.alpha or pix.n - pix.alpha != 3:
            pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
        # 사진은 물리 크기를 모르므로 A4 가정으로 pt 좌표계를 둔다
        return [PageImage(
            page=0, source=PageSource.UPLOAD, page_size_pt=(595.0, 842.0),
            png=pix.tobytes("png"), pixel_size=(pix.width, pix.height),
            dpi=None, warnings=["사진 업로드: 기울기·원근 보정 필요할 수 있음"],
        )]

    raise ValueError(f"지원하지 않는 형식: {suffix}")


if __name__ == "__main__":
    import sys
    for p in preprocess(sys.argv[1]):
        print(p.page, p.source.value, p.pixel_size, f"{p.dpi:.0f}dpi" if p.dpi else "-",
              [(a.role.value, a.bbox_pt) for a in p.aux], p.warnings)

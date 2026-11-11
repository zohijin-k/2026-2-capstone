"""Deterministic, fictitious OCR evaluation pages; no real documents are opened.

Uses demo.fixtures.make_samples' CJK TextWriter rendering convention and form
vocabulary. The application/consent PDF templates are not these document types,
so their artwork is deliberately not represented as an official certificate.
"""
from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
import pymupdf
from PIL import Image, ImageFilter
from demo.fixtures.make_samples import BODY_HINTS

OUT_DIR = Path(__file__).resolve().parents[1] / "data" / "synth_eval" / "revised"
STAGES = ("clean", "scan300", "blur", "noise", "rotate", "jpeg", "phone_weak", "phone_strong")
TODAY = "2026-11-11"


def documents():
    """Ground truth is authored independently of OCR/extractor outputs."""
    titles = {key: lines[0] for key, lines in BODY_HINTS}
    name = "가상시험"
    # (x%, baseline y%, text). Columns mirror the existing extractors' contract.
    resident = [(12, 5, "문서확인번호 : 0000-0000-0000-00000"), (82, 5, "1/1"),
                (15, 9, titles["주민등록초본"] + " (초본)"),
                (58, 13, "2026년 11월 10일"), (58, 16, "전북특별자치도 전주시장"),
                (10, 20, "성명(한자)"), (25, 20, name),
                (53, 20, "주민등록번호"), (72, 20, "990101-1******"),
                (8, 30, "번호"), (25, 30, "주소"), (54, 30, "발생일 / 신고일"), (80, 30, "세대주및관계"),
                (8, 35, "1"), (15, 35, "전북특별자치도 전주시 가상동"),
                (54, 35, "2020-01-01"), (69, 35, "2020-01-01"), (84, 35, "본인"),
                (73, 38, "전입")]
    def header(title):
        return [(10, 8, title), (10, 14, "성명"), (25, 14, name),
                (10, 18, "생년월일"), (30, 18, "1999.01.01"),
                (10, 22, "발급일"), (30, 22, "2026.11.10")]
    payment = header(titles["건강보험료납부확인서"]) + [
        (10, 27, "가입구분"), (30, 27, "직장가입자"),
        (10, 34, "년월"), (45, 34, "고지금액"), (78, 34, "납부금액")]
    for i, (month, amount) in enumerate((("2025.10", "100,000"), ("2025.11", "110,000"), ("2025.12", "120,000"))):
        payment += [(10, 39+i*5, month), (45, 39+i*5, amount), (78, 39+i*5, amount)]
    payment += [(10, 55, "합계"), (45, 55, "330,000")]
    acquisition = header(titles["4대보험가입내역확인서"]) + [
        (10, 11, "건강보험 자격득실확인서"),
        (10, 27, "조회기간"), (30, 27, "2020.01.01 ~ 2026.11.10"),
        (8, 34, "가입자구분"), (30, 34, "자격취득일"), (52, 34, "자격상실일"), (75, 34, "사업장명칭"),
        (8, 40, "직장가입자"), (30, 40, "2020.01.01"), (75, 40, "가상시험사업장"),
        (10, 50, "국민연금"), (32, 50, "가입"), (10, 55, "고용보험"), (32, 55, "가입"),
        (10, 60, "산재보험"), (32, 60, "가입")]
    common = {"성명": name, "생년월일": "1999-01-01", "발급일": "2026-11-10"}
    result = [
        ("resident_abstract", resident, {"name": name, "birth_date": "1999-01-01", "issue_date": "2026-11-10", "address_history_count": 1}),
        ("nhis_payment", payment, dict(common, 가입구분="직장", 건강보험료="110000", 고지월="2025-10,2025-11,2025-12")),
        ("nhis_acquisition_loss", acquisition, dict(common, 가입구분="직장", 취득일="2020-01-01", 변동내역="최근 5년 포함")),
    ]
    for kind, cells, fields in result:
        cells.append((10, 75, "합성 평가 전용 가짜 서류 - 실제 인물 및 기관 발급 문서 아님"))
        yield kind, sorted(cells, key=lambda c: (c[1], c[0])), fields


def render(cells, font_path=None):
    with pymupdf.open() as doc:
        page = doc.new_page(width=595, height=842)
        writer = pymupdf.TextWriter(page.rect)
        font = pymupdf.Font(fontfile=str(font_path)) if font_path else pymupdf.Font("cjk")
        for x, y, text in cells:
            writer.append((x*5.95, y*8.42), text, font=font, fontsize=10)
        writer.write_text(page)
        pix = page.get_pixmap(dpi=300, alpha=False)
        return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def degrade(base, stage, rng):
    """Compatibility image-only API; geometry is available from degrade_with_geometry."""
    if stage in {"phone_weak", "phone_strong"}:
        return phone_capture(base, stage, rng)[0]
    if stage == "clean":
        return base.copy()
    if stage == "scan300":
        # True 300 dpi canvas with mild scanner tone and blur.
        a = np.asarray(base.filter(ImageFilter.GaussianBlur(.35))).astype(float)
        return Image.fromarray(np.uint8(np.clip(a*.96 + rng.normal(0, 1, a.shape), 0, 255)))
    if stage == "blur":
        return base.filter(ImageFilter.GaussianBlur(1.7))
    if stage == "noise":
        a = np.asarray(base).astype(float)
        return Image.fromarray(np.uint8(np.clip(a+rng.normal(0, 15, a.shape), 0, 255)))
    if stage == "rotate":
        angle = float(rng.choice([-1, 1])) * float(rng.uniform(.8, 2))
        return base.rotate(angle, Image.Resampling.BICUBIC, fillcolor="white")
    if stage == "jpeg":
        buf = io.BytesIO()
        base.save(buf, format="JPEG", quality=18)
        return Image.open(io.BytesIO(buf.getvalue())).convert("RGB")
    if stage == "phone":
        import cv2
        w, h = base.size
        src = np.float32([[0, 0], [w-1, 0], [w-1, h-1], [0, h-1]])
        dst = np.float32([[w*.045, h*.025], [w*.96, h*.06], [w*.99, h*.97], [w*.01, h*.94]])
        matrix = cv2.getPerspectiveTransform(src, dst)
        a = cv2.warpPerspective(np.asarray(base), matrix, (w, h), borderValue=(235,235,235)).astype(float)
        xx = np.linspace(.63, 1.03, w)[None, :, None]
        yy = np.linspace(1.0, .82, h)[:, None, None]
        return Image.fromarray(np.uint8(np.clip(a*xx*yy, 0, 255)))
    raise ValueError(stage)


SPLITS = {
    "train": {"fonts": ("nanumgothiccoding",), "template": "stacked_header_v1"},
    "test": {"fonts": ("nanumgothic", "nanummyeongjo"), "template": "inline_header_v1"},
}


def split_documents(split):
    """Template families are assigned before degradation, never by image/seed."""
    for kind, cells, fields in documents():
        if split == "train":
            # A structurally different header: values appear below their labels.
            # Tables keep their semantics but use a narrower, lower body.
            updated = []
            for x, y, text in cells:
                if kind == "resident_abstract" and y == 20:
                    x, y = ({10: 10, 25: 10, 53: 55, 72: 55}[x],
                            20 if x in (10, 53) else 24)
                elif kind != "resident_abstract" and y in (14, 18, 22):
                    col = {14: 10, 18: 38, 22: 68}[y]
                    x, y = col, 15 if x == 10 else 19
                elif y >= 27 and y < 75:
                    x, y = 5 + x*.9, y + 3
                updated.append((x, y, text))
            cells = sorted(updated, key=lambda c: (c[1], c[0]))
        yield kind, cells, fields


def phone_capture(base, stage, rng):
    """Four independent corner displacements + desk, shading, optical blur.

    Offsets are 3–5% (weak) or 6–8% (strong) of page width/height.
    Metadata describes image formation; never supplied to the OCR/preprocessor.
    """
    import cv2
    w, h = base.size
    strong = stage == "phone_strong"
    low, high = (.06, .08) if strong else (.03, .05)
    insets = rng.uniform(low, high, (4, 2))
    margin = .10 if strong else .07
    mw, mh = round(w*margin), round(h*margin)
    cw, ch = w + 2*mw, h + 2*mh
    src = np.float32([[0,0], [w-1,0], [w-1,h-1], [0,h-1]])
    # Alternating inward/outward corners produce real trapezoid/skew rather
    # than four almost equal insets merely shrinking the whole sheet.
    signs = np.float32([[1,1], [-1,-1], [1,-1], [-1,1]])
    signs *= rng.choice([-1,1])
    offsets = insets * signs
    dst = np.float32(src + [mw,mh] + offsets * [w,h])
    matrix = cv2.getPerspectiveTransform(src, dst)
    # Illumination gradient and broad oblique shadow happen on the document.
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    xx, yy = xx/w, yy/h
    gradient = 1 - (.24 if strong else .13)*xx - (.16 if strong else .08)*yy
    shadow = np.exp(-((xx - .75*yy - .10)/(.17 if strong else .22))**2)
    light = gradient * (1 - (.38 if strong else .20)*shadow)
    sheet = np.uint8(np.clip(np.asarray(base)*light[:,:,None], 0, 255))
    sheet = cv2.GaussianBlur(sheet, (0,0), 1.15 if strong else .65)
    # Wood-toned background stays clearly visible around every corner.
    by, bx = np.mgrid[0:ch, 0:cw].astype(np.float32)
    texture = 4*np.sin(bx/31) + 2*np.sin(by/83)
    desk = np.empty((ch,cw,3), dtype=np.uint8)
    for channel, level in enumerate((105, 87, 68)):
        desk[:,:,channel] = np.clip(level + texture, 0, 255)
    warped = cv2.warpPerspective(sheet, matrix, (cw,ch), flags=cv2.INTER_CUBIC)
    mask = cv2.warpPerspective(np.full((h,w),255,np.uint8), matrix, (cw,ch))
    alpha = mask.astype(np.float32)[:,:,None]/255
    capture = np.uint8(np.clip(warped*alpha + desk*(1-alpha), 0,255))
    metadata = {"corner_displacement_magnitudes": insets.tolist(), "corner_offsets": offsets.tolist(), "document_corners_px": dst.tolist(),
                "background_margin": margin, "blur_sigma_px": 1.15 if strong else .65,
                "shadow_opacity": .38 if strong else .20}
    return Image.fromarray(capture), matrix, metadata


def degrade_with_geometry(base, stage, rng):
    import cv2
    if stage in {"phone_weak", "phone_strong"}:
        return phone_capture(base, stage, rng)
    if stage == "rotate":
        angle = float(rng.choice([-1, 1])) * float(rng.uniform(.8, 2))
        w, h = base.size
        affine = cv2.getRotationMatrix2D((w/2,h/2), angle, 1)
        image = cv2.warpAffine(np.asarray(base), affine, (w,h),
                               flags=cv2.INTER_CUBIC, borderValue=(255,255,255))
        matrix = np.vstack((affine, [0,0,1]))
        return Image.fromarray(image), matrix, {"angle_degrees": angle}
    return degrade(base, stage, rng), np.eye(3), {}


def generate(out_dir=OUT_DIR, seed=20261111, *, split="test", fonts=None):
    from engine_v2.tools.fetch_synth_fonts import font_path
    if split not in SPLITS:
        raise ValueError("Unknown split")
    selected = tuple(fonts) if fonts else SPLITS[split]["fonts"]
    if not selected or not set(selected).issubset(SPLITS[split]["fonts"]):
        raise ValueError("Fonts must belong to selected split; train/test fonts cannot overlap")
    # Verify all font assets before creating outputs.
    paths = {name: font_path(name) for name in selected}
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for font_name in selected:
        font_index = ("nanumgothic", "nanummyeongjo", "nanumgothiccoding").index(font_name)
        for doc_index, (kind, cells, fields) in enumerate(split_documents(split)):
            base = render(cells, paths[font_name])
            ys = sorted({c[1] for c in cells})
            lines = [" ".join(c[2] for c in cells if c[1] == y) for y in ys]
            for stage_index, stage in enumerate(STAGES):
                sample_id = f"{split}_{font_name}_{doc_index+1:02}_{stage_index:02}"
                rng = np.random.default_rng(np.random.SeedSequence([seed, font_index, doc_index, stage_index]))
                img, matrix, degradation_params = degrade_with_geometry(base, stage, rng)
                img.save(out_dir / f"{sample_id}.png", dpi=(300, 300))
                record = {"id": sample_id, "image": f"{sample_id}.png", "document_type": kind,
                          "degradation": stage, "synthetic": True, "seed": seed,
                          "font": font_name, "split": split,
                          "template_id": kind+":"+SPLITS[split]["template"],
                          "page_size_pt": [595,842], "text_lines": lines, "fields": fields,
                          "original_size_px": list(base.size), "page_transform": matrix.tolist(),
                          "cells": cells, "line_baselines_px": [y*base.height/100 for y in ys],
                          "degradation_params": degradation_params}
                (out_dir / f"{sample_id}.json").write_text(json.dumps(record, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
                records.append(record)
    manifest = {"version": 2, "synthetic": True, "seed": seed, "today": TODAY,
                "split": split, "split_policy": SPLITS, "samples": records}
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    return manifest


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path, default=OUT_DIR)
    ap.add_argument("--seed", type=int, default=20261111)
    ap.add_argument("--split", choices=sorted(SPLITS), default="test")
    ap.add_argument("--fonts", nargs="+", help="Subset of fonts allocated to this split")
    args = ap.parse_args()
    manifest = generate(args.output, args.seed, split=args.split, fonts=args.fonts)
    print(f"Generated {len(manifest['samples'])} synthetic pages: {args.output}")

if __name__ == "__main__":
    main()

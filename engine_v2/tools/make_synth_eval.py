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

OUT_DIR = Path(__file__).resolve().parents[1] / "data" / "synth_eval"
STAGES = ("clean", "scan300", "blur", "noise", "rotate", "jpeg", "phone")
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


def render(cells):
    with pymupdf.open() as doc:
        page = doc.new_page(width=595, height=842)
        writer = pymupdf.TextWriter(page.rect)
        font = pymupdf.Font("cjk")  # same bundled font as demo.fixtures.make_samples
        for x, y, text in cells:
            writer.append((x*5.95, y*8.42), text, font=font, fontsize=10)
        writer.write_text(page)
        pix = page.get_pixmap(dpi=300, alpha=False)
        return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def degrade(base, stage, rng):
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


def generate(out_dir=OUT_DIR, seed=20261111):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for doc_index, (kind, cells, fields) in enumerate(documents()):
        base = render(cells)
        lines = []
        for y in sorted({c[1] for c in cells}):
            lines.append(" ".join(c[2] for c in cells if c[1] == y))
        for stage_index, stage in enumerate(STAGES):
            sample_id = f"sample_{doc_index+1:02}_{stage_index:02}"
            rng = np.random.default_rng(np.random.SeedSequence([seed, doc_index, stage_index]))
            img = degrade(base, stage, rng)
            img.save(out_dir / f"{sample_id}.png", dpi=(300, 300))
            record = {"id": sample_id, "image": f"{sample_id}.png", "document_type": kind,
                      "degradation": stage, "synthetic": True, "seed": seed,
                      "page_size_pt": [595,842], "text_lines": lines, "fields": fields}
            (out_dir / f"{sample_id}.json").write_text(json.dumps(record, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
            records.append(record)
    manifest = {"version": 1, "synthetic": True, "seed": seed, "today": TODAY, "samples": records}
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    return manifest


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path, default=OUT_DIR)
    ap.add_argument("--seed", type=int, default=20261111)
    args = ap.parse_args()
    manifest = generate(args.output, args.seed)
    print(f"Generated {len(manifest['samples'])} synthetic pages: {args.output}")

if __name__ == "__main__":
    main()

"""본인 서류 PDF 점검 스크립트 — 반드시 본인 PC에서 실행.

엔진 설계 첫 분기점을 확인한다:
  텍스트 레이어 있음 → OCR 없이 직접 추출 (정확·빠름)
  텍스트 레이어 없음 → 이미지 기반, OCR/VLM 필요

사용법
  python -m engine_v2.tools.inspect_pdf engine_v2/data/private/초본.pdf            # 요약만 (팀 공유 가능)
  python -m engine_v2.tools.inspect_pdf engine_v2/data/private/초본.pdf --show     # 개인정보를 가린 본문
  python -m engine_v2.tools.inspect_pdf engine_v2/data/private/초본.pdf --dump     # 단어별 좌표 JSON 저장 (data/private/, 커밋 금지)
  python -m engine_v2.tools.inspect_pdf engine_v2/data/private/초본.pdf --render   # 페이지 PNG 저장 (OCR 실험용, 커밋 금지)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from ..paths import PRIVATE_DIR
from .privacy import mask_text

try:
    import pymupdf as fitz
except ImportError:
    sys.exit("PyMuPDF가 필요합니다: pip install pymupdf")


# 서류 종류 판별·필드 위치 설계에 쓸 키워드 (값이 아니라 존재 여부만 본다)
KEYWORDS = [
    "주민등록표", "초본", "등본", "발급일", "발급번호", "문서확인번호",
    "전입", "주소", "변동", "세대주", "전라북도", "전북특별자치도",
    "자격득실", "건강보험", "영수증", "면접", "응시",
]

DATE_PATTERN = re.compile(r"(19|20)\d{2}\s*[.\-년/]\s*\d{1,2}\s*[.\-월/]\s*\d{1,2}")
RRN_PATTERN = re.compile(r"\d{6}\s*-\s*[1-4*]")  # 주민번호 앞자리+성별자리 (존재 여부만)


def mask_digits(text: str) -> str:
    return mask_text(text)


def describe_images(page: "fitz.Page") -> list[dict]:
    """페이지 위 이미지들의 배치. 내용은 안 보고 위치·크기만 본다.

    - coverage_pct: 이미지가 페이지 면적의 몇 %를 덮는지
      100% 가까운 게 여러 장 → 본문 위에 배경무늬/워터마크가 겹친 구조일 가능성
      작은 조각 여러 장 → 페이지가 타일로 잘렸거나 직인·바코드 같은 부분 이미지
    - eff_dpi: 이 이미지를 페이지 크기로 펼쳤을 때 해상도. OCR은 보통 200~300dpi 이상 권장
    """
    page_area = page.rect.width * page.rect.height
    out = []
    for info in page.get_image_info():
        x0, y0, x1, y1 = info["bbox"]
        w_pt, h_pt = max(x1 - x0, 1e-6), max(y1 - y0, 1e-6)
        out.append({
            "bbox_pt": [round(x0), round(y0), round(x1), round(y1)],
            "pixels": [info["width"], info["height"]],
            "coverage_pct": round(100 * w_pt * h_pt / page_area, 1),
            "eff_dpi": round(info["width"] / (w_pt / 72)),
            "colorspace_n": info.get("colorspace"),
        })
    return out


def render_pages(doc: "fitz.Document", src: Path, dpi: int = 300) -> list[Path]:
    """페이지를 PNG로 렌더링. OCR 실험·전처리 확인용 (data/private/, 커밋 금지)."""
    out_dir = PRIVATE_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, page in enumerate(doc):
        p = out_dir / f"{src.stem}_p{i}.png"
        page.get_pixmap(dpi=dpi).save(p)
        paths.append(p)
    return paths


def summarize(doc: "fitz.Document") -> dict:
    pages = []
    for i, page in enumerate(doc):
        text = page.get_text("text")
        words = page.get_text("words")
        pages.append({
            "page": i,
            "size_pt": [round(page.rect.width), round(page.rect.height)],
            "text_chars": len(text.strip()),
            "words": len(words),
            "images": len(page.get_images(full=True)),
            "image_layout": describe_images(page),
            "date_like_count": len(DATE_PATTERN.findall(text)),
            "rrn_like_present": bool(RRN_PATTERN.search(text)),
            "keywords_found": [k for k in KEYWORDS if k in text],
        })

    total_chars = sum(p["text_chars"] for p in pages)
    image_pages = sum(1 for p in pages if p["images"] > 0 and p["text_chars"] < 50)

    if total_chars == 0:
        verdict = "텍스트 레이어 없음 → 이미지 기반. OCR/VLM 경로 필요"
    elif image_pages:
        verdict = f"혼합: {image_pages}개 페이지는 이미지 위주 → 페이지별로 경로 분기 필요"
    else:
        verdict = "텍스트 레이어 있음 → OCR 없이 직접 추출 가능 (권장 경로)"

    return {
        "encrypted": doc.is_encrypted,
        "needs_password": doc.needs_pass,
        "page_count": doc.page_count,
        "producer": mask_text((doc.metadata or {}).get("producer", "")),
        "creator": mask_text((doc.metadata or {}).get("creator", "")),
        "verdict": verdict,
        "pages": pages,
    }


def show_masked(doc: "fitz.Document") -> None:
    print("\n=== 본문 (개인정보 가림) ===")
    for i, page in enumerate(doc):
        print(f"\n--- page {i} ---")
        for line in page.get_text("text").splitlines():
            if line.strip():
                print(mask_digits(line))


def dump_words(doc: "fitz.Document", src: Path) -> Path:
    out_dir = PRIVATE_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{src.stem}.words.json"
    data = []
    for i, page in enumerate(doc):
        for x0, y0, x1, y1, word, block, line, wno in page.get_text("words"):
            data.append({
                "page": i, "bbox": [round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1)],
                "text": mask_text(word), "block": block, "line": line,
            })
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="서류 PDF 구조 점검 (로컬 전용)")
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--show", action="store_true", help="개인정보를 가린 본문 출력")
    ap.add_argument("--dump", action="store_true", help="단어별 좌표를 engine_v2/data/private/에 저장")
    ap.add_argument("--render", action="store_true", help="페이지를 300dpi PNG로 engine_v2/data/private/에 저장")
    args = ap.parse_args()

    if not args.pdf.exists():
        sys.exit(f"파일 없음: {args.pdf}")

    doc = fitz.open(args.pdf)
    if doc.needs_pass:
        print("암호가 걸린 PDF입니다. 정부24 발급 PDF라면 암호 해제 저장본이 필요할 수 있습니다.")
        return

    summary = summarize(doc)
    print("=== 요약 (팀 공유 가능) ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if args.show:
        show_masked(doc)
    if args.dump:
        out = dump_words(doc, args.pdf)
        print(f"\n단어 좌표 저장: {out}  (커밋 금지)")
    if args.render:
        for p in render_pages(doc, args.pdf):
            print(f"렌더링: {p}  (커밋 금지)")


if __name__ == "__main__":
    main()

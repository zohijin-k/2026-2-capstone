"""좌표 맵을 템플릿 쪽 위에 그린 확인용 PNG로 내보낸다.

기본 저장 위치는 시스템 임시 폴더다. 원본 템플릿과 입력값은 수정하지 않는다.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw, ImageFont

FIXTURES = Path(__file__).resolve().parent
REPOSITORY = FIXTURES.parents[1]
COORDS = FIXTURES / "form_coords"
TEMPLATES = FIXTURES / "templates"


def preview(output: Path) -> list[Path]:
    output = output.expanduser().resolve()
    if output.is_relative_to(REPOSITORY):
        raise ValueError("확인용 PNG는 저장소 바깥 경로에 저장해 주세요.")
    output.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    font = ImageFont.load_default()

    for coords_path in sorted(COORDS.glob("*.json")):
        data = json.loads(coords_path.read_text(encoding="utf-8"))
        template_path = TEMPLATES / f"{coords_path.stem}.pdf"
        with pymupdf.open(template_path) as document:
            for page_no, page in enumerate(document):
                scale = 1.7
                pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
                image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
                draw = ImageDraw.Draw(image)
                index = 0
                for field_key, field in data["fields"].items():
                    if field["page"] != page_no:
                        continue
                    index += 1
                    x0, y0, x1, y1 = field["box"]
                    rect = tuple(round(value * scale) for value in (x0, y0, x1, y1))
                    color = {"text": "#d42020", "check": "#16753c", "image": "#1769aa"}.get(field["type"], "#111111")
                    draw.rectangle(rect, outline=color, width=2)
                    draw.text((rect[0], max(0, rect[1] - 10)), str(index), fill=color, font=font)
                target = output / f"{coords_path.stem}-p{page_no + 1}.png"
                image.save(target)
                written.append(target)
                print(f"{target}: " + ", ".join(
                    f"{index + 1}={key}" for index, (key, field) in enumerate(
                        (item for item in data["fields"].items() if item[1]["page"] == page_no)
                    )
                ))
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path(tempfile.gettempdir()) / "demo-form-coordinate-previews",
        help="저장소 외부의 출력 폴더 (기본: 시스템 임시 폴더)",
    )
    args = parser.parse_args()
    preview(args.out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

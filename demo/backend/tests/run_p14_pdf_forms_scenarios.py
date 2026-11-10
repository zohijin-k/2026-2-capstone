"""원본 신청 서식 템플릿·좌표 맵과 렌더링을 가상 값으로 검증한다."""
from __future__ import annotations

import json

import pymupdf

from ..forms.coords import COORDS_DIR, FIXTURES, load
from ..forms.render import render
from ..forms.values import FilledForm
from ...fixtures.cut_templates import TEMPLATES_SPEC


def run() -> None:
    failures: list[str] = []
    form_keys = [spec.key for spec in TEMPLATES_SPEC]
    for key in form_keys:
        template_path = FIXTURES / "templates" / f"{key}.pdf"
        coords_path = COORDS_DIR / f"{key}.json"
        if not template_path.exists() or not coords_path.exists():
            failures.append(f"{key}: 템플릿 또는 좌표 맵 없음")
            continue
        spec = json.loads(coords_path.read_text(encoding="utf-8"))
        coords = load(key)
        if coords is None or not coords.available:
            failures.append(f"{key}: 좌표 맵을 읽을 수 없음")
            continue
        with pymupdf.open(template_path) as template:
            if template.page_count != len(spec["source"]["pages"]):
                failures.append(f"{key}: 원본 페이지 수 불일치")
            for index, page in enumerate(template):
                marker = spec["source"]["pages"][index]["title"]
                if "".join(marker.split()) not in "".join(page.get_text().split()):
                    failures.append(f"{key}: 페이지 제목 불일치")
                if abs(page.rect.width - 595.276) > 1 or abs(page.rect.height - 841.89) > 1:
                    failures.append(f"{key}: A4 페이지가 아님")
            for name, field in spec["fields"].items():
                rect = pymupdf.Rect(*field["box"])
                if field["page"] < 0 or field["page"] >= template.page_count or not template[field["page"]].rect.contains(rect):
                    failures.append(f"{key}.{name}: 쪽 밖 좌표")
                if rect.is_empty:
                    failures.append(f"{key}.{name}: 빈 좌표")
            positioned_fields = list(spec["fields"].items())
            for index, (name, field) in enumerate(positioned_fields):
                a = pymupdf.Rect(*field["box"])
                for other_name, other in positioned_fields[index + 1 :]:
                    if field["page"] == other["page"] and a.intersects(pymupdf.Rect(*other["box"])):
                        failures.append(f"{key}.{name}/{other_name}: 입력 상자 겹침")

        fake = FilledForm(form_no=key)
        for name, field in spec["fields"].items():
            if field["type"] == "text":
                fake.texts[name] = "가상값"
        pdf = render(coords, fake)
        with pymupdf.open(stream=pdf, filetype="pdf") as result:
            for name, field in spec["fields"].items():
                if field["type"] != "text":
                    continue
                rect = pymupdf.Rect(*field["box"])
                words = result[field["page"]].get_text("words")
                if not any(word[4] == "가상값" and rect.intersects(pymupdf.Rect(word[:4])) for word in words):
                    failures.append(f"{key}.{name}: 값이 좌표에서 확인되지 않음")
            if key == "job_application":
                text = "\n".join(page.get_text() for page in result)
                for example in ("OO시/군", "한국교통안전공단", "한국산업인력공단"):
                    if example in text:
                        failures.append(f"{key}: 예시 문구가 결과 텍스트에 남음")

    if failures:
        raise AssertionError("\n".join(failures))
    print(f"[OK] {len(form_keys)}개 원본 서식, 좌표·렌더링·예시 제거 검증")


def main() -> int:
    run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

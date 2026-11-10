"""원본 신청 서식 템플릿·좌표 맵과 렌더링을 가상 값으로 검증한다."""
from __future__ import annotations

import json

import pymupdf

from ..forms.coords import COORDS_DIR, FIXTURES, load
from ..forms.render import render
from ..forms.values import FilledForm
from ...fixtures.build_form_coords import read_sheet
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
                sheet = read_sheet(page, index)
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
                page_rect = template[field["page"]].rect
                if rect.x0 < page_rect.x0 + 20 or rect.y0 < page_rect.y0 + 20 or rect.x1 > page_rect.x1 - 20 or rect.y1 > page_rect.y1 - 20:
                    failures.append(f"{key}.{name}: 쪽 가장자리 20pt 안쪽에 좌표가 있음")
                if field["type"] == "text":
                    if rect.height > 40:
                        failures.append(f"{key}.{name}: 글자 칸 높이가 40pt 초과")
                    sheet = read_sheet(template[field["page"]], field["page"])
                    cell = sheet.cell_at((rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2)
                    if rect.x0 < cell[0] - 0.7 or rect.x1 > cell[2] + 0.7:
                        failures.append(f"{key}.{name}: 글자 칸 너비가 표 셀 밖")
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

        required_signatures = {"서식5", "job_application", "job_consent"}
        if key in required_signatures and not any(field["type"] == "image" for field in spec["fields"].values()):
            failures.append(f"{key}: 서명이 필요한 서식에 서명 좌표가 없음")
        if key == "서식1" and "householdSizeCount" not in spec["fields"]:
            failures.append("서식1: 10인 이상 가구원 수 입력 좌표가 없음")
        if key == "서식5":
            name_box = pymupdf.Rect(*spec["fields"]["name"]["box"])
            sign_box = pymupdf.Rect(*spec["fields"]["signature"]["box"])
            if name_box.x1 >= sign_box.x0:
                failures.append("서식5: 성명 입력칸이 서명칸과 겹침")
        if key in {"job_application", "job_consent"}:
            with pymupdf.open(template_path) as source:
                words = source[0].get_text("words")
                if key == "job_application":
                    fields = spec["fields"]
                    bank_box = pymupdf.Rect(*fields["bankName"]["box"])
                    account_box = pymupdf.Rect(*fields["accountNo"]["box"])
                    account_marker = next((pymupdf.Rect(word[:4]) for word in words if word[4] == "계좌번호("), None)
                    bank_marker = next((pymupdf.Rect(word[:4]) for word in words if word[4] == "은행)"), None)
                    if account_marker is None or bank_marker is None or not (
                        bank_box.x0 >= account_marker.x1 and bank_box.x1 <= bank_marker.x0
                        and account_box.x0 >= bank_marker.x1
                    ):
                        failures.append("job_application: 은행명·계좌번호가 인쇄된 괄호 문구와 겹침")
                else:
                    fields = spec["fields"]
                    month_box = pymupdf.Rect(*fields["consent.job.month"]["box"])
                    day_box = pymupdf.Rect(*fields["consent.job.day"]["box"])
                    month_marker = next((pymupdf.Rect(word[:4]) for word in words if word[4] == "월" and 650 <= word[1] <= 670), None)
                    day_marker = next((pymupdf.Rect(word[:4]) for word in words if word[4] == "일" and 650 <= word[1] <= 670), None)
                    year_marker = next((pymupdf.Rect(word[:4]) for word in words if word[4] == "2026년" and 650 <= word[1] <= 670), None)
                    if year_marker is None or month_marker is None or day_marker is None or not (
                        month_box.x0 >= year_marker.x1 and month_box.x1 <= month_marker.x0
                        and day_box.x0 >= month_marker.x1 and day_box.x1 <= day_marker.x0
                    ):
                        failures.append("job_consent: 월·일 입력 좌표가 인쇄된 날짜 표기 사이에 있지 않음")

    if failures:
        raise AssertionError("\n".join(failures))
    print(f"[OK] {len(form_keys)}개 원본 서식, 좌표·렌더링·예시 제거 검증")


def main() -> int:
    run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

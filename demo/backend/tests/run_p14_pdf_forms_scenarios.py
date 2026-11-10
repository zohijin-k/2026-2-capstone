"""원본 신청 서식 템플릿·좌표 맵과 렌더링을 가상 값으로 검증한다."""
from __future__ import annotations

import json
from pathlib import Path

import pymupdf

from ..forms.coords import COORDS_DIR, FIXTURES, load
from ..forms.render import format_field_text, render, render_page_png
from ..forms.values import FilledForm
from ...fixtures.build_form_coords import read_sheet
from ...fixtures.cut_templates import TEMPLATES_SPEC


def _form_font_corpus() -> set[str]:
    """All Hangul/ASCII, static form text, field labels, and fake entered values."""
    chars = {chr(code) for code in range(0x20, 0x7F)}
    for lead in range(0xB0, 0xC9):
        for trail in range(0xA1, 0xFF):
            try:
                value = bytes((lead, trail)).decode("euc_kr")
            except UnicodeDecodeError:
                continue
            if len(value) == 1 and 0xAC00 <= ord(value) <= 0xD7A3:
                chars.add(value)
    for spec in COORDS_DIR.glob("*.json"):
        chars.update(spec.read_text(encoding="utf-8"))
    from .run_p7_scenarios import P7_FORM1, P7_FORM5

    def collect(value):
        if isinstance(value, str):
            chars.update(value)
        elif isinstance(value, dict):
            for child in value.values():
                collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    collect(P7_FORM1)
    collect(P7_FORM5)
    return {char for char in chars if ord(char) >= 0x20}


def _check_bundled_form_fonts() -> list[str]:
    from ..forms.render import _font

    repo_demo = Path(__file__).resolve().parents[2]
    fonts_dir = repo_demo / "frontend" / "src" / "assets" / "fonts"
    failures = []
    corpus = _form_font_corpus()
    for family, directory in (("sans", "NotoSansKR"), ("serif", "NotoSerifKR")):
        folder = fonts_dir / directory
        ttf = folder / f"{directory}-subset.ttf"
        woff2 = folder / f"{directory}-subset.woff2"
        license_file = folder / "OFL.txt"
        if not ttf.is_file() or not woff2.is_file() or not license_file.is_file():
            failures.append(f"{directory}: TTF/WOFF2/OFL 파일 누락")
            continue
        font = _font(family)
        missing = sorted(ord(char) for char in corpus if not font.has_glyph(ord(char)))
        if missing:
            failures.append(f"{directory}: 글리프 누락 " + " ".join(f"U+{code:04X}" for code in missing))
    return failures


def _chars(page):
    return [
        (char["c"], pymupdf.Rect(char["bbox"]))
        for block in page.get_text("rawdict")["blocks"]
        for line in block.get("lines", [])
        for span in line["spans"]
        for char in span["chars"]
    ]


def _text_glyph_boxes(page):
    grouped = []
    for block in page.get_text("rawdict")["blocks"]:
        for line in block.get("lines", []):
            chars = [char for span in line["spans"] for char in span["chars"]]
            text = "".join(char["c"] for char in chars)
            if text:
                grouped.append((text, pymupdf.Rect(
                    min(char["bbox"][0] for char in chars), min(char["bbox"][1] for char in chars),
                    max(char["bbox"][2] for char in chars), max(char["bbox"][3] for char in chars),
                ), chars))
    return grouped


def _has_source_square(page, rect: pymupdf.Rect) -> bool:
    if any(char in {"□", "☐"} and rect.intersects(box) for char, box in _chars(page)):
        return True
    return any(
        item[0] == "re"
        and 3 <= item[1].width <= 16
        and 3 <= item[1].height <= 16
        and rect.intersects(item[1])
        for drawing in page.get_drawings()
        for item in drawing["items"]
    )


def run() -> None:
    failures: list[str] = []
    failures.extend(_check_bundled_form_fonts())
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
                    if field.get("format") in {"yyyy", "yy", "none"} and rect.width > 60:
                        failures.append(f"{key}.{name}: 날짜 칸 너비가 60pt 초과")
                    sheet = read_sheet(template[field["page"]], field["page"])
                    cell = sheet.cell_at((rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2)
                    if rect.x0 < cell[0] - 0.7 or rect.x1 > cell[2] + 0.7:
                        failures.append(f"{key}.{name}: 글자 칸 너비가 표 셀 밖")
                    masks = [
                        pymupdf.Rect(*mask["box"])
                        for mask in (spec.get("masks") or [])
                        if mask["page"] == field["page"]
                    ]
                    overlaps = [
                        char for char, char_box in _chars(template[field["page"]])
                        if char.strip() and rect.intersects(char_box)
                        and not any(mask.contains(char_box) for mask in masks)
                    ]
                    if overlaps:
                        failures.append(f"{key}.{name}: 글자 칸에 가림 처리되지 않은 원본 글자가 겹침 ({''.join(overlaps[:8])})")
                if field["type"] == "check":
                    if field.get("control") == "radio_text":
                        glyph_lines = _text_glyph_boxes(template[field["page"]])
                        def glyph_box(label: str, y: float):
                            for text, line_box, chars in glyph_lines:
                                offset = text.find(label)
                                if offset < 0 or abs(line_box.y0 - y) > 2:
                                    continue
                                selected = [pymupdf.Rect(char["bbox"]) for char in chars[offset:offset + len(label)]]
                                return pymupdf.Rect(
                                    min(box.x0 for box in selected), min(box.y0 for box in selected),
                                    max(box.x1 for box in selected), max(box.y1 for box in selected),
                                )
                            return None
                        target_box = glyph_box(field.get("label", ""), rect.y0)
                        if target_box is None or not (
                            rect.x0 <= target_box.x0 + 0.02 and rect.y0 <= target_box.y0 + 0.02
                            and rect.x1 >= target_box.x1 - 0.02 and rect.y1 >= target_box.y1 - 0.02
                        ):
                            failures.append(f"{key}.{name}: 라디오 영역이 원본 글자 bbox를 감싸지 않음")
                        opposite = "아니오" if field.get("label") == "예" else "예"
                        opposite_box = glyph_box(opposite, rect.y0)
                        if opposite_box is not None and rect.intersects(opposite_box):
                            failures.append(f"{key}.{name}: 라디오 영역이 옆 글자와 겹침")
                    elif not _has_source_square(template[field["page"]], rect):
                        failures.append(f"{key}.{name}: 좌표 안에서 원본 체크 상자(□)를 찾지 못함")
            if key == "서식2":
                for row in range(1, 9):
                    yes = spec["fields"].get(f"self_check.{row}.예")
                    no = spec["fields"].get(f"self_check.{row}.아니오")
                    if not yes or not no:
                        failures.append(f"서식2: {row}번 행에 예/아니오 라디오 쌍이 없음")
                    elif pymupdf.Rect(*yes["box"]).intersects(pymupdf.Rect(*no["box"])):
                        failures.append(f"서식2: {row}번 행의 예/아니오 글자 영역이 겹침")
            positioned_fields = list(spec["fields"].items())
            for index, (name, field) in enumerate(positioned_fields):
                a = pymupdf.Rect(*field["box"])
                for other_name, other in positioned_fields[index + 1 :]:
                    if field["page"] == other["page"] and a.intersects(pymupdf.Rect(*other["box"])):
                        failures.append(f"{key}.{name}/{other_name}: 입력 상자 겹침")

        fake = FilledForm(form_no=key)
        for name, field in spec["fields"].items():
            if field["type"] == "text":
                fake.texts[name] = "2026" if field.get("format") == "yy" else "가상값"
        pdf = render(coords, fake)
        with pymupdf.open(stream=pdf, filetype="pdf") as result:
            for name, field in spec["fields"].items():
                if field["type"] != "text":
                    continue
                rect = pymupdf.Rect(*field["box"])
                words = result[field["page"]].get_text("words")
                expected_text = format_field_text(field, fake.texts[name])
                if not any(word[4] == expected_text and rect.intersects(pymupdf.Rect(word[:4])) for word in words):
                    failures.append(f"{key}.{name}: 값이 좌표에서 확인되지 않음")
                if field.get("format") == "yy" and expected_text != "26":
                    failures.append(f"{key}.{name}: 두 자리 연도 출력 형식이 아님")
            if key == "job_application":
                if "job.applicationYear" in spec["fields"]:
                    failures.append("job_application: 인쇄된 연도를 다시 입력하는 필드가 있음")
                if "job.applicationMonth" not in spec["fields"] or "job.applicationDay" not in spec["fields"]:
                    failures.append("job_application: 월·일 입력 좌표가 없음")
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
    sample = FIXTURES / "templates" / "서식2.pdf"
    png = render_page_png(sample.read_bytes(), 1, dpi=200)
    pixmap = pymupdf.Pixmap(png)
    if not (1650 <= pixmap.width <= 1660 and 2335 <= pixmap.height <= 2345):
        raise AssertionError(f"200dpi 페이지 PNG 크기가 예상과 다름: {pixmap.width}x{pixmap.height}")
    print(f"[OK] {len(form_keys)}개 원본 서식, 좌표·렌더링·예시 제거 검증")


def main() -> int:
    run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

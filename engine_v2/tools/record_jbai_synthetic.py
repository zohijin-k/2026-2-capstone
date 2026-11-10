"""합성 서류를 전북AI OCR/Table Recognition에 보내 재생 fixture를 기록한다.

  python -m engine_v2.tools.record_jbai_synthetic

이 도구는 가상 인물·가상 값만 만든다. Authorization·API 키·요청 헤더는
저장하지 않으며, 응답은 message.content만 fixture에 보존한다.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pymupdf
from dotenv import dotenv_values

from ..pipeline.jbai_ocr import run_jbai_image_pair

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "engine_v2" / "tests" / "fixtures" / "jbai_synthetic"
FONT = Path("/System/Library/Fonts/AppleSDGothicNeo.ttc")
NAME = "김가상"
BIRTH = "1999-01-01"
ISSUE = "2026-11-10"


def _load_local_key() -> None:
    values = dotenv_values(ROOT / ".env")
    for key in ("JBAI_BASE_URL", "JBAI_API_KEY"):
        value = values.get(key)
        if value and not os.environ.get(key):
            os.environ[key] = value
    if not os.environ.get("JBAI_API_KEY"):
        raise SystemExit("JBAI_API_KEY 환경 설정이 필요합니다.")


def _page(document, title: str, page_no: int, page_total: int):
    page = document.new_page(width=595, height=842)
    page.insert_font(fontname="ko", fontfile=str(FONT))
    page.insert_text((35, 38), f"문서확인번호 : 1234-5678-9012-34567     {page_no}/{page_total}",
                     fontname="ko", fontsize=8)
    page.insert_text((35, 75), title, fontname="ko", fontsize=17)
    return page


def _text(page, y: float, value: str, size: float = 9, x: float = 38) -> None:
    page.insert_text((x, y), value, fontname="ko", fontsize=size)


def _grid(page, xs: list[float], ys: list[float], *, skip_vertical: set[tuple[int, int]] = set(),
          skip_horizontal: set[tuple[int, int]] = set()) -> None:
    for yi, y in enumerate(ys):
        for xi in range(len(xs) - 1):
            if yi in {0, len(ys) - 1} or (yi, xi) not in skip_horizontal:
                page.draw_line((xs[xi], y), (xs[xi + 1], y), color=(0, 0, 0), width=0.6)
    for xi, x in enumerate(xs):
        for yi in range(len(ys) - 1):
            if xi in {0, len(xs) - 1} or (yi, xi) not in skip_vertical:
                page.draw_line((x, ys[yi]), (x, ys[yi + 1]), color=(0, 0, 0), width=0.6)


def _cell(page, x0: float, x1: float, y0: float, y1: float, value: str, size: float = 7) -> None:
    if value:
        page.insert_text((x0 + 3, (y0 + y1) / 2 + size * 0.34), value,
                         fontname="ko", fontsize=size)


def _resident_pdf() -> tuple[bytes, dict]:
    d = pymupdf.open()
    for pno, address, occur, report in (
        (1, "전라북도 전주시 덕진구 예시로 2", "2020.04.10", "2020.04.11"),
        (2, "전북특별자치도 전주시 완산구 가상로 1", "2023.08.30", "2023.08.30"),
    ):
        p = _page(d, "주민등록표 ( 초 본 )", pno, 2)
        _text(p, 104, "발급일 2026년 11월 10일")
        _text(p, 142, f"성명 {NAME}")
        _text(p, 162, f"생년월일 {BIRTH}")
        if pno == 1:
            _text(p, 184, f"신청인: {NAME} ({BIRTH})")
        xs = [35, 85, 315, 395, 475, 560]
        ys = [220, 247, 285, 323]
        _grid(p, xs, ys)
        for i, label in enumerate(("번호", "주소", "발생일", "신고일", "세대주 및 관계")):
            _cell(p, xs[i], xs[i + 1], ys[0], ys[1], label)
        _cell(p, xs[0], xs[1], ys[1], ys[2], str(pno))
        _cell(p, xs[1], xs[2], ys[1], ys[2], address)
        _cell(p, xs[2], xs[3], ys[1], ys[2], occur)
        _cell(p, xs[3], xs[4], ys[1], ys[2], report)
        _cell(p, xs[4], xs[5], ys[1], ys[2], "본인")
        _cell(p, xs[1], xs[2], ys[2], ys[3], "변동사유 전입")
    out = d.tobytes()
    d.close()
    return out, {"name": NAME, "birth_date": BIRTH, "issue_date": ISSUE,
                 "applicant_name": NAME, "applicant_birth_date": BIRTH,
                 "history_count": 2}


def _payment_pdf() -> tuple[bytes, dict]:
    d = pymupdf.open()
    health = {month: (10100 if month == 10 else -500 if month == 11 else 10300 if month == 12 else 10000 + month * 100)
              for month in range(1, 13)}
    care = {month: 700 + month * 10 for month in range(1, 13)}
    for pno, months in ((1, range(1, 7)), (2, range(7, 13))):
        p = _page(d, "가입자 건강·장기요양보험료 납부확인서", pno, 2)
        _text(p, 100, f"가입자 성명 {NAME}")
        _text(p, 120, "생년월일 1999.01.01")
        _text(p, 140, "사업장 명칭 가상회사")
        _text(p, 160, "납부자번호 1234567890")
        _text(p, 178, "2025년 01월 ~ 2025년 12월 납부내역")
        xs = [35, 85] + [85 + i * 59.4 for i in range(1, 9)]
        ys = [185, 210, 239, 266, 291] + [315 + i * 24 for i in range(9)]
        # 월별은 3행 머리글 세로 병합, 고지·납부 그룹은 각 4열 가로 병합
        skip_v = {(0, 1), (1, 1)}
        skip_v |= {(1, 4), (1, 8)}
        skip_h = {(0, 2), (0, 3), (0, 4), (0, 6), (0, 7), (0, 8), (1, 3), (1, 7)}
        _grid(p, xs, ys, skip_vertical=skip_v, skip_horizontal=skip_h)
        _cell(p, xs[0], xs[1], ys[0], ys[3], "월별", size=7)
        _cell(p, xs[1], xs[5], ys[0], ys[1], "고지금액", size=7)
        _cell(p, xs[5], xs[9], ys[0], ys[1], "납부금액", size=7)
        for shift in (0, 4):
            _cell(p, xs[1 + shift], xs[2 + shift], ys[1], ys[2], "건강", size=7)
            _cell(p, xs[2 + shift], xs[3 + shift], ys[1], ys[2], "장기요양", size=6)
            _cell(p, xs[3 + shift], xs[5 + shift], ys[1], ys[2], "보수 외 소득월액", size=6)
            _cell(p, xs[1 + shift], xs[2 + shift], ys[2], ys[3], "보험료", size=7)
            _cell(p, xs[2 + shift], xs[3 + shift], ys[2], ys[3], "보험료", size=7)
            _cell(p, xs[3 + shift], xs[4 + shift], ys[2], ys[3], "(건강)", size=7)
            _cell(p, xs[4 + shift], xs[5 + shift], ys[2], ys[3], "(요양)", size=7)
        page_months = list(months)
        settlement = pno == 2
        row_values = []
        for month in page_months:
            row_values.append([f"{month}월", str(health[month]), str(care[month]), "0", "0",
                               str(health[month] - 200), str(care[month] - 20), "0", "0"])
        if settlement:
            row_values.append(["연말정산", "-250", "-25", "", "", "-220", "-20", "", ""])
        billed_totals = [sum(int(values[col]) for values in row_values if values[col]) for col in range(1, 5)]
        paid_totals = [sum(int(values[col]) for values in row_values if values[col]) for col in range(5, 9)]
        row_values.append(["합계", *map(str, billed_totals), *map(str, paid_totals)])
        for row, values in enumerate(row_values):
            top, bottom = ys[3 + row], ys[4 + row]
            for col, value in enumerate(values):
                size = 8 if col == 0 and value in {"연말정산", "합계"} else 7
                _cell(p, xs[col], xs[col + 1], top, bottom, value, size=size)
        _text(p, 525, "위와 같이 보험료를 납부하였음을 확인합니다", size=9)
        _text(p, 552, "2026 년 11 월 10 일", size=10)
        _text(p, 580, "국민건강보험공단 이사장", size=9)
    out = d.tobytes()
    d.close()
    return out, {"name": NAME, "birth_date": BIRTH, "issue_date": ISSUE,
                 "insurance_type": "직장", "billed_by_month": {f"2025-{m:02d}": health[m] for m in health},
                 "long_term_care_by_month": {f"2025-{m:02d}": care[m] for m in care}}


def _acquisition_pdf() -> tuple[bytes, dict]:
    d = pymupdf.open()
    history = [
        {"category": "지역", "acquired": "2020-03-01", "lost": "2021-12-31"},
        {"category": "직장", "acquired": "2022-01-01", "lost": "2023-05-31"},
        {"category": "직장", "acquired": "2023-06-01", "lost": None},
    ]
    for pno, rows in ((1, history[:2]), (2, history[2:])):
        p = _page(d, "건강보험 자격득실확인서", pno, 2)
        _text(p, 105, f"성명 {NAME}")
        _text(p, 126, "생년월일 1999.01.01")
        _text(p, 146, "발급일 2026.11.10")
        _text(p, 168, "조회기간 2020.01.01 ~ 2026.11.10")
        xs = [35, 150, 255, 365, 560]
        ys = [205, 235, 270, 305, 340]
        _grid(p, xs, ys)
        headers = ["가입자구분", "자격취득일", "자격상실일", "사업장명칭"]
        for i, value in enumerate(headers):
            _cell(p, xs[i], xs[i + 1], ys[0], ys[1], value, size=7)
        for row_index, row in enumerate(rows):
            for col, value in enumerate((row["category"], row["acquired"], row["lost"] or "", "가상사업장")):
                _cell(p, xs[col], xs[col + 1], ys[row_index + 1], ys[row_index + 2], value or "", size=7)
    out = d.tobytes()
    d.close()
    return out, {"name": NAME, "birth_date": BIRTH, "issue_date": ISSUE,
                 "recent_five_years": True, "history": history}


def main() -> None:
    if not FONT.exists():
        raise SystemExit("한글 합성 문서용 macOS 글꼴이 필요합니다.")
    _load_local_key()
    os.environ.setdefault("JBAI_ALLOW_REAL_DOCS", "false")
    FIXTURES.mkdir(parents=True, exist_ok=True)
    documents = {
        "resident_abstract": _resident_pdf,
        "nhis_payment": _payment_pdf,
        "nhis_acquisition_loss": _acquisition_pdf,
    }
    for kind, builder in documents.items():
        pdf, expected = builder()
        pdf_path = FIXTURES / f"{kind}.pdf"
        pdf_path.write_bytes(pdf)
        recorded = {"doc_type": kind, "expected": expected, "pages": []}
        with pymupdf.open(stream=pdf, filetype="pdf") as document:
            for page_index, page in enumerate(document):
                pix = page.get_pixmap(matrix=pymupdf.Matrix(200 / 72, 200 / 72), alpha=False)
                response = run_jbai_image_pair(pix.tobytes("png"), (pix.width, pix.height), page=page_index)
                recorded["pages"].append({
                    "page": page_index,
                    "ocr_content": response.raw_content,
                    "table_content": response.table_content,
                })
        (FIXTURES / f"{kind}.json").write_text(
            json.dumps(recorded, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"{kind}: {len(recorded['pages'])} 쪽 녹화 완료 (합성 서류)")


if __name__ == "__main__":
    main()

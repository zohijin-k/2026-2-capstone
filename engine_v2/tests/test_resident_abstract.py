"""초본 추출기 테스트 — 실측 레이아웃 좌표를 그대로 본뜬 가짜 OCR 결과 사용 (개인정보 없음).

  python -m pytest tests/ -q      또는      python -m engine_v2.tests.test_resident_abstract
"""

from __future__ import annotations

from datetime import date

from ..extractors.resident_abstract import extract, months_between, trailing_residence_start
from ..pipeline.ocr import OcrResult, OcrWord
from ..pipeline.preprocess import PageImage, PageSource
from ..schemas.models import DocType

W, H = 2066, 2923


def wd(x: float, y: float, text: str, conf: float = 0.5, width: float = 10) -> OcrWord:
    """페이지 % 좌표로 단어 배치."""
    return OcrWord(text, conf, (x / 100 * W, y / 100 * H, (x + width) / 100 * W, (y + 1.0) / 100 * H))


def header(page: int, total: int, issue="2026년 11월 10일", name="김전북", title="초 본",
           applicant: str | None = None) -> list[OcrWord]:
    a, b = title.split()
    words = [
        wd(16.5, 3.3, "문서확인번호 : 1234-5678-9012-34567", 1.0, 30), wd(79.4, 3.3, f"{page}/{total}", 1.0, 3),
        wd(46.5, 5.4, f"이 {a}{b}은 개인별 주민등록표의 기재 내용을", 1.0, 30),
        wd(15.4, 7.4, "주민등록표", 0.5), wd(46.5, 7.4, "그대로 증명합니다.", 1.0),
        wd(14.6, 10.0, "(", 1.0, 1), wd(20.4, 10.0, a, 0.5, 2), wd(33.5, 10.0, f"{b} )", 0.5, 3),
        wd(58.6, 12.8, issue, 1.0, 15), wd(65.4, 14.5, "전북특별자치도 전주시장", 1.0, 20),
        wd(9.5, 17.7, "성명(한자)", 0.5, 8), wd(22.8, 17.7, name, 0.5, 8), wd(36.4, 17.7, "( 金全北", 0.5, 8),
        wd(49.6, 17.7, ")", 0.5, 1), wd(54.5, 17.7, "주민등록번호", 1.0, 10), wd(68.3, 17.7, "990101-1234567", 1.0, 15),
    ]
    if applicant is not None:
        words.append(wd(14.0, 19.5, applicant, 1.0, 35))
    return words


def table_head(y: float) -> list[OcrWord]:
    return [wd(7.8, y, "번호", 0.5, 4), wd(24.5, y, "주", 0.5, 2), wd(39.7, y, "소", 0.5, 2),
            wd(54.1, y, "발생일 / 신고일", 0.5, 12), wd(78.6, y, "세대주및관계", 0.5, 10),
            wd(54.5, y + 0.8, "변 동", 0.5, 4), wd(74.3, y + 0.8, "사 유", 0.5, 4)]


def row(y: float, no: int, addr: str, rep: str, occ: str | None = None, reason="전입",
        no_on_top: bool = False, detail: str | None = None) -> list[OcrWord]:
    out = [wd(13.2, y, addr, 1.0, 35), wd(67.9, y, rep, 1.0, 9), wd(79.2, y, "김전북 본인", 0.5, 12)]
    if occ:
        out.append(wd(54.3, y, occ, 1.0, 9))
    if no_on_top:
        out.append(wd(8.4, y, str(no), 1.0, 2))
    else:
        out.append(wd(9.1, y + 0.9, str(no), 1.0, 2))
    out.append(wd(72.6, y + 0.9, reason, 0.5, 6))
    if detail:
        out.append(wd(13.4, y + 0.9, detail, 1.0, 20))
    return out


def footer() -> list[OcrWord]:
    return [wd(7.0, 79.0, "수수료 1. 본인이 발급한 주민등록표는 ...", 1.0, 80)]


def page(i: int, words: list[OcrWord]) -> tuple[PageImage, OcrResult]:
    p = PageImage(page=i, source=PageSource.EMBEDDED, page_size_pt=(595, 842), png=b"",
                  pixel_size=(W, H), dpi=250)
    return p, OcrResult("fake", words)


def build(**kw):
    p0 = header(1, 3, **kw) + table_head(31.8) + [
        *row(34.4, 1, "서울특별시 관악구 신림동 123-4", "2005-03-02", "2005-03-01"),
        *row(37.8, 2, "서울특별시 관악구 신림동 123-4", "2008-01-10", reason="세대주변경"),
        *row(41.3, 3, "전라북도 전주시 완산구 효자동 456", "2015-02-20", "2015-02-18"),
    ] + [wd(8.0, 69.9, "병역", 0.5, 3), wd(8.0, 71.1, "사항", 0.5, 3)] + footer()
    p1 = header(2, 3, **kw) + table_head(21.1) + [
        *row(23.7, 4, "전라북도 전주시 덕진구 금암동 78", "2019-08-05", "2019-08-01"),
        *row(27.8, 5, "경기도 수원시 팔달구 인계동 9", "2021-03-02", "2021-03-01", no_on_top=True),
        *row(30.4, 6, "경기도 수원시 팔달구 인계동 9", "2022-01-03", reason="세대주변경"),
        *row(34.6, 7, "전라북도 전주시 덕진구 금암동 10", "2023-09-01", "2023-08-30",
             no_on_top=True, detail="금암2동 101-202"),
    ] + footer()
    p2 = header(3, 3, **kw) + table_head(21.1) + [
        wd(8.4, 24.6, "8", 1.0, 2),                                     # 실측: 메모 줄에도 순번
        wd(13.0, 24.6, "[도로명주소 (11.07.29) 도로명주소로 주소변경]", 1.0, 40),
        *row(27.0, 9, "전라북도 전주시 덕진구 금암동 10,", "2023-09-01", reason="도로명주소", detail="기린대로 123 (금암동)"),
        wd(8.4, 38.1, "10", 1.0, 2),
        wd(13.0, 38.1, "[행정구역 변경(2024.1.18.) 전북특별자치도로 변경]", 1.0, 40),
        *row(40.6, 11, "전북특별자치도 전주시 덕진구 금암동 10,", "2024-01-18", reason="행정변경"),
        wd(42.8, 44.6, "== 이하 여백==", 0.5, 12),
    ] + footer()
    return [page(0, p0), page(1, p1), page(2, p2)]


def test_basic_fields():
    r = extract(build(), today=date(2026, 11, 10))
    f = r.fields
    assert r.detected_type == DocType.RESIDENT_ABSTRACT
    assert f["issue_date"].value == date(2026, 11, 10)
    assert f["name"].value == "김전북"
    assert f["birth_date"].value == date(1999, 1, 1)
    assert "1234567" not in f["birth_date"].raw_text          # 주민번호 뒷자리 미보존
    assert f["issue_date"].confidence >= 0.9                    # 3쪽 일치 → 높은 신뢰도
    assert f["issue_date"].bbox is not None and f["issue_date"].bbox.page == 0


def test_applicant_identity_fields():
    r = extract(build(applicant="신청인: 김전북 (1999-01-01)"), today=date(2026, 11, 10))
    assert r.fields["applicant_name"].value == "김전북"
    assert r.fields["applicant_birth_date"].value == date(1999, 1, 1)
    assert r.fields["applicant_name"].bbox is not None


def test_applicant_unreadable_is_not_guessed():
    r = extract(build(applicant="신청인: 김전북 (생년월일 확인불가)"), today=date(2026, 11, 10))
    assert "applicant_name" not in r.fields
    assert "applicant_birth_date" not in r.fields
    assert any("신청인" in warning for warning in r.warnings)


def test_single_address_history_count_is_preserved():
    words = header(1, 1, applicant="신청인: 김전북 (1999-01-01)") + table_head(31.8)
    words += row(34.4, 1, "전북특별자치도 전주시 완산구 효자동 456", "2023-08-30", "2023-08-30")
    r = extract([page(0, words)], today=date(2026, 11, 10))
    assert r.fields["address_history_count"].value == 1


def test_history_parsing():
    r = extract(build(), today=date(2026, 11, 10))
    h = r.history
    assert [e.no for e in h] == [1, 2, 3, 4, 5, 6, 7, 9, 11]   # 8, 10은 메모 줄 번호
    assert h[1].occurred is None and h[1].reported == date(2008, 1, 10)
    assert "금암2동 101-202" in h[6].address_text               # 둘째 줄 주소 상세가 붙음
    assert h[7].notes and h[7].notes[0].startswith("[도로명")   # 메모는 다음 건에 붙음
    assert all(v.passed for v in r.validations), [v for v in r.validations if not v.passed]


def test_residence_continuity_across_rename():
    r = extract(build(), today=date(2026, 11, 10))
    start = trailing_residence_start(r.history, "전북")
    assert start == date(2023, 8, 30)                           # 수원 → 전주 전입일 (명칭 변경으로 안 끊김)
    assert months_between(start, date(2026, 11, 10)) == 38


def test_register_detected():
    r = extract(build(title="등 본"), today=date(2026, 11, 10))
    assert r.detected_type == DocType.RESIDENT_REGISTER


def test_inconsistent_issue_date_lowers_confidence():
    pages = build()
    p, res = pages[1]
    for w in res.words:
        if "년" in w.text and "월" in w.text:
            w.text = "2026년 11월 18일"                          # OCR 오독 가정
    r = extract(pages, today=date(2026, 11, 20))
    assert r.fields["issue_date"].value == date(2026, 11, 10)  # 다수결
    assert r.fields["issue_date"].confidence < 0.9


def test_missing_row_number_detected():
    pages = build()
    _, res = pages[1]
    res.words = [w for w in res.words if w.text != "5"]          # 순번 5를 OCR이 놓친 경우
    r = extract(pages, today=date(2026, 11, 10))
    v = {x.name: x for x in r.validations}
    assert not v["history_numbers_sequential"].passed
    assert "빠진 번호 [5]" in v["history_numbers_sequential"].detail


def test_missing_page_detected():
    r = extract(build()[:2], today=date(2026, 11, 10))
    v = {x.name: x for x in r.validations}
    assert not v["pages_complete"].passed


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)

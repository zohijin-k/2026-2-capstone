"""면접확인서 판독기 테스트. 모든 인물·회사·연락처는 가상 값이다.

`official_words`는 사업계획서 서식(demo/fixtures/templates/job_interview_confirmation.pdf)의
칸 위치를 페이지 비율로 옮긴 것이다 (라벨 x≈21%, 값 x≈29%, 오른쪽 칸 라벨 x≈56%·값 x≈65%).
"""
from datetime import date

from ..extractors import interview_confirmation
from ..pipeline.ocr import OcrResult, OcrWord
from ..pipeline.preprocess import PageImage, PageSource
from ..schemas.models import DocType

W, H = 1000, 1414
TODAY = date(2026, 11, 11)


def wd(x: float, y: float, text: str, width: float = 8) -> OcrWord:
    return OcrWord(text, 0.99, (x / 100 * W, y / 100 * H, (x + width) / 100 * W, (y + 0.8) / 100 * H))


def page(words: list[OcrWord]):
    image = PageImage(page=0, source=PageSource.EMBEDDED, page_size_pt=(595, 841), png=b"",
                      pixel_size=(W, H), dpi=200)
    return image, OcrResult("synthetic", words)


def run(words):
    return interview_confirmation.extract([page(words)], today=TODAY)


def values(result) -> dict:
    return {key: field.value for key, field in result.fields.items()}


def checks(result) -> dict:
    return {item.name: item.passed for item in result.validations}


def official_words(interview: str = "2026. 03. 20. 14:00~14:40", signed_company: str = "한빛테크(주)"):
    return [
        wd(39, 10.5, "면접확인서", 22),
        wd(21, 19.8, "성  명"), wd(29, 19.8, "김가상"), wd(56, 19.8, "생년월일"), wd(65, 19.8, "1999. 01. 01.", 14),
        wd(10, 23.7, "면접자"), wd(21, 23.7, "주  소"), wd(29, 23.7, "전북특별자치도 전주시 가상로 12", 30),
        wd(21, 27.5, "연락처"), wd(29, 27.5, "010-0000-0000", 14), wd(56, 27.5, "이메일"), wd(65, 27.5, "test@example.com", 18),
        wd(21, 31.5, "회사명"), wd(29, 31.5, "한빛테크(주)", 12),
        wd(21, 35.3, "소재지"), wd(29, 35.3, "전북특별자치도 전주시 덕진구 가상로 34", 32),
        wd(10, 37.2, "면접기업"), wd(20, 39.2, "업태/업종", 9), wd(29, 39.2, "정보통신업/소프트웨어 개발", 26),
        wd(21, 43.0, "담당자"), wd(29, 43.0, "박담당"), wd(56, 43.0, "연락처"), wd(65, 43.0, "063-000-0000", 14),
        wd(20, 46.8, "면접일시"), wd(29, 46.8, interview, 24),
        wd(10, 50.7, "면접현황"), wd(20, 50.7, "면접장소"), wd(29, 50.7, "본사 3층 회의실", 16),
        wd(20, 54.5, "응시직군"), wd(29, 54.5, "사무 행정", 10),
        wd(13, 58.5, "상기인은 위와 같이 기업의 채용을 위한 면접에 참석하였음을", 76), wd(43, 61.2, "확인합니다.", 14),
        wd(38, 67.3, "2026년", 8), wd(48, 67.3, "3", 2), wd(51, 67.3, "월", 3), wd(56, 67.3, "20", 3), wd(60, 67.3, "일", 3),
        wd(52, 75.8, "회사명 :", 10), wd(63, 75.8, signed_company, 14),
        wd(52, 79.4, "담당자 :", 10), wd(63, 79.4, "박담당"), wd(79, 79.4, "(서명/인)", 10),
    ]


def test_official_form_reads_interview_fields():
    result = run(official_words())
    assert result.detected_type == DocType.INTERVIEW_CONFIRM
    assert values(result) == {
        "성명": "김가상", "생년월일": date(1999, 1, 1), "회사명": "한빛테크(주)",
        "업태업종": "정보통신업/소프트웨어 개발", "면접일": date(2026, 3, 20), "면접시간": "14:00~14:40",
        "면접장소": "본사 3층 회의실", "응시직군": "사무 행정", "확인일": date(2026, 3, 20),
    }
    assert all(checks(result).values())
    assert result.fields["면접일"].confidence == 1.0
    assert result.warnings == []


def test_contact_details_are_not_extracted():
    result = run(official_words())
    raw = " ".join(str(field.raw_text) for field in result.fields.values())
    assert not {"주소", "연락처", "이메일", "담당자", "소재지"} & set(result.fields)
    assert "010-0000-0000" not in raw and "test@example.com" not in raw and "박담당" not in raw


def test_unfilled_template_date_is_not_read():
    result = run(official_words(interview="2026. 00. 00. 00:00~00:00"))
    assert "면접일" not in result.fields
    assert not checks(result)["interview_date_found"]
    assert any("면접일" in warning for warning in result.warnings)


def test_signed_company_must_match_company_cell():
    result = run(official_words(signed_company="새솔물산"))
    assert not checks(result)["company_names_match"]
    assert result.fields["회사명"].confidence < 1.0
    assert any("서명란 회사명" in warning for warning in result.warnings)


def test_company_suffix_difference_is_same_company():
    result = run(official_words(signed_company="한빛테크 주식회사"))
    assert checks(result)["company_names_match"]


def test_company_own_layout():
    result = run([
        wd(35, 5, "면 접 확 인 서", 30), wd(10, 14, "성명: 이가상", 20), wd(45, 14, "생년월일: 2001.05.06", 25),
        wd(10, 18, "기업명: 새솔물산", 22), wd(10, 21, "업종: 도소매", 18),
        wd(10, 24, "면접일자: 2026년 3월 20일", 30), wd(10, 27, "지원분야: 영업", 18),
        wd(10, 33, "위 사람이 당사 채용 면접에 참석하였음을 확인합니다.", 60),
        wd(38, 38, "2026년 3월 21일", 20), wd(35, 44, "새솔물산 대표 (인)", 24),
    ])
    got = values(result)
    assert result.detected_type == DocType.INTERVIEW_CONFIRM
    assert (got["성명"], got["생년월일"], got["회사명"], got["업태업종"]) == (
        "이가상", date(2001, 5, 6), "새솔물산", "도소매")
    assert (got["면접일"], got["응시직군"], got["확인일"]) == (date(2026, 3, 20), "영업", date(2026, 3, 21))
    assert "company_names_match" not in checks(result)  # 서명란 회사명 칸이 없는 양식


def test_unrelated_document_is_unknown():
    result = run([wd(30, 5, "주민등록표 (초본)", 30), wd(10, 12, "성명"), wd(25, 12, "김가상")])
    assert result.detected_type == DocType.UNKNOWN
    assert not checks(result)["document_type"]

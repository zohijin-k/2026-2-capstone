"""응시확인서·성적표 판독기 테스트. 모든 인물·시험·기관은 가상 값이다."""
from datetime import date

from ..extractors import exam_docs
from ..pipeline.ocr import OcrResult, OcrWord
from ..pipeline.preprocess import PageImage, PageSource
from ..schemas.models import DocType

W, H = 1000, 1400
TODAY = date(2026, 11, 11)


def wd(x: float, y: float, text: str, width: float = 8) -> OcrWord:
    return OcrWord(text, 0.99, (x / 100 * W, y / 100 * H, (x + width) / 100 * W, (y + 0.8) / 100 * H))


def page(words: list[OcrWord]):
    image = PageImage(page=0, source=PageSource.EMBEDDED, page_size_pt=(595, 842), png=b"",
                      pixel_size=(W, H), dpi=250)
    return image, OcrResult("synthetic", words)


def run(words):
    return exam_docs.extract([page(words)], today=TODAY)


def values(result) -> dict:
    return {key: field.value for key, field in result.fields.items()}


def checks(result) -> dict:
    return {item.name: item.passed for item in result.validations}


def admission_words(exam_date: str = "2026. 4. 12.(일)", issue: str = "발급일자: 2026. 4. 30."):
    words = [
        wd(35, 4, "응 시 확 인 서", 30),
        wd(10, 12, "성 명"), wd(25, 12, "김가상"), wd(55, 12, "생년월일"), wd(70, 12, "1999. 01. 01.", 14),
        wd(10, 15, "수험번호"), wd(25, 15, "26123456"),
        wd(10, 18, "종 목 명"), wd(25, 18, "정보처리기능사", 16),
        wd(10, 24, "시험장소"), wd(25, 24, "전주 가상고등학교", 18),
        wd(10, 30, "위 사람은 위 시험에 응시하였음을 확인합니다.", 50),
        wd(30, 36, issue, 25), wd(35, 42, "전북가상검정원장", 20),
    ]
    if exam_date:
        words += [wd(10, 21, "시험일자"), wd(25, 21, exam_date, 16)]
    return words


def test_admission_reads_name_exam_and_dates():
    result = run(admission_words())
    assert result.detected_type == DocType.EXAM_ADMISSION
    assert values(result) == {
        "성명": "김가상", "생년월일": date(1999, 1, 1), "시험명": "정보처리기능사",
        "응시일": date(2026, 4, 12), "발급일": date(2026, 4, 30),
    }
    assert all(checks(result).values())
    assert result.fields["응시일"].confidence == 1.0
    assert result.warnings == []


def test_score_report_is_its_own_type():
    result = run([
        wd(35, 4, "성 적 통 지 서", 30), wd(10, 12, "성명"), wd(25, 12, "이가상"),
        wd(10, 15, "종목"), wd(25, 15, "컴퓨터활용능력 2급", 18), wd(10, 18, "시험일"), wd(25, 18, "2026-05-23", 14),
        wd(10, 21, "점수"), wd(25, 21, "85점"), wd(45, 21, "합격여부"), wd(60, 21, "합격"),
        wd(10, 25, "출력일"), wd(25, 25, "2026-06-10", 14),
    ])
    assert result.detected_type == DocType.EXAM_SCORE
    got = values(result)
    assert (got["성명"], got["시험명"], got["응시일"], got["발급일"]) == (
        "이가상", "컴퓨터활용능력 2급", date(2026, 5, 23), date(2026, 6, 10))


def test_missing_exam_date_is_not_filled_and_warns():
    result = run(admission_words(exam_date=""))
    assert "응시일" not in result.fields
    assert not checks(result)["exam_date_found"]
    assert any("응시일" in warning for warning in result.warnings)


def test_exam_date_after_issue_fails_order():
    result = run(admission_words(exam_date="2026. 5. 12.", issue="발급일자: 2026. 4. 30."))
    assert not checks(result)["exam_date_not_after_issue"]
    assert result.fields["응시일"].confidence < 1.0


def test_admission_ticket_is_not_accepted():
    result = run([wd(40, 4, "수 험 표", 20), wd(10, 12, "성명"), wd(25, 12, "김가상"),
                  wd(10, 15, "시험일시"), wd(25, 15, "2026. 4. 12. 09:00", 18)])
    assert result.detected_type == DocType.UNKNOWN
    assert not checks(result)["document_type"]
    assert any("수험표" in warning for warning in result.warnings)


def test_rrn_back_digits_are_erased_and_birth_is_kept():
    words = admission_words()
    words = [word for word in words if word.text not in {"생년월일", "1999. 01. 01."}]
    rrn = wd(25, 27, "990101-1234567", 16)
    words += [wd(10, 27, "주민등록번호", 14), rrn]
    result = run(words)
    assert rrn.text == "990101-1******"
    assert values(result)["생년월일"] == date(1999, 1, 1)
    assert all("1234567" not in str(field.raw_text) for field in result.fields.values())

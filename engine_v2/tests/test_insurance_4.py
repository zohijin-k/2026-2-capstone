"""4대 사회보험 가입내역 확인서 테스트. 모든 인물·회사·식별번호는 가상 값이다."""
import json
from datetime import date

from ..extractors import insurance_4
from ..pipeline.ocr import OcrResult, OcrWord
from ..pipeline.preprocess import PageImage, PageSource

W, H = 1000, 1400


def wd(x: float, y: float, text: str, width: float = 8) -> OcrWord:
    return OcrWord(text, 0.99, (x / 100 * W, y / 100 * H,
                                (x + width) / 100 * W, (y + 0.8) / 100 * H))


def page(words: list[OcrWord]):
    image = PageImage(page=0, source=PageSource.EMBEDDED, page_size_pt=(595, 842), png=b"",
                      pixel_size=(W, H), dpi=250)
    return image, OcrResult("synthetic", words)


def _base():
    return [
        wd(12, 3, "문서확인번호"), wd(35, 3, "1234-5678-9012-3456", 22),
        wd(15, 13, "4대 사회보험"), wd(14, 16, "가입자 가입내역 확인서"),
        wd(10, 21, "발급번호"), wd(30, 21, "98765432109876", 18),
        wd(58, 21, "발급일시"), wd(74, 21, "2026.11.10 10:20", 18),
        wd(10, 25, "주민(외국인)등록번호"), wd(34, 25, "990101-1123456", 20),
        wd(60, 25, "성명"), wd(80, 25, "김전북", 12),
        wd(10, 29, "가입 내역(발급일자 현재기준)"), wd(87, 29, "1 / 1"),
        wd(14, 31, "내역"), wd(23, 31, "성명"), wd(34, 31, "가입자종별"),
        wd(48, 31, "사업장"), wd(48, 32, "관리번호"), wd(65, 31, "사업장명칭"),
        wd(82, 31, "자격취득일"), wd(82, 32, "(신고접수일)"),
    ]


def synthetic_words():
    # 지역가입자 + 피부양자 + 미가입 2행. 괄호 속 '-'는 빈 신고접수일.
    return _base() + [
        wd(9, 36, "국민연금"), wd(23, 36, "김전북"), wd(34, 36, "지역가입자", 12),
        wd(82, 36, "2020.01.02"), wd(82, 37, "(-)"),
        wd(9, 40, "건강보험"), wd(23, 40, "김전북"), wd(34, 40, "직장피부양자", 14),
        wd(48, 40, "-"), wd(65, 40, "-"), wd(82, 40, "2021.02.03"), wd(82, 41, "(2021.02.04)"),
        wd(9, 44, "산재보험"), wd(23, 44, "미가입"), wd(34, 44, "미가입"),
        wd(48, 44, "미가입"), wd(65, 44, "미가입"), wd(82, 44, "미가입"),
        wd(9, 48, "고용보험"), wd(23, 48, "미가입"), wd(34, 48, "미가입"),
        wd(48, 48, "미가입"), wd(65, 48, "미가입"), wd(82, 48, "(-)"),
    ]


def employed_words():
    # 직장가입자 + 사업장 정보, 고용·산재 가입.
    return _base() + [
        wd(9, 36, "국민연금"), wd(23, 36, "김전북"), wd(34, 36, "사업장가입자", 14),
        wd(48, 36, "12345678901", 12), wd(65, 36, "가상회사", 12),
        wd(82, 36, "2023.01.02"), wd(82, 37, "(-)"),
        wd(9, 40, "건강보험"), wd(23, 40, "김전북"), wd(34, 40, "직장가입자", 12),
        wd(48, 40, "12345678901", 12), wd(65, 40, "가상회사", 12),
        wd(82, 40, "2023.01.03"), wd(82, 41, "(2023.01.02)"),
        wd(9, 44, "산재보험"), wd(23, 44, "김전북"), wd(34, 44, "사업장가입자", 14),
        wd(48, 44, "12345678901", 12), wd(65, 44, "가상회사", 12),
        wd(82, 44, "2023.01.05"), wd(82, 45, "(-)"),
        wd(9, 48, "고용보험"), wd(23, 48, "김전북"), wd(34, 48, "사업장가입자", 14),
        wd(48, 48, "12345678901", 12), wd(65, 48, "가상회사", 12),
        wd(82, 48, "2023.01.06"), wd(82, 49, "(2023.01.07)"),
    ]


def test_extracts_actual_enrollment_rows_and_discards_rrn_tail():
    pages = [page(synthetic_words())]
    result = insurance_4.extract(pages, today=date(2026, 11, 11))
    assert result.detected_type.value == "insurance_4"
    assert result.fields["문서확인번호"].value == "1234-5678-9012-3456"
    assert result.fields["발급번호"].value == "98765432109876"
    assert result.fields["발급일"].value == date(2026, 11, 10)
    assert result.fields["성명"].value == "김전북"
    assert result.fields["생년월일"].value == date(1999, 1, 1)
    checks = {item.name: item.passed for item in result.validations}
    assert all(checks.values()), result.validations
    assert [row.insurance_type for row in result.rows] == ["국민연금", "건강보험", "산재보험", "고용보험"]
    assert result.rows[0].subscriber_category == "지역가입자"
    assert result.rows[0].received is None
    assert result.rows[1].subscriber_category == "직장피부양자"
    assert result.rows[1].received == date(2021, 2, 4)
    assert result.rows[2].status == "미가입" and not result.rows[2].subscriber_name
    assert "상실일" not in result.fields["가입내역"].value
    assert result.fields["가입내역"].bbox is not None
    serialized = json.dumps({key: field.model_dump(mode="json") for key, field in result.fields.items()}, ensure_ascii=False)
    assert "123456" not in serialized
    assert "123456" not in " ".join(word.text for word in pages[0][1].words)


def test_work_summary_and_receipt_warning_are_not_eligibility_judgments():
    result = insurance_4.extract([page(employed_words())], today=date(2026, 11, 11))
    checks = {item.name: item.passed for item in result.validations}
    assert all(checks.values()), result.validations
    assert result.rows[0].management_number == "12345678901"
    assert result.rows[0].workplace_name == "가상회사"
    assert result.fields["근로관련가입여부"].value == "True"
    assert result.fields["근로관련최초취득일"].value == "2023-01-02"
    assert result.fields["근로관련최근취득일"].value == "2023-01-06"
    assert any("신고접수일이 자격취득일보다 빠른" in warning for warning in result.warnings)
    # 신고접수일이 취득일보다 빠른 것은 경고이며 검증 실패가 아니다.
    assert all(checks.values())


def test_rejects_other_types_and_checks_page_marker_and_future_issue_date():
    for words in ([wd(10, 8, "주민등록표 초본")], [wd(10, 8, "건강보험료 납부확인서")]):
        assert insurance_4.extract([page(words)], today=date(2026, 11, 11)).detected_type.value == "unknown"
    words = synthetic_words()
    next(word for word in words if word.text == "1 / 1").text = "1 / 2"
    next(word for word in words if word.text == "2026.11.10 10:20").text = "2027.11.10 10:20"
    result = insurance_4.extract([page(words)], today=date(2026, 11, 11))
    checks = {item.name: item.passed for item in result.validations}
    assert not checks["page_marker_1_of_1"]
    assert not checks["issue_not_future"]


def test_requires_parseable_parenthesized_receipt_date():
    words = employed_words()
    next(word for word in words if word.text == "(2023.01.02)").text = "(2023.99.99)"
    result = insurance_4.extract([page(words)], today=date(2026, 11, 11))
    checks = {item.name: item.passed for item in result.validations}
    assert not checks["date_formats"]

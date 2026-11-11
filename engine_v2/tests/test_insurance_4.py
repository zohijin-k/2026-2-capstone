"""4대 사회보험 판독기 테스트. 모든 인물·회사·식별번호는 가상 값이다."""

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


def synthetic_words() -> list[OcrWord]:
    words = [
        wd(10, 3, "문서확인번호"), wd(36, 3, "1234-5678-9012-3456", 22),
        wd(10, 8, "4대 사회보험 가입내역 확인서", 38),
        wd(10, 13, "발급번호"), wd(25, 13, "98765432109876", 18),
        wd(58, 13, "발급일시"), wd(72, 13, "2026.11.10 10:20", 18),
        wd(15, 20, "외국인등록번호"), wd(35, 20, "990101-1234567", 20),
        wd(60, 20, "성명"), wd(80, 20, "김전북", 12),
        wd(8, 30, "구분"), wd(22, 30, "성명"), wd(33, 30, "가입자구분"),
        wd(48, 30, "사업장"), wd(48, 31, "관리번호"), wd(64, 31, "사업장명칭"),
        wd(82, 30, "자격취득일"), wd(82, 31, "(자격상실일)"),
        wd(8, 36, "국민연금"), wd(33, 36, "지역가입자"),
        wd(82, 36, "2020.01.02"), wd(82, 37, "(-)"),
        wd(8, 40, "건강보험"), wd(33, 40, "직장가입자"),
        wd(64, 40, "가상회사주식회사", 22), wd(82, 40, "2021.02.03"),
        wd(82, 41, "(2024.04.05)"),
        wd(8, 44, "산재보험"), wd(22, 44, "미가입"), wd(33, 44, "미가입"),
        wd(64, 44, "미가입"), wd(82, 44, "(-)"),
        wd(8, 48, "고용보험"), wd(33, 48, "직장가입자"),
        wd(64, 48, "가상회사주식회사", 22), wd(82, 48, "2023.06.07"),
        wd(7, 71, "위와 같이 가입내역을 확인합니다.", 36),
    ]
    return words


def test_extracts_all_insurer_rows_and_wrapped_loss_date_without_retaining_rrn():
    pages = [page(synthetic_words())]
    result = insurance_4.extract(pages, today=date(2026, 11, 11))

    assert result.detected_type.value == "insurance_4"
    assert result.fields["문서확인번호"].value == "1234-5678-9012-3456"
    assert result.fields["발급번호"].value == "98765432109876"
    assert result.fields["발급일"].value == "2026-11-10"
    assert result.fields["성명"].value == "김전북"
    assert result.fields["생년월일"].value == "1999-01-01"
    assert all(item.passed for item in result.validations), result.validations
    assert len(result.rows) == 4
    assert result.rows[1].acquired == date(2021, 2, 3)
    assert result.rows[1].lost == date(2024, 4, 5)
    assert result.rows[2].status == "미가입"
    assert result.rows[3].acquired == date(2023, 6, 7)
    assert result.fields["가입내역"].bbox is not None
    assert all(field.bbox is not None for field in result.fields.values())
    serialized = json.dumps({key: field.model_dump(mode="json") for key, field in result.fields.items()},
                            ensure_ascii=False)
    assert "1234567" not in serialized
    assert "98765432109876" in serialized  # 발급번호는 별도 서류 식별값
    source_text = " ".join(word.text for word in pages[0][1].words)
    assert "1234567" not in source_text


def test_rejects_other_document_types_and_validation_errors():
    for words in (
        [wd(10, 8, "주민등록표 초본"), wd(10, 20, "성명"), wd(20, 20, "김전북")],
        [wd(10, 8, "건강보험료 납부확인서"), wd(10, 20, "고지금액"), wd(20, 20, "200000")],
    ):
        assert insurance_4.extract([page(words)], today=date(2026, 11, 11)).detected_type.value == "unknown"

    invalid = synthetic_words()
    for word in invalid:
        if word.text == "2026.11.10 10:20":
            word.text = "2027.11.10 10:20"
    result = insurance_4.extract([page(invalid)], today=date(2026, 11, 11))
    checks = {item.name: item.passed for item in result.validations}
    assert not checks["issue_not_future"]

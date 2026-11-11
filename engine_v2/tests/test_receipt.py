"""결제영수증 판독기 테스트. 모든 상호·번호·금액은 가상 값이다."""
from datetime import date

from ..extractors import job_common as job
from ..extractors import receipt
from ..pipeline.ocr import OcrResult, OcrWord
from ..pipeline.preprocess import PageImage, PageSource
from ..schemas.models import DocType

W, H = 1000, 1400
TODAY = date(2026, 11, 11)
BRN = "123-45-67891"  # 검증숫자가 맞는 가상 번호


def wd(x: float, y: float, text: str, width: float = 8, conf: float = 0.99) -> OcrWord:
    return OcrWord(text, conf, (x / 100 * W, y / 100 * H, (x + width) / 100 * W, (y + 0.8) / 100 * H))


def page(words: list[OcrWord]):
    image = PageImage(page=0, source=PageSource.EMBEDDED, page_size_pt=(595, 842), png=b"",
                      pixel_size=(W, H), dpi=250)
    return image, OcrResult("synthetic", words)


def run(words):
    return receipt.extract([page(words)], today=TODAY)


def values(result) -> dict:
    return {key: field.value for key, field in result.fields.items()}


def checks(result) -> dict:
    return {item.name: item.passed for item in result.validations}


def card_slip_words(items=(("정장 대여", "45,000"),), title="[신용승인]", brn=BRN):
    words = [
        wd(30, 3, title, 14), wd(28, 5, "카드 매출전표", 16),
        wd(10, 8, "가맹점명"), wd(30, 8, "한빛정장대여", 14),
        wd(10, 10, "사업자번호"), wd(30, 10, brn, 16),
        wd(10, 12, "거래일시"), wd(30, 12, "26/03/15"), wd(40, 12, "14:20"),
        wd(10, 14, "카드번호"), wd(30, 14, "9410-12**-****-3456", 20),
        wd(10, 16, "승인번호"), wd(30, 16, "12345678"),
    ]
    y = 20
    for name, amount in items:
        words += [wd(10, y, name, 12), wd(60, y, amount)]
        y += 2
    total = sum(int(amount.replace(",", "")) for _, amount in items)
    supply = round(total / 1.1)
    words += [wd(10, y + 2, "공급가액"), wd(60, y + 2, f"{supply:,}"),
              wd(10, y + 4, "부가세"), wd(60, y + 4, f"{total - supply:,}"),
              wd(10, y + 6, "합계금액"), wd(60, y + 6, f"{total:,}원")]
    return words


def test_card_slip_reads_total_date_store_and_number():
    result = run(card_slip_words())
    assert result.detected_type == DocType.RECEIPT
    got = values(result)
    assert got["결제금액"] == "45000"
    assert got["결제일"] == date(2026, 3, 15)  # 두 자리 연도 '26/03/15'
    assert got["상호"] == "한빛정장대여"
    assert got["사업자등록번호"] == BRN
    assert got["결제수단"] == "카드"
    assert (got["공급가액"], got["부가세"]) == ("40909", "4091")
    assert all(checks(result).values())
    assert result.fields["결제금액"].confidence == 1.0
    assert result.fields["결제금액"].bbox is not None
    assert result.warnings == []


def test_cash_receipt_prefers_total_over_cash_given():
    result = run([
        wd(40, 3, "영 수 증", 20), wd(10, 8, "상호:"), wd(20, 8, "새솔양복점", 12),
        wd(10, 10, "일자: 2026년 3월 15일", 30),
        wd(10, 14, "합 계"), wd(60, 14, "45,000"),
        wd(10, 16, "받은금액"), wd(60, 16, "50,000"),
        wd(10, 18, "거스름돈"), wd(60, 18, "5,000"),
    ])
    got = values(result)
    assert got["결제금액"] == "45000"
    assert got["결제일"] == date(2026, 3, 15)
    assert got["상호"] == "새솔양복점"


def test_label_and_value_read_as_one_word():
    result = run([wd(40, 3, "영수증"), wd(10, 8, "합계금액:45,000원", 30),
                  wd(10, 10, "결제일시:2026.03.15", 30), wd(45, 10, "14:20")])
    got = values(result)
    assert got["결제금액"] == "45000"
    assert got["결제일"] == date(2026, 3, 15)


def test_value_below_label_on_payment_screen():
    result = run([
        wd(10, 5, "결제가 완료되었습니다", 30),
        wd(10, 12, "결제일시"), wd(40, 12, "2026.03.15 14:20", 20),
        wd(10, 15, "상품명"), wd(40, 15, "면접 정장 대여", 20),
        wd(10, 18, "결제수단"), wd(40, 18, "신용카드(일시불)", 20),
        wd(10, 22, "결제금액"), wd(10, 24.5, "45,000원", 12),
        wd(10, 28, "판매자"), wd(40, 28, "미래정장", 12),
        wd(10, 31, "사업자등록번호", 16), wd(40, 31, BRN, 16),
    ])
    got = values(result)
    assert result.detected_type == DocType.RECEIPT
    assert got["결제금액"] == "45000"
    assert result.fields["결제금액"].raw_text == "45,000원"
    assert got["상호"] == "미래정장"
    assert got["결제수단"] == "카드"


def test_transfer_confirmation_reads_payee_and_amount():
    result = run([
        wd(35, 3, "이체확인증", 14), wd(10, 8, "이체일시"), wd(40, 8, "2026-03-12 10:05", 20),
        wd(10, 10, "받는분"), wd(40, 10, "다온사진관", 12),
        wd(10, 12, "이체금액"), wd(40, 12, "20,000원"), wd(10, 14, "수수료"), wd(40, 14, "0원"),
    ])
    got = values(result)
    assert got["결제금액"] == "20000"
    assert got["결제일"] == date(2026, 3, 12)
    assert got["받는분"] == "다온사진관"
    assert got["결제수단"] == "계좌이체"


def test_registration_confirmation_is_not_a_receipt():
    result = run([wd(30, 3, "원서접수확인서", 20), wd(10, 8, "종목명"), wd(30, 8, "정보처리기능사", 16),
                  wd(10, 10, "응시수수료"), wd(30, 10, "19,400원")])
    assert result.detected_type == DocType.UNKNOWN
    assert not checks(result)["document_type"]
    assert any("접수확인서" in warning for warning in result.warnings)


def test_several_items_flag_bulk_payment():
    result = run(card_slip_words(items=(("정보처리기능사 필기", "19,400"), ("컴퓨터활용능력 2급", "19,000"))))
    assert values(result)["품목수"] == 2
    assert not checks(result)["single_item"]
    assert any("품목이 여러 개" in warning for warning in result.warnings)


def test_cancelled_slip_is_flagged():
    result = run(card_slip_words(title="[승인취소]"))
    assert not checks(result)["not_cancelled"]
    assert any("취소" in warning for warning in result.warnings)


def test_wrong_check_digit_fails_number_validation():
    result = run(card_slip_words(brn="123-45-67890"))
    assert not checks(result)["brn_checksum"]
    assert result.fields["사업자등록번호"].confidence < 1.0
    assert any("검증숫자" in warning for warning in result.warnings)


def test_supply_and_vat_mismatch_lowers_amount_confidence():
    words = card_slip_words()
    next(word for word in words if word.text == "40,909").text = "40,000"
    result = run(words)
    assert not checks(result)["supply_plus_vat_matches"]
    assert result.fields["결제금액"].confidence < 1.0


def test_two_different_totals_are_a_conflict():
    result = run([wd(40, 3, "영수증"), wd(10, 8, "합계"), wd(60, 8, "45,000"),
                  wd(10, 10, "결제금액"), wd(60, 10, "90,000"), wd(10, 12, "결제일"), wd(60, 12, "2026.03.15")])
    assert not checks(result)["single_total"]


def test_unlabeled_single_date_is_used_with_warning():
    result = run([wd(40, 3, "영수증"), wd(10, 6, "2026.03.15"), wd(10, 8, "합계"), wd(60, 8, "45,000")])
    assert values(result)["결제일"] == date(2026, 3, 15)
    assert result.fields["결제일"].confidence < 1.0
    assert any("라벨이 없어" in warning for warning in result.warnings)


def test_missing_amount_is_not_filled():
    result = run([wd(40, 3, "영수증"), wd(10, 8, "결제일"), wd(30, 8, "2026.03.15")])
    assert "결제금액" not in result.fields
    assert not checks(result)["amount_found"]
    assert "결제금액" in result.diagnostics


def test_amount_and_number_parsers():
    assert job.parse_amount("2026.03.15 14:20 45,000원") == 45000
    assert job.parse_amount("45.000") == 45000  # OCR이 쉼표를 마침표로 읽은 경우
    assert job.parse_amount("0원") is None
    assert job.parse_date("26/03/15 14:20", short_year=True) == date(2026, 3, 15)
    assert job.parse_date("2026.09.2112:02") == date(2026, 9, 21)  # OCR이 날짜·시각을 붙여 읽은 경우
    assert job.parse_date("26/05/0409:31", short_year=True) == date(2026, 5, 4)
    assert job.parse_amount("2026.09.2112:02 45,000원") == 45000
    assert job.parse_date("26/03/15") is None  # 라벨 없는 두 자리 연도는 쓰지 않는다
    assert job.brn_is_valid(BRN) and not job.brn_is_valid("123-45-67890")
    assert job.parse_brn("사업자번호 1234567891") == BRN

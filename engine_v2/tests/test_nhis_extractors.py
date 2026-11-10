"""건강보험 추출기 테스트. 모든 이름·숫자·좌표는 가상 값이다."""

from datetime import date

from ..extractors import nhis_acquisition_loss, nhis_payment
from ..pipeline.ocr import OcrResult, OcrWord
from ..pipeline.preprocess import PageImage, PageSource

W, H = 1000, 1400


def wd(x: float, y: float, text: str, width: float = 8) -> OcrWord:
    return OcrWord(text, 0.99, (x / 100 * W, y / 100 * H,
                                (x + width) / 100 * W, (y + 0.8) / 100 * H))


def page(words: list[OcrWord], no: int = 0):
    image = PageImage(page=no, source=PageSource.EMBEDDED, page_size_pt=(595, 842), png=b"",
                      pixel_size=(W, H), dpi=250)
    return image, OcrResult("synthetic", words)


def person_header(title: str, name: str = "김전북", issue: str = "2026.11.10") -> list[OcrWord]:
    return [wd(10, 4, title, 35), wd(10, 10, "성명"), wd(20, 10, name),
            wd(10, 13, "생년월일"), wd(25, 13, "1999.01.01", 12),
            wd(10, 16, "발급일"), wd(25, 16, issue, 12)]


def payment_pages(*, missing: set[str] = set(), separate_care: bool = False,
                  paid_diff: bool = True, formats: tuple[str, str, str] = ("2025.10", "2025-11", "2025년 12월")):
    words = person_header("건강보험료 납부확인서") + [wd(10, 24, "가입구분"), wd(25, 24, "직장가입자")]
    words.extend([wd(10, 30, "년월")])
    if separate_care:
        words.extend([wd(30, 30, "건강보험료"), wd(48, 30, "고지금액"),
                      wd(60, 30, "장기요양보험료"), wd(72, 30, "고지금액"), wd(88, 30, "납부금액")])
    else:
        words.extend([wd(40, 30, "고지"), wd(47, 30, "금액"), wd(82, 30, "납부금액")])
    values = (("2025-10", 100_000, 20_000, 10_000),
              ("2025-11", 110_000, 22_000, 11_000),
              ("2025-12", 120_000, 24_000, 12_000))
    y = 34
    for display, (month, billed, care, paid) in zip(formats, values):
        if month in missing:
            continue
        words.append(wd(10, y, display, 12))
        if separate_care:
            words.extend([wd(49, y, f"{billed:,}"), wd(73, y, f"{care:,}"), wd(89, y, f"{paid:,}")])
        else:
            words.extend([wd(50, y, f"{billed:,}"), wd(83, y, f"{paid if paid_diff else billed:,}")])
        y += 2.2
    words.extend([wd(10, y, "합계"), wd(50, y, "330,000")])
    return [page(words)]


def test_payment_uses_billed_amounts_and_supported_month_formats():
    result = nhis_payment.extract(payment_pages())
    assert result.detected_type.value == "nhis_payment"
    assert result.fields["성명"].value == "김전북"
    assert result.fields["생년월일"].value == "1999-01-01"
    assert result.fields["건강보험료"].value == "110000"
    assert result.fields["고지월"].value == "2025-10,2025-11,2025-12"
    assert result.fields["가입구분"].value == "직장"
    assert all(v.passed for v in result.validations), result.validations
    assert result.fields["건강보험료"].bbox is not None


def test_payment_accepts_all_month_formats_and_wrapped_headers():
    format_sets = [
        ("2025.10", "2025-11", "2025년 12월"),
        ("2025. 10.", "202511", "2025-12"),
    ]
    for formats in format_sets:
        result = nhis_payment.extract(payment_pages(formats=formats))
        assert result.fields["건강보험료"].value == "110000"

    # 열 제목이 두 줄로 나뉜 경우에도 열 이름으로 고지·납부를 구별한다.
    words = person_header("건강보험료 납부확인서")
    words.extend([wd(10, 30, "년"), wd(10, 32, "월"), wd(42, 30, "고지"),
                  wd(42, 32, "금액"), wd(82, 30, "납부금액")])
    for i, (month, billed, paid) in enumerate((("202510", 100000, 90000),
                                               ("2025. 11.", 110000, 100000),
                                               ("2025년 12월", 120000, 110000))):
        y = 36 + i * 2
        words.extend([wd(10, y, month, 12), wd(50, y, f"{billed:,}"), wd(83, y, f"{paid:,}")])
    wrapped = nhis_payment.extract([page(words)])
    assert wrapped.fields["건강보험료"].value == "110000"

    spaced_money = payment_pages()
    for word in spaced_money[0][1].words:
        if word.text == "100,000":
            word.text = "100, 000원"
            break
    result = nhis_payment.extract(spaced_money)
    assert result.fields["건강보험료"].value == "110000"


def test_common_date_parser_accepts_requested_formats():
    from ..extractors.nhis_common import parse_date

    for text in ("2025.10.01", "2025-10-01", "2025년 10월 1일", "20251001"):
        assert parse_date(text) == date(2025, 10, 1)


def test_layout_output_masks_all_values(capsys):
    from ..tools.extract_check import _layout

    pages = payment_pages()
    _layout("nhis_payment", pages)
    output = capsys.readouterr().out
    assert "###" in output
    for private_value in ("김전북", "1999.01.01", "100,000", "90,000"):
        assert private_value not in output


def test_payment_missing_month_leaves_average_empty():
    result = nhis_payment.extract(payment_pages(missing={"2025-11"}))
    assert "건강보험료" not in result.fields
    assert result.fields["고지월"].value == "2025-10,2025-12"
    assert any("찾지 못한 달" in warning for warning in result.warnings)


def test_payment_checks_names_across_pages():
    first = payment_pages()[0]
    second = page(person_header("건강보험료 납부확인서", name="이익산"), no=1)
    result = nhis_payment.extract([first, second])
    assert not next(v for v in result.validations if v.name == "page_names_match").passed
    assert any("쪽마다 성명" in warning for warning in result.warnings)


def test_payment_separates_long_term_care_amount():
    result = nhis_payment.extract(payment_pages(separate_care=True))
    assert result.fields["건강보험료"].value == "110000"
    assert result.fields["장기요양보험료"].value == "22000"


def test_payment_ambiguous_combined_total_is_not_used():
    words = person_header("건강보험료 납부확인서") + [wd(10, 30, "년월"), wd(40, 30, "장기요양보험료 합계"),
        wd(50, 34, "2025.10"), wd(70, 34, "120,000"), wd(50, 36, "2025.11"), wd(70, 36, "132,000"),
        wd(50, 38, "2025.12"), wd(70, 38, "144,000")]
    result = nhis_payment.extract([page(words)])
    assert "건강보험료" not in result.fields
    assert any("합계만" in warning for warning in result.warnings)


def test_payment_rejects_zero_or_negative_amounts():
    pages = payment_pages()
    for word in pages[0][1].words:
        if word.text == "100,000":
            word.text = "0"
    result = nhis_payment.extract(pages)
    assert "건강보험료" not in result.fields
    assert any("0 또는 음수" in warning for warning in result.warnings)


def test_payment_does_not_guess_when_paid_column_heading_is_missing():
    pages = payment_pages()
    pages[0][1].words[:] = [word for word in pages[0][1].words if word.text != "납부금액"]
    result = nhis_payment.extract(pages)
    assert "건강보험료" not in result.fields
    assert result.diagnostics["건강보험료"] == "고지금액 후보 2개(열 구분 실패)"


def acquisition_pages(*, name2: str | None = None, acquired="2018.01.01", lost="", period=True):
    def one(name, no=0):
        words = person_header("건강보험 자격득실확인서", name=name)
        words.extend([wd(10, 24, "조회기간")])
        if period:
            words.extend([wd(25, 24, "2020.01.01"), wd(42, 24, "~"), wd(47, 24, "2026.11.10")])
        words.extend([wd(8, 30, "가입자구분"), wd(30, 30, "자격취득일"),
                      wd(52, 30, "자격상실일"), wd(75, 30, "사업장명칭")])
        words.extend([wd(8, 34, "직장가입자"), wd(30, 34, acquired, 12)])
        if lost:
            words.append(wd(52, 34, lost, 12))
        words.append(wd(75, 34, "가상사업장"))
        return page(words, no)
    pages = [one("김전북")]
    if name2:
        pages.append(one(name2, 1))
    return pages


def test_acquisition_loss_current_job_and_recent_five_years():
    result = nhis_acquisition_loss.extract(acquisition_pages())
    assert result.fields["취득일"].value == "2018-01-01"
    assert result.fields["변동내역"].value == "최근 5년 포함"
    assert result.fields["취득일"].bbox is not None
    assert all(v.passed for v in result.validations), result.validations
    assert "가상사업장" not in str(result.warnings)


def test_acquisition_loss_wrapped_column_headings_and_compact_dates():
    words = person_header("건강보험 자격득실확인서", issue="20261110")
    words.extend([wd(10, 30, "가입자구분"), wd(32, 29, "자격취득"),
                  wd(32, 31, "일"), wd(55, 29, "자격상실"), wd(55, 31, "일"),
                  wd(10, 35, "직장가입자"), wd(32, 35, "20180101", 12)])
    result = nhis_acquisition_loss.extract([page(words)])
    assert result.fields["발급일"].value == "2026-11-10"
    assert result.fields["취득일"].value == "2018-01-01"


def test_acquisition_loss_five_years_not_covered():
    result = nhis_acquisition_loss.extract(acquisition_pages(acquired="2024-02-01", lost="2025-02-01", period=False))
    assert result.fields["변동내역"].value == "최근 5년 미포함"
    assert "취득일" not in result.fields


def test_acquisition_loss_rejects_reversed_dates_and_page_name_mismatch():
    result = nhis_acquisition_loss.extract(acquisition_pages(name2="이익산", acquired="2025-01-01", lost="2024-01-01"))
    assert not next(v for v in result.validations if v.name == "acquisition_before_loss").passed
    assert not next(v for v in result.validations if v.name == "page_names_match").passed
    assert any("순서" in warning for warning in result.warnings)

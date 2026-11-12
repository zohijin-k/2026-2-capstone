"""Synthetic continuation-page identity and confirmation-number regressions."""

from engine_v2.extractors import nhis_acquisition_loss
from engine_v2.pipeline.ocr import OcrResult, OcrWord
from engine_v2.pipeline.preprocess import PageImage, PageSource

W, H = 1000, 1400


def _word(x, y, text, width=10):
    return OcrWord(text, 0.99, (x / 100 * W, y / 100 * H,
                                (x + width) / 100 * W, (y + 0.8) / 100 * H))


def _page(no, *, identity=True, name="가상가입자", birth="1984.02.03",
          confirmation="7310-2468-1357-9024", labeled_issue=False):
    words = [_word(5, 4, "건강보험 자격득실확인서", 35),
             _word(8, 7, "문서확인번호"), _word(24, 7, confirmation, 25)]
    if identity:
        rrn_prefix = birth.replace(".", "")
        words += [_word(8, 10, "성명"), _word(18, 10, name),
                  _word(8, 13, "주민등록번호"), _word(26, 13, f"{rrn_prefix}-3******", 25)]
    if labeled_issue:
        words += [_word(8, 16, "발급일"), _word(18, 16, "2031.07.08", 15)]
    words += [_word(8, 22, "가입자구분"), _word(32, 22, "자격취득일"),
              _word(55, 22, "자격상실일"), _word(76, 22, "사업장명칭")]
    acquired = "2024.01.02" if no == 0 else "2025.03.04"
    words += [_word(8, 27, "직장가입자"), _word(32, 27, acquired, 12),
              _word(76, 27, "가상회사", 12)]
    if no == 1:
        words += [_word(8, 70, "위와 같이 확인합니다", 40),
                  _word(42, 73, "2031 년 7 월 8 일", 25),
                  _word(35, 76, "국민건강보험공단 이사장", 40)]
    image = PageImage(page=no, source=PageSource.EMBEDDED, page_size_pt=(595, 842), png=b"",
                      pixel_size=(W, H), dpi=250)
    return image, OcrResult("synthetic", words)


def _validation(result, name):
    return next(item.passed for item in result.validations if item.name == name)


def test_headerless_continuation_compares_only_observed_identity_and_document_number():
    result = nhis_acquisition_loss.extract([
        _page(0, labeled_issue=True), _page(1, identity=False),
    ])

    assert _validation(result, "성명_consistent")
    assert _validation(result, "생년월일_consistent")
    assert _validation(result, "page_names_match")
    assert _validation(result, "document_confirmation_number_consistent")


def test_conflicting_identity_or_document_number_fails():
    changed_identity = nhis_acquisition_loss.extract([
        _page(0, labeled_issue=True), _page(1, name="가상다른", birth="1985.04.06"),
    ])
    assert not _validation(changed_identity, "성명_consistent")
    assert not _validation(changed_identity, "생년월일_consistent")
    assert not _validation(changed_identity, "page_names_match")

    changed_number = nhis_acquisition_loss.extract([
        _page(0, labeled_issue=True), _page(1, identity=False, confirmation="8421-3579-2468-0135"),
    ])
    assert not _validation(changed_number, "document_confirmation_number_consistent")
    assert "문서확인번호" not in changed_number.fields


def test_first_page_identity_is_required_and_single_page_label_behavior_is_preserved():
    missing_first = nhis_acquisition_loss.extract([
        _page(0, identity=False, labeled_issue=True), _page(1, identity=False),
    ])
    assert not _validation(missing_first, "성명_consistent")
    assert not _validation(missing_first, "생년월일_consistent")
    assert not _validation(missing_first, "page_names_match")

    single = nhis_acquisition_loss.extract([_page(0, labeled_issue=True)])
    assert _validation(single, "성명_consistent")
    assert _validation(single, "생년월일_consistent")
    assert _validation(single, "page_names_match")
    assert single.fields["발급일"].value == "2031-07-08"

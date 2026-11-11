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


def test_page_marker_accepts_joined_spaced_and_split_tokens():
    from ..extractors.insurance_4 import _page_marker
    from ..pipeline.layout import normalize

    for tokens in (("1/1",), ("1", "/", "1"), ("1", " / ", "1")):
        words = [wd(85 + index * 2, 29, token) for index, token in enumerate(tokens)]
        normalized = normalize(words, 0, (W, H))
        from ..extractors.nhis_common import group_lines
        assert _page_marker(group_lines(normalized)), tokens
    split_lines = normalize([wd(85, 28, "1"), wd(85, 29.2, "/"), wd(85, 30.4, "1")],
                            0, (W, H))
    assert _page_marker(group_lines(split_lines))
    words = [wd(85, 29, "1"), wd(87, 29, "/"), wd(89, 29, "2")]
    assert not _page_marker(group_lines(normalize(words, 0, (W, H))))


def test_blank_receipt_markers_are_not_dates_and_issue_timestamp_formats_work():
    for marker in ("-", "( - )", "(-)", ""):
        words = employed_words()
        for word in words:
            if word.text == "(2023.01.02)":
                word.text = marker
                break
        result = insurance_4.extract([page(words)], today=date(2026, 11, 11))
        checks = {item.name: item.passed for item in result.validations}
        assert checks["date_formats"], marker

    for issue in ("2026.11.10 10:20", "2026-11-10 10:20"):
        words = synthetic_words()
        next(word for word in words if word.text == "2026.11.10 10:20").text = issue
        result = insurance_4.extract([page(words)], today=date(2026, 11, 11))
        checks = {item.name: item.passed for item in result.validations}
        assert checks["issue_not_future"], issue


def test_received_dash_is_normalized_to_empty_in_gt_comparison():
    from ..tools.extract_check import _expected, _row_mismatch_reason

    gt = {"rows": [{"insurance": "건강보험", "status": "가입", "received": "-"}]}
    expected = json.loads(_expected("insurance_4", gt)["가입내역"])
    assert expected[0]["신고접수일"] == ""
    actual = [dict(expected[0], 신고접수일="9999-99-99")]
    reason = _row_mismatch_reason(actual, expected)
    assert reason == "건강보험 행 신고접수일: 추출=날짜, 정답=비어 있음"


def test_list_mismatch_explains_safe_cell_shape_without_values():
    from ..tools.extract_check import _row_mismatch_reason

    actual = [{"보험": "건강보험", "신고접수일": ""}]
    expected = [{"보험": "건강보험", "신고접수일": "9999-99-99"}]
    reason = _row_mismatch_reason(actual, expected)
    assert reason == "건강보험 행 신고접수일: 추출=비어 있음, 정답=날짜"
    assert "9999" not in reason


def test_extract_check_output_keeps_fixed_explanation_and_masks_values(monkeypatch, capsys):
    from pathlib import Path
    from types import SimpleNamespace

    from ..tools import extract_check

    pages = [page(synthetic_words())]
    monkeypatch.setattr("engine_v2.engine._load_pages", lambda _doc, _engine: pages)
    gt = {"rows": [{"insurance": "건강보험", "status": "가입",
                    "name": "추출안되는개인값", "received": "9999-99-99"}]}
    extract_check._run_nhis(SimpleNamespace(file=Path("synthetic.pdf"), engine="applevision",
                                            doc="insurance_4", layout=False), gt)
    output = capsys.readouterr().out
    assert "행 1 보험 이름: 추출=국민연금, 정답=건강보험" in output
    assert "정답과 일치" in output
    for private in ("김전북", "가상회사", "추출안되는개인값", "9999-99-99"):
        assert private not in output


def test_nhis_extract_check_outputs_keep_fixed_reasons_and_hide_values(monkeypatch, capsys):
    from pathlib import Path
    from types import SimpleNamespace

    from ..extractors import nhis_acquisition_loss, nhis_payment
    from ..tools import extract_check

    monkeypatch.setattr("engine_v2.engine._load_pages", lambda _doc, _engine: [])
    synthetic_secret = "합성개인값"
    result = SimpleNamespace(fields={"성명": SimpleNamespace(value=synthetic_secret)},
                             validations=[], diagnostics={})
    monkeypatch.setattr(nhis_payment, "extract", lambda _pages: result)
    monkeypatch.setattr(nhis_acquisition_loss, "extract", lambda _pages: result)
    for doc in ("nhis_payment", "nhis_acquisition_loss"):
        extract_check._run_nhis(SimpleNamespace(file=Path("synthetic.pdf"), engine="applevision",
                                                doc=doc, layout=False), {})
    output = capsys.readouterr().out
    assert output.count("추출됨 (정답 비교 안 함)") == 2
    assert synthetic_secret not in output


def test_requires_parseable_parenthesized_receipt_date():
    words = employed_words()
    next(word for word in words if word.text == "(2023.01.02)").text = "(2023.99.99)"
    result = insurance_4.extract([page(words)], today=date(2026, 11, 11))
    checks = {item.name: item.passed for item in result.validations}
    assert not checks["date_formats"]

"""Opt-in diagnostics expose failed check identifiers, never values or raw text."""
from copy import deepcopy
from datetime import date

from PIL import Image
import pytest

import demo.backend.ocr as chain
from demo.backend.ocr.base import OcrResult
from demo.backend.rules.doc_types import DocType
from demo.backend.tests.test_verify_upload import SECRET, assert_safe, no_db, snapshot
from demo.backend.tools import verify_upload as tool


@pytest.mark.parametrize("name", [
    "monthly_rows_found", "monthly_amounts_numeric", "months_continuous",
    "monthly_total_matches", "paid_total_matches", "payment_billing_absence_certain",
    "payment_column_1_sum", "payment_column_8_sum", "daily_0_table_headers",
    "daily_1_applicant_identity", "daily_99_rows_in_period", "daily_selection_readable",
    "history_numbers_sequential", "성명_consistent", "문서확인번호_consistent",
    "발급일_required", "business_사업자등록번호_read",
])
def test_reviewed_validation_identifiers_and_bounded_families(name):
    assert tool._failed_validations("nhis_payment", {"판독검증실패": name}) == [
        f"failed_validation: nhis_payment {name}",
    ]


@pytest.mark.parametrize("raw", [None, [], {}, 123, False, "", " , , "])
def test_missing_or_malformed_failed_metadata_emits_no_names(raw):
    assert tool._failed_validations("nhis_payment", {"판독검증실패": raw}) == []


@pytest.mark.parametrize("unknown", [
    SECRET, "1990-01-01", "1234567890123", "monthly_rows_found\n" + SECRET,
    "monthly_rows_found: 123,000", "daily_100_table_headers", "daily_19900101_table_rows",
    "payment_column_9_sum", "business_가짜성명_read", "unreviewed_future_validation",
])
def test_unknown_or_value_bearing_names_use_fixed_marker(unknown):
    source = {"판독검증실패": f" {unknown}, monthly_rows_found, {unknown}, monthly_rows_found "}
    before = deepcopy(source)
    output = "\n".join(tool._failed_validations("nhis_payment", source))
    assert output == ("failed_validation: nhis_payment UNKNOWN_VALIDATION\n"
                      "failed_validation: nhis_payment monthly_rows_found")
    assert source == before
    assert_safe(output)


def authored_adapter(monkeypatch, failures):
    class AuthoredAdapter:
        name = "fixture"

        def read(self, file_path, expected):
            fields = {
                "성명": SECRET, "생년월일": "1990-01-01", "발급일": "2026-03-03",
                "판독검증": "monthly_total_matches: 가짜 성공 검증 원문 1234567890",
                "판독경고": "가짜 경고 원문과 금액 123,000",
            }
            if expected in failures:
                fields["판독검증실패"] = failures[expected]
            return OcrResult(
                expected, .9, image_quality=.9, issue_date=date(2026, 3, 3),
                fields=fields, tier="fixture", engine="fixture",
            )

    monkeypatch.setattr(chain, "CHAIN", [AuthoredAdapter()])


def test_single_option_is_opt_in_deduplicated_and_value_free(tmp_path, monkeypatch, capfd, no_db):
    path = tmp_path / "FAKE.png"
    Image.new("RGB", (1800, 2400), "white").save(path)
    authored_adapter(monkeypatch, {
        DocType.RESIDENT_ABSTRACT: f"months_continuous, {SECRET}, months_continuous",
    })
    args = ["--slot", "resident_abstract", str(path)]
    before = snapshot(tmp_path)
    assert tool.main(args) == 0
    default = capfd.readouterr()
    assert default.err == ""
    assert "failed_validation:" not in default.out
    assert tool.main([*args, "--validations"]) == 0
    diagnosed = capfd.readouterr()
    assert diagnosed.err == ""
    names = [line for line in diagnosed.out.splitlines() if line.startswith("failed_validation:")]
    assert names == [
        "failed_validation: resident_abstract months_continuous",
        "failed_validation: resident_abstract UNKNOWN_VALIDATION",
    ]
    assert "monthly_total_matches" not in diagnosed.out
    assert "123,000" not in diagnosed.out and "가짜 성공" not in diagnosed.out
    assert_safe(diagnosed.out)
    assert snapshot(tmp_path) == before


def test_income_option_associates_failed_names_with_each_document(tmp_path, monkeypatch, capfd, no_db):
    paths = [tmp_path / f"FAKE-{index}.png" for index in range(3)]
    for path in paths:
        Image.new("RGB", (1800, 2400), "white").save(path)
    authored_adapter(monkeypatch, {
        DocType.NHIS_PAYMENT: "monthly_rows_found",
        DocType.NHIS_QUALIFICATION: "household_rows_read",
        DocType.NHIS_ACQUISITION_LOSS: "history_dates_read",
    })
    before = snapshot(tmp_path)
    assert tool.main(["--validations", "--income", *(str(path) for path in paths)]) == 0
    captured = capfd.readouterr()
    assert captured.err == ""
    assert [line for line in captured.out.splitlines() if line.startswith("failed_validation:")] == [
        "failed_validation: nhis_payment monthly_rows_found",
        "failed_validation: nhis_qualification household_rows_read",
        "failed_validation: nhis_acquisition_loss history_dates_read",
    ]
    assert "monthly_total_matches" not in captured.out
    assert_safe(captured.out)
    assert snapshot(tmp_path) == before


def test_validation_mode_rejects_slots_list_without_echoing_arguments(capfd, no_db):
    assert tool.main(["--slots-list", "--validations"]) == 2
    captured = capfd.readouterr()
    assert captured.err == ""
    assert captured.out == "error: ARGUMENT_ERROR\n"

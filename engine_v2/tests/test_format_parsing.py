"""Synthetic regressions for typed parsing; existing/main tests stay untouched."""
from copy import deepcopy
from datetime import date
import json

import pytest

from engine_v2.extractors import insurance_4, nhis_common, nhis_payment, nhis_acquisition_loss, resident_abstract
from engine_v2.extractors.format_text import DASH_CHARACTERS, normalize_format_text
from engine_v2.pipeline.layout import normalize, group_lines
from engine_v2.tools import extract_diag
from .test_insurance_4 import page, synthetic_words, wd
from .test_nhis_extractors import payment_pages, month_only_payment_pages, acquisition_pages
from .test_resident_abstract import build


@pytest.mark.parametrize("dash", DASH_CHARACTERS)
def test_typed_dash_allowlist_and_original_evidence(dash):
    words = synthetic_words()
    issue = next(w for w in words if w.text == "2026.11.10 10:20")
    issue.text = f"2026{dash}11{dash}10 10:20"
    identifier = next(w for w in words if w.text == "990101-1123456")
    identifier.text = identifier.text.replace("-", dash)
    raw_issue = issue.text
    result = insurance_4.extract([page(words)], today=date(2026, 11, 11))
    assert result.fields["발급일"].value == date(2026, 11, 10)
    assert result.fields["생년월일"].value == date(1999, 1, 1)
    assert all(v.passed for v in result.validations)
    assert issue.text == raw_issue
    assert identifier.text == ""  # Existing immediate identifier-tail disposal.
    assert "1123456" not in repr(result)
    text = f"2026{dash}11{dash}10"
    assert nhis_common.parse_date(text) == date(2026, 11, 10)
    assert normalize_format_text(text) == "2026-11-10"
    assert len(normalize_format_text(text)) == len(text)


def test_date_separator_grammars_and_source_spans_are_preserved():
    # The resident history parser still excludes slashes; NHIS already allowed them.
    assert resident_abstract.ISO_DATE.fullmatch(normalize_format_text("2026/11/10")) is None
    assert nhis_common.parse_date("2026/11/10") == date(2026, 11, 10)
    for text in ("2026／11／10", "2026．11．10", "2026·11·10", "2026~11~10", "2026_11_10"):
        assert nhis_common.parse_date(text) is None
        assert normalize_format_text(text) == text
    assert nhis_common.parse_date("2026−02−30") is None
    words = normalize([wd(10, 10, "라벨"), wd(30, 10, "2026–11–10")], 0, (1000, 1400))
    hits = nhis_common.dates_in_line(words)
    assert hits[0][1] == [words[1]]
    assert hits[0][1][0].text == "2026–11–10"


@pytest.mark.parametrize("stamp_y", (3, 20.8, 21))
def test_stamp_date_and_time_cannot_displace_right_cell(stamp_y):
    words = synthetic_words() + [wd(2, stamp_y, "2026/11/09", 25), wd(2, stamp_y + 1, "09:30:12 KST", 25)]
    # An oversized stamp near the row must not widen label row tolerance.
    words.append(type(words[0])("2026/11/08", .99, (10, 1, 400, 590)))
    result = insurance_4.extract([page(words)], today=date(2026, 11, 11))
    assert result.fields["발급일"].value == date(2026, 11, 10)
    assert result.fields["발급일"].bbox.x0 > 400


@pytest.mark.parametrize("cell", ("", "깨진날짜", "2026-XX-10 10:20", "2026-02-30 10:20",
                                   "2026-11-10 10:20 2026-11-09"))
def test_empty_or_corrupt_cell_stays_absent_with_existing_failures(cell):
    words = synthetic_words() + [wd(2, 21, "2026/11/09", 25)]
    next(w for w in words if w.text == "2026.11.10 10:20").text = cell
    result = insurance_4.extract([page(words)], today=date(2026, 11, 11))
    assert "발급일" not in result.fields
    assert "발급일" in result.diagnostics
    checks = {v.name: v.passed for v in result.validations}
    assert not checks["발급일_consistent"]
    assert not checks["issue_not_future"]
    assert not checks["dates_not_after_issue"]
    assert any("담당자 확인" in w for w in result.warnings)


@pytest.mark.parametrize("label", ("발굽일시", "", "조회기간"))
def test_unrecognized_label_never_uses_any_other_date(label):
    words = synthetic_words() + [wd(2, 21, "2026/11/09", 25)]
    next(w for w in words if w.text == "발급일시").text = label
    result = insurance_4.extract([page(words)], today=date(2026, 11, 11))
    assert "발급일" not in result.fields
    assert not next(v for v in result.validations if v.name == "발급일_consistent").passed


@pytest.mark.parametrize("variant", ("split_label", "merged_region", "split_date", "space_colon"))
def test_label_and_cell_ocr_granularity(variant):
    words = [w for w in synthetic_words() if w.text not in ("발급일시", "2026.11.10 10:20")]
    if variant == "split_label":
        words += [wd(58, 21, "발급", 4), wd(62, 21, "일시", 4), wd(74, 21, "2026–11–10 10:20", 18)]
    elif variant == "merged_region":
        words += [wd(58, 21, "발급일시 : 2026−11−10 10:20", 36)]
    elif variant == "split_date":
        words += [wd(58, 21, "발급일시"), wd(74, 21, "2026", 4), wd(78, 21, "－", 1),
                  wd(79, 21, "11", 2), wd(81, 21, "－", 1), wd(82, 21, "10", 2), wd(85, 21, "10:20", 8)]
    else:
        words += [wd(58, 21, "발 급 일 시："), wd(74, 21, "2026.11.10 10:20", 18)]
    assert insurance_4.extract([page(words)]).fields["발급일"].value == date(2026, 11, 10)


def test_outside_header_below_cell_next_label_and_duplicate_labels_fail_closed():
    for variant in ("body", "below", "next_label", "duplicate"):
        words = synthetic_words()
        label = next(w for w in words if w.text == "발급일시")
        cell = next(w for w in words if w.text == "2026.11.10 10:20")
        if variant == "body":
            words.remove(label); words.remove(cell)
            words += [wd(58, 70, "발급일시"), wd(74, 70, "2026.11.10 10:20", 18)]
        elif variant == "below":
            words.remove(cell); words += [wd(74, 23, "2026.11.10 10:20", 18)]
        elif variant == "next_label":
            words += [wd(69, 21, "조회기간", 4)]
        else:
            words += [wd(58, 23, "발급일시"), wd(74, 23, "2026.11.10 10:20", 18)]
        assert "발급일" not in insurance_4.extract([page(words)]).fields


@pytest.mark.parametrize("dash", DASH_CHARACTERS)
def test_resident_identity_history_and_address_text(dash):
    pages = build()
    expected = resident_abstract.extract(deepcopy(pages), today=date(2026, 11, 11))
    for _, result in pages:
        for word in result.words:
            if resident_abstract.RRN.search(word.text) or resident_abstract.ISO_DATE.fullmatch(word.text):
                word.text = word.text.replace("-", dash)
    address = next(w for w in pages[0][1].words if "123-4" in w.text)
    address.text = address.text.replace("-", dash)
    originals = [[w.text for w in r.words] for _, r in pages]
    actual = resident_abstract.extract(pages, today=date(2026, 11, 11))
    for key in ("name", "birth_date", "issue_date", "address_history_count"):
        assert actual.fields[key].value == expected.fields[key].value
    assert address.text in actual.history[0].address
    assert [[w.text for w in r.words] for _, r in pages] == originals
    assert [(v.name, v.passed) for v in actual.validations] == [(v.name, v.passed) for v in expected.validations]


def test_name_and_address_characters_are_not_normalized():
    pages = build(name="김–전북")
    actual = resident_abstract.extract(pages)
    assert actual.fields["name"].value == "김–전북"
    assert normalize_format_text("010−1234－5678") == "010-1234-5678"


@pytest.mark.parametrize("dash", DASH_CHARACTERS)
def test_payment_months_and_nhis_header_share_typed_normalization(dash):
    pages = payment_pages(formats=tuple(f"2025{dash}{m}" for m in (10, 11, 12)))
    for word in pages[0][1].words:
        if word.text == "2026.11.10":
            word.text = f"2026{dash}11{dash}10"
    texts = [w.text for w in pages[0][1].words]
    result = nhis_payment.extract(pages)
    assert result.fields["발급일"].value == "2026-11-10"
    assert result.fields["건강보험료"].value == "110000"
    assert result.fields["고지월"].value == "2025-10,2025-11,2025-12"
    assert all(v.passed for v in result.validations)
    assert [w.text for w in pages[0][1].words] == texts


def test_nhis_selection_and_payment_confirmation_fallback_remain_independent(monkeypatch):
    def forbidden(*args):
        raise AssertionError("Insurance header selection must stay isolated")
    monkeypatch.setattr(insurance_4, "select_issue_date", forbidden)
    result = nhis_payment.extract(payment_pages())
    assert result.fields["발급일"].value == "2026-11-10"
    fallback = nhis_payment.extract(month_only_payment_pages((2025, 10), [10, 11, 12], issue_label=False))
    assert fallback.fields["발급일"].value == "2026-11-10"
    pages = payment_pages()
    header = nhis_common.header_for_page(*pages[0])
    assert header.issue == date(2026, 11, 10)


@pytest.mark.parametrize("stamp", ("2026–11–1010:20", "2026−11−10 10:20:30"))
def test_complete_timestamp_establishes_merged_day_time_boundary(stamp):
    words = synthetic_words()
    next(w for w in words if w.text == "2026.11.10 10:20").text = stamp
    assert insurance_4.extract([page(words)]).fields["발급일"].value == date(2026, 11, 10)


@pytest.mark.parametrize("dash", DASH_CHARACTERS)
def test_acquisition_history_and_query_period_use_common_date_parser(dash):
    pages = acquisition_pages()
    expected = nhis_acquisition_loss.extract(deepcopy(pages))
    for _, result in pages:
        for word in result.words:
            if nhis_common.parse_date(word.text):
                word.text = word.text.replace(".", dash)
    actual = nhis_acquisition_loss.extract(pages)
    assert {k: v.value for k, v in actual.fields.items()} == {k: v.value for k, v in expected.fields.items()}
    assert [(v.name, v.passed) for v in actual.validations] == [(v.name, v.passed) for v in expected.validations]


@pytest.mark.parametrize("kind,factory,digest", (
    (resident_abstract, build, "d898d96a4f77b693c2ac8952c255915f1da3056f5101db5464eed6349aa70c82"),
    (nhis_payment, payment_pages, "4977bffcd15208bbf93ff5a29138beb2b0cd60001ed178208bebb4cd90eb3d1a"),
    (nhis_payment, lambda: payment_pages(separate_care=True), "30faa6eb408c8e05c62c42f389300d51e85fa58502f635a43553ffcc93416235"),
    (nhis_payment, lambda: month_only_payment_pages((2025, 10), [10, 11, 12], issue_label=False),
     "b1c06951895a20db10e59a5004a31aef69e570f22d84a17bd35df58a02610caf"),
    (nhis_acquisition_loss, acquisition_pages, "3c28e899c79eaf224143958c212f8e2861f9dbf084debbbdef2a4c408b062236"),
))
def test_ascii_compatibility_against_main_snapshots(kind, factory, digest):
    """92eadc2 full fields/evidence/confidence/checks/warnings, synthetic only."""
    from dataclasses import asdict
    import hashlib
    result = kind.extract(factory(), today=date(2026, 11, 11))
    snapshot = {
        "fields": {k: v.model_dump(mode="json") for k, v in result.fields.items()},
        "validations": [asdict(v) for v in result.validations], "warnings": result.warnings,
        "type": result.detected_type.value, "type_confidence": result.type_confidence,
        "diagnostics": getattr(result, "diagnostics", {}),
    }
    if kind is nhis_acquisition_loss:
        # Assert the new additive contract, then retain the original digest
        # for every pre-existing field/evidence/confidence/check/warning.
        evidence = {"recent_five_years_covered": True, "coverage_basis": "query_period",
                    "coverage_years": 5, "period_label_present": True}
        for key in ("value", "raw_text"):
            history = json.loads(snapshot["fields"]["자격이력자료"][key])
            assert {name: history.pop(name) for name in evidence} == evidence
            snapshot["fields"]["자격이력자료"][key] = json.dumps(
                history, ensure_ascii=False, separators=(",", ":"))
    serialized = json.dumps(snapshot, sort_keys=True, ensure_ascii=False, default=str).encode()
    assert hashlib.sha256(serialized).hexdigest() == digest


def test_safe_diagnostic_literal_schema_and_no_values():
    words = synthetic_words() + [wd(2, 21, "2026/11/09", 25), wd(2, 22, "09:30:12 KST", 25)]
    next(w for w in words if w.text == "2026.11.10 10:20").text = "2026−11−10 10:20"
    report = extract_diag.diagnose_safe_issue([page(words)])
    assert set(report) == extract_diag.SAFE_ISSUE_KEYS
    assert set(report["separator_counts"]) == set(extract_diag.SEPARATOR_CLASSES.values())
    assert report["issue_label_found"] and report["right_cell_present"]
    assert report["right_cell_date_format"] and report["selected_via_label"]
    assert report["stamp_date_candidate_present"]
    assert report["separator_counts"]["MINUS_SIGN"] == 2
    serialized = json.dumps(report, ensure_ascii=False)
    for private in ("2026", "11/09", "09:30", "10:20", "김전북", "990101", "1123456", "1234-5678"):
        assert private not in serialized
    assert not any(key in serialized for key in ("bbox", "cell_text", "pixel_size", "filename"))


@pytest.mark.parametrize("variant", ("empty", "corrupt", "missing_label", "merged_timestamp"))
def test_safe_diagnostic_distinguishes_missing_and_invalid_evidence(variant):
    words = synthetic_words() + [wd(2, 21, "2026/11/09", 25)]
    cell = next(w for w in words if w.text == "2026.11.10 10:20")
    if variant == "empty":
        cell.text = ""
    elif variant == "corrupt":
        cell.text = "2026-XX-10"
    elif variant == "missing_label":
        next(w for w in words if w.text == "발급일시").text = "발굽일시"
    else:
        cell.text = "2026−11−1010:20"
    report = extract_diag.diagnose_safe_issue([page(words)])
    assert report["issue_label_found"] == (variant != "missing_label")
    assert report["right_cell_present"] == (variant in ("corrupt", "merged_timestamp"))
    assert report["right_cell_date_format"] == (variant == "merged_timestamp")
    assert report["selected_via_label"] == (variant == "merged_timestamp")
    assert report["stamp_date_candidate_present"]
    if variant == "merged_timestamp":
        assert report["header_date_candidate_count"] == 2
        assert report["separator_counts"]["MINUS_SIGN"] == 2


def test_safe_cli_suppresses_python_native_output_paths_and_truth(monkeypatch, capsys):
    import os
    pairs = [page(synthetic_words())]
    def raster(_path):
        print("SecretFilenameQX.pdf 2099-12-31")
        os.write(2, b"SecretNativeQX")
        return [pairs[0][0]]
    monkeypatch.setattr(extract_diag, "raster_pages", raster)
    monkeypatch.setattr(extract_diag, "run_ocr", lambda *a: pairs[0][1])
    assert extract_diag.main(["SecretFilenameQX.pdf", "--doc", "insurance_4", "--safe-issue"]) == 0
    output = capsys.readouterr()
    assert output.err == ""
    assert set(json.loads(output.out)) == extract_diag.SAFE_ISSUE_KEYS
    for private in ("SecretFilenameQX", "SecretNativeQX", "2099", "김전북", "2026.11.10"):
        assert private not in output.out
    with pytest.raises(SystemExit):
        extract_diag.main(["SecretFilenameQX.pdf", "--doc", "insurance_4", "--safe-issue", "--gt", "SecretTruthQX.json"])
    assert "SecretTruthQX" not in capsys.readouterr().err

"""Authored upload/CLI evidence for daily candidates and positional address dates."""
from datetime import date
import json

from PIL import Image
import pytest

from demo.backend.api.review import document_blockers
from demo.backend.rules.doc_check import check_document
from demo.backend.rules.eligibility_blockers import eligibility_blockers
from demo.backend.rules.identity import Identity
from demo.backend.rules.programs import DOUBLE_SAVINGS, PROGRAMS
from demo.backend.rules.required_docs import WorkCategory
from demo.backend.rules.work_continuity import assess_work
from demo.backend.tests.test_address_resolution_failures import convert, req
from demo.backend.tests.test_daily_work_uploads import text_pdf
from demo.backend.tests.test_followup_daily_reproduction import converted, document, requirement
from demo.backend.tests.test_verify_upload import (assert_safe, authored_recognition,
                                                   no_db, snapshot)
from demo.backend.tools import verify_upload as tool
from engine_v2.pipeline.ocr import OcrWord
from engine_v2.tests import fail_case_samples as base
from engine_v2.tests.followup_address_samples import sparse_dates
from engine_v2.tests.followup_daily_samples import daily_short_birth


@pytest.mark.parametrize("two_digit", [True, False])
def test_source_shaped_four_page_pdf_cli_rejects_missing_work_months(two_digit, tmp_path, monkeypatch, capfd, no_db):
    path = text_pdf(tmp_path / "FAKE-opaque.pdf", daily_short_birth(two_digit=two_digit))
    monkeypatch.setenv("ENGINE_V2_OCR", "off")
    before = snapshot(tmp_path)
    assert tool.main(["--slot", "work_proof", "--work-category", "지역가입자·피부양자",
                      "--self-identity", str(path)]) == 0
    output = capfd.readouterr()
    assert output.err == ""
    for expected in ("identity: O", "document_status: PASS", "work_status: NOT_MET",
                     "work_reason: WORK_CONTINUITY_NOT_MET", "blockers: O"):
        assert expected + "\n" in output.out
    assert_safe(output.out)
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("two_digit", [True, False])
@pytest.mark.parametrize("mismatch", ["birth", "name"])
def test_authenticated_identity_mismatch_preserves_existing_daily_rules(two_digit, mismatch):
    _, read = converted(daily_short_birth(two_digit=two_digit))
    identity = Identity("다른가짜명" if mismatch == "name" else base.NAME,
                        date(1991, 1, 1) if mismatch == "birth" else base.BIRTH)
    result = check_document(requirement(), read, identity=identity)
    assert result.status == ("NEEDS_REVIEW" if two_digit else "FAIL")
    assert ("IDENTITY_UNCERTAIN" if two_digit else "IDENTITY_MISMATCH") in result.codes
    program = PROGRAMS[DOUBLE_SAVINGS]
    work = assess_work(program, program.announcement_date, WorkCategory.LOCAL,
                       [document(read, result.status)], identity)
    assert work.status == "UNDETERMINED"
    assert "WORK_IDENTITY_UNCONFIRMED" in work.detail_codes


def test_short_year_copy_disagreement_still_prevents_work_rejection():
    pages = daily_short_birth()
    for word in pages[2][1].words:
        if word.text == "90년01월01일":
            word.text = "91년01월01일"
    extracted, read = converted(pages)
    assert extracted.structure_complete is False
    assert not json.loads(read.fields["일용근로내역자료"])["copies_consistent"]
    result = check_document(requirement(), read, identity=Identity(base.NAME, base.BIRTH))
    assert result.status == "NEEDS_REVIEW" and "REQUIRED_FIELD_UNREADABLE" in result.codes
    program = PROGRAMS[DOUBLE_SAVINGS]
    work = assess_work(program, program.announcement_date, WorkCategory.LOCAL,
                       [document(read, result.status)], Identity(base.NAME, base.BIRTH))
    assert work.status == "UNDETERMINED"
    assert not eligibility_blockers(program, {}, {"name": base.NAME, "birth": base.BIRTH.isoformat()},
                                    [document(read, result.status)], WorkCategory.LOCAL,
                                    {"announcement_date": program.announcement_date.isoformat()})


@pytest.mark.parametrize("variant", ["blank", "digit", "no-headers", "one-row", "dated"])
def test_sparse_address_document_and_actual_blocker_agree(variant, tmp_path):
    pages = sparse_dates(digit=variant == "digit", headers=variant != "no-headers",
                         rows=1 if variant == "one-row" else 3)
    if variant == "dated":
        pages[0][1].words += [OcrWord("2020-01-01", .95, (530,475,620,495)),
                             OcrWord("2020-01-02", .95, (640,475,740,495))]
    read = convert(pages)
    result = check_document(req(), read, file_format="jpg")
    assert read.image_quality < .6 and read.confidence == .4
    assert result.status == ("FAIL" if variant == "blank" else "NEEDS_REVIEW")
    assert ("MISSING_ADDRESS_DATES" in result.codes) == (variant == "blank")
    row = tool._row(req(), tmp_path / "FAKE.jpg", read, result)
    blockers = document_blockers([req()], [row])
    assert bool(blockers) == (variant == "blank")


def test_sparse_address_actual_image_cli_blocks_without_value_output(tmp_path, monkeypatch, capfd, no_db):
    pages = sparse_dates()
    path = tmp_path / "FAKE-opaque.png"
    Image.new("RGB", pages[0][0].pixel_size, "white").save(path)
    authored_recognition(monkeypatch, pages)
    before = snapshot(tmp_path)
    assert tool.main(["--slot", "resident_abstract", "--self-identity", str(path)]) == 0
    output = capfd.readouterr()
    assert output.err == ""
    assert "document_status: FAIL\n" in output.out
    assert "reason: MISSING_ADDRESS_DATES FAIL\n" in output.out
    assert "blockers: O\n" in output.out
    assert_safe(output.out)
    assert snapshot(tmp_path) == before

"""Synthetic-only CLI acceptance: shared upload, blockers and zero-value output."""
from copy import deepcopy
from datetime import date
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import sys

from PIL import Image
import pymupdf
import pytest

from demo.backend import models
from demo.backend.ocr import localocr
from demo.backend.ocr.base import OcrResult
from demo.backend.ocr.pdftext import PdfTextOcr
from demo.backend.rules.doc_types import DocType
from demo.backend.tools import verify_upload as tool
from engine_v2.pipeline import ocr as coordinate_ocr
from engine_v2.tests import fail_case_samples as cases, p2_resident_samples
from engine_v2.tests.nhis_form_samples import acquisition_cells, insurance_portal_cells, text_pdf
from demo.backend.tests.test_daily_work_uploads import text_pdf as daily_pdf

SECRET = "가짜비밀성명출력금지"
FAKE_DATE = "1990-01-01"


def snapshot(root):
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob("*") if path.is_file()}


def assert_safe(output):
    assert not re.search(r"\d{4,}", output)
    for value in (SECRET, FAKE_DATE, cases.NAME, p2_resident_samples.NAME,
                  "가짜사업장", "가짜상사", "2026-03-03", "2025-10", "message:", "basis:", "file_path:"):
        assert value not in output


@pytest.fixture
def no_db(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Verification must not use a database session")
    monkeypatch.setattr(models, "get_session", forbidden)
    # Imported aliases are forbidden too, including the API wrappers.
    from demo.backend.api import common, documents, review
    from demo.backend.rules import criteria
    for module in (common, documents, review, criteria):
        monkeypatch.setattr(module, "get_session", forbidden)
    monkeypatch.delenv("JBAI_ALLOW_REAL_DOCS", raising=False)


def authored_image_pdf(path, pages):
    with pymupdf.open() as document:
        for source, _ in pages:
            content = io.BytesIO()
            Image.new("RGB", source.pixel_size, "white").save(content, format="PNG")
            page = document.new_page(width=595, height=842)
            page.insert_image(page.rect, stream=content.getvalue(), keep_proportion=False)
        document.save(path)
    return path


def authored_recognition(monkeypatch, pages):
    import demo.backend.ocr as chain
    monkeypatch.setenv("ENGINE_V2_OCR", "own")
    monkeypatch.setattr(chain, "CHAIN", [localocr.LocalOcr(), PdfTextOcr()])
    captured = iter(deepcopy(pages))

    def recognize(png, size):
        page, result = next(captured)
        assert png and size == page.pixel_size
        return result.words

    monkeypatch.setitem(coordinate_ocr.ENGINES, "own", recognize)


@pytest.mark.parametrize("case,slot,category,status,code,grade,attachments", [
    ("1", "nhis_payment", None, "FAIL", "UNREADABLE_FILE", "FAIL", 0),
    ("3a", "work_proof", "지역가입자·피부양자", "PASS", "WORK_DAILY_MONTHS_MISSING", None, 0),
    ("3b", "work_proof", "직장가입자", "PASS", "WORK_ALL_ACQUISITIONS_AFTER_START", None, 2),
    ("4", "resident_abstract", None, "FAIL", "DOCUMENT_ISSUED_TOO_EARLY", "FAIL", 0),
    ("5", "resident_abstract", None, "FAIL", "MISSING_ADDRESS_DATES", "FAIL", 0),
    ("6", "resident_abstract", None, "FAIL", "IMAGE_RESOLUTION_TOO_LOW", "FAIL", 0),
    ("7", "nhis_payment", None, "FAIL", "MISSING_BILLING_MONTHS", "FAIL", 0),
])
def test_failure_case_cli(case, slot, category, status, code, grade, attachments,
                          tmp_path, monkeypatch, capfd, no_db):
    path = tmp_path / "FAKE-input.pdf"
    if case == "1":
        cases.encrypted_pdf(path)
        monkeypatch.setenv("ENGINE_V2_OCR", "off")
    else:
        if case == "3a":
            from demo.backend.tests.test_daily_work_uploads import shaped
            pages = shaped(image=True)
        elif case == "3b":
            cells = [(x, y, "2026.01.01" if text == "2020.01.01" else text)
                     for x, y, text in insurance_portal_cells()]
            first = text_pdf(tmp_path / "FAKE-form.pdf", cells)
            with pymupdf.open(first) as source, pymupdf.open() as document:
                document.insert_pdf(source)
                for _ in range(2):
                    content = io.BytesIO()
                    Image.new("RGB", (2480, 3508), "white").save(content, format="PNG")
                    page = document.new_page()
                    page.insert_image(page.rect, stream=content.getvalue())
                document.save(path)
            monkeypatch.setenv("ENGINE_V2_OCR", "off")
            pages = None
        elif case == "4":
            pages = p2_resident_samples.resident()
            for _, recognized in pages:
                for word in recognized.words:
                    if word.text == "2026년 03월 03일":
                        word.text = "2026년 03월 02일"
        elif case == "5":
            pages = cases.missing_address_dates()
        elif case == "6":
            pages = cases.tiny_unknown()
        else:
            pages = cases.missing_payment_months()
        if pages is not None:
            authored_image_pdf(path, pages)
            authored_recognition(monkeypatch, pages)
    args = ["--slot", slot, "--self-identity", str(path)]
    if category:
        args += ["--work-category", category]
    before = snapshot(tmp_path)
    assert tool.main(args) == 0
    captured = capfd.readouterr()
    assert captured.err == ""
    output = captured.out
    assert f"document_status: {status}\n" in output
    assert f"reason: {code} {grade}\n" in output if grade else f"work_reason: {code}\n" in output
    assert f"additional_pages: {attachments}\n" in output
    assert "blockers: O\n" in output
    if case in {"3a", "3b"}:
        assert "identity: O\n" in output
        assert "work_status: NOT_MET\n" in output
        assert "work_reason: WORK_CONTINUITY_NOT_MET\n" in output
    if case == "6":
        assert "reason: PAGES_INCOMPLETE FAIL\n" in output
    assert_safe(output)
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("identity_option", [False, True])
def test_identity_missing_does_not_guess_century(identity_option, tmp_path, monkeypatch, capfd, no_db):
    pages = cases.daily()
    for _, recognized in pages:
        for word in recognized.words:
            if word.text == "1990년01월01일":
                word.text = "90년01월01일"
    path = daily_pdf(tmp_path / "FAKE-birth.pdf", pages)
    monkeypatch.setenv("ENGINE_V2_OCR", "off")
    args = ["--slot", "work_proof", "--work-category", "지역가입자·피부양자", str(path)]
    if identity_option:
        args.append("--self-identity")
    assert tool.main(args) == 0
    output = capfd.readouterr().out
    assert "identity: 본인정보 없음\n" in output
    assert "work_status: UNDETERMINED\n" in output
    assert "WORK_IDENTITY_UNCONFIRMED" in output
    assert "blockers: X\n" in output
    assert_safe(output)


@pytest.mark.parametrize("category,expected", [
    ("직장가입자", "4대보험"), ("지역가입자·피부양자", "일용근로내역서"),
    ("사업소득 사업자", "사업자등록증명"), ("농업·임업", "농업경영체"), ("어업", "어업경영체"),
])
def test_slots_follow_actual_category(category, expected, capfd, no_db):
    assert tool.main(["--slots-list", "--work-category", category]) == 0
    output = capfd.readouterr().out
    assert "work_proof:" in output and expected in output
    assert "resident_abstract:" in output and "nhis_payment:" in output
    assert_safe(output)


def test_job_package_slots_have_no_work_or_income(capfd, no_db):
    assert tool.main(["--program", "job_package", "--slots-list"]) == 0
    output = capfd.readouterr().out
    assert "resident_abstract:" in output
    assert "work_proof:" not in output and "nhis_payment:" not in output
    assert_safe(output)


@pytest.mark.parametrize("args,code", [
    (["--program", SECRET, "--slots-list"], "PROGRAM_UNKNOWN"),
    (["--work-category", SECRET, "--slots-list"], "WORK_CATEGORY_UNKNOWN"),
    (["--slot", SECRET, SECRET], "UPLOAD_SLOT_UNKNOWN"),
    (["--slot", "work_proof", SECRET], "WORK_CATEGORY_REQUIRED"),
    (["--program", "job_package", "--income", SECRET, SECRET, SECRET], "INCOME_NOT_APPLICABLE"),
    (["--program", "job_package", "--work-category", "직장가입자", "--slots-list"], "WORK_CATEGORY_NOT_APPLICABLE"),
    (["--slot", "nhis_payment", SECRET + ".pdf"], "INPUT_UNAVAILABLE"),
    (["--slot", "nhis_payment", SECRET + ".txt"], "FORMAT_UNSUPPORTED"),
    (["--income", SECRET], "ARGUMENT_ERROR"),
    (["--unknown", SECRET], "ARGUMENT_ERROR"),
    (["--slots-list", SECRET], "ARGUMENT_ERROR"),
    ([], "ARGUMENT_ERROR"),
])
def test_errors_never_echo_args(args, code, capfd, no_db):
    assert tool.main(args) == 2
    captured = capfd.readouterr()
    assert captured.err == ""
    assert captured.out == f"error: {code}\n"
    assert_safe(captured.out)


@pytest.mark.parametrize("operation", ["write", "mkdir", "os-open", "sqlite", "log", "copy", "tempfile", "process"])
def test_write_attempts_are_blocked_even_when_ocr_catches_them(operation, tmp_path, monkeypatch, capfd, no_db):
    import demo.backend.ocr as chain
    path = tmp_path / "FAKE-source.png"
    Image.new("RGB", (900, 1000), "white").save(path)
    dest = tmp_path / "FAKE-forbidden"

    class WritingAdapter:
        name = "fixture"
        def read(self, file_path, expected):
            if operation == "write":
                dest.write_text(SECRET)
            elif operation == "mkdir":
                dest.mkdir()
            elif operation == "os-open":
                os.close(os.open(dest, os.O_WRONLY | os.O_CREAT))
            elif operation == "sqlite":
                import sqlite3
                sqlite3.connect(str(dest))
            elif operation == "log":
                logging.FileHandler(dest)
            elif operation == "copy":
                import shutil
                shutil.copyfile(path, dest)
            elif operation == "tempfile":
                import tempfile
                tempfile.mkstemp(dir=tmp_path)
            else:
                subprocess.run([sys.executable, "-c", "pass"])

    monkeypatch.setattr(chain, "CHAIN", [WritingAdapter(), PdfTextOcr()])
    before = snapshot(tmp_path)
    assert tool.main(["--slot", "resident_abstract", str(path)]) == 2
    output = capfd.readouterr()
    assert output.out == "error: WRITE_ATTEMPT_BLOCKED\n" and output.err == ""
    assert snapshot(tmp_path) == before


def test_python_native_logs_and_exception_text_never_escape(tmp_path, monkeypatch, capfd, no_db):
    import ctypes
    import demo.backend.ocr as chain
    path = tmp_path / (SECRET + ".png")
    Image.new("RGB", (900, 1000), "white").save(path)
    log_path = tmp_path / "FAKE-existing.log"
    handler = logging.FileHandler(log_path)
    logging.getLogger().addHandler(handler)
    before = snapshot(tmp_path)

    class NoisyAdapter:
        name = "fixture"
        def read(self, file_path, expected):
            print(SECRET)
            print(FAKE_DATE, file=sys.stderr)
            os.write(1, SECRET.encode())
            os.write(2, FAKE_DATE.encode())
            ctypes.CDLL(None).printf((SECRET + "\n").encode())
            logging.critical(SECRET)
            raise RuntimeError(SECRET)

    monkeypatch.setattr(chain, "CHAIN", [NoisyAdapter(), PdfTextOcr()])
    try:
        assert tool.main(["--slot", "resident_abstract", str(path)]) == 0
    finally:
        logging.getLogger().removeHandler(handler)
        handler.close()
    output = capfd.readouterr()
    assert output.err == ""
    assert_safe(output.out)
    assert str(path) not in output.out
    assert snapshot(tmp_path) == before


def test_dynamic_metadata_cannot_become_output(tmp_path, monkeypatch, capfd, no_db):
    import demo.backend.ocr as chain
    from demo.backend import upload_assessment
    from demo.backend.rules.doc_check import CheckFinding, CheckResult
    path = tmp_path / "FAKE-source.png"
    Image.new("RGB", (900, 1000), "white").save(path)

    class MaliciousAdapter:
        name = "fixture"
        def read(self, file_path, expected):
            return OcrResult(tier=SECRET, confidence=float("nan"), page_count=12345,
                             fields={SECRET: FAKE_DATE, "추가첨부쪽": json.dumps([SECRET] * 1000)})

    monkeypatch.setattr(chain, "CHAIN", [MaliciousAdapter()])
    monkeypatch.setattr(upload_assessment, "check_document", lambda *args, **kwargs: CheckResult(
        "NEEDS_REVIEW", [CheckFinding("FAKE_UNAPPROVED_CODE", SECRET, severity=SECRET)]))
    assert tool.main(["--slot", "resident_abstract", str(path)]) == 0
    output = capfd.readouterr().out
    assert "tier: X\n" in output and "confidence: X\n" in output and "pages: X\n" in output
    assert "reason: UNKNOWN_CODE X\n" in output
    assert "additional_pages: X\n" in output
    assert "FAKE_UNAPPROVED_CODE" not in output
    assert_safe(output)


def test_standalone_cli_and_help_are_value_free_and_do_not_write(tmp_path):
    path = cases.encrypted_pdf(tmp_path / "FAKE-source.pdf")
    before = snapshot(tmp_path)
    env = {**os.environ, "ENGINE_V2_OCR": "off", "JBAI_ALLOW_REAL_DOCS": "false"}
    for args, expected in [(["--slot", "nhis_payment", str(path)], 0),
                           (["--program", SECRET], 2), (["--help"], 0)]:
        result = subprocess.run([sys.executable, "-B", "-m", "demo.backend.tools.verify_upload", *args],
                                capture_output=True, text=True, env=env, cwd=Path(__file__).resolve().parents[3])
        assert result.returncode == expected
        assert_safe(result.stdout + result.stderr)
        assert result.stderr == ""
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("outcome,status,blocked", [
    ("normal", "MET", "X"), ("excess", "OVER_LIMIT", "O"),
    ("unreadable", "UNDETERMINED", "X"), ("pair-mismatch", "UNDETERMINED", "X"),
])
def test_income_uses_three_real_synthetic_files(outcome, status, blocked, tmp_path, monkeypatch, capfd, no_db):
    from engine_v2.tests import p2_form_samples as qualification, p2_payment_samples as payment
    from engine_v2.tests.test_income_payment_evidence import _text_pdf
    q_cells, q_size = qualification.qualification(noise=False, empty_management=False)
    p_cells, p_size = payment.payment(workplace="가상사업장")
    if outcome == "excess":
        p_cells = [(*cell[:4], f"{int(cell[4].replace(',', '')) * 100:,}", cell[5])
                   if re.fullmatch(r"[\d,]+", cell[4]) and "," in cell[4] else cell for cell in p_cells]
    elif outcome == "unreadable":
        p_cells = [cell for cell in p_cells if cell[4] != "고지금액"]
    elif outcome == "pair-mismatch":
        q_cells = [(*cell[:4], "가짜다른성명", cell[5]) if cell[4] == qualification.NAME else cell for cell in q_cells]
    p_path = _text_pdf(tmp_path / "FAKE-payment.pdf", p_cells, p_size)
    q_path = _text_pdf(tmp_path / "FAKE-qualification.pdf", q_cells, q_size)
    a_path = text_pdf(tmp_path / "FAKE-history.pdf", acquisition_cells(name=payment.NAME))
    monkeypatch.setenv("ENGINE_V2_OCR", "off")
    before = snapshot(tmp_path)
    assert tool.main(["--self-identity", "--income", str(p_path), str(q_path), str(a_path)]) == 0
    output = capfd.readouterr()
    assert output.err == ""
    assert f"income_status: {status}\n" in output.out
    assert f"blockers: {blocked}\n" in output.out
    if outcome in {"normal", "excess"}:
        assert "membership: 직장\n" in output.out
    if outcome == "excess":
        assert "reason: INCOME_ABOVE_BOTH_LIMITS\n" in output.out
    if outcome == "pair-mismatch":
        assert "reason: NHIS_SUBSCRIBER_IDENTITY_REVIEW\n" in output.out
    assert {line.split(":", 1)[0] for line in output.out.splitlines()} <= {
        "membership", "income_status", "reason", "blockers",
    }
    assert_safe(output.out)
    assert qualification.NAME not in output.out and payment.NAME not in output.out
    assert snapshot(tmp_path) == before


def test_work_history_in_nhis_slot_uses_actual_work_blocker(tmp_path, monkeypatch, capfd, no_db):
    import demo.backend.ocr as chain
    path = tmp_path / "FAKE-history.png"
    Image.new("RGB", (1800, 2400), "white").save(path)
    fields = {"성명": SECRET, "생년월일": FAKE_DATE, "발급일": "2026-03-03",
              "양식판독상태": "완전", "변동내역": "최근 5년 포함",
              "자격이력자료": json.dumps({"period": None, "period_label_present": False,
                  "coverage_basis": "full_history", "recent_five_years_covered": True,
                  "rows": [{"category": "직장", "acquired": "2026-01-01", "lost": None}]})}

    class AuthoredAdapter:
        name = "fixture"
        def read(self, file_path, expected):
            return OcrResult(detected_doc_type=DocType.NHIS_ACQUISITION_LOSS,
                             confidence=.97, image_quality=.95, issue_date=date(2026, 3, 3),
                             fields=fields, tier="fixture")

    monkeypatch.setattr(chain, "CHAIN", [AuthoredAdapter()])
    assert tool.main(["--slot", "nhis_acquisition_loss", "--work-category", "직장가입자",
                      "--self-identity", str(path)]) == 0
    output = capfd.readouterr().out
    assert "document_status: PASS\n" in output
    assert "work_status: NOT_MET\n" in output
    assert "work_reason: WORK_HISTORY_START_NOT_COVERED\n" in output
    assert "blockers: O\n" in output
    assert_safe(output)


def test_image_portal_title_interleaving_retains_existing_uncertainty(tmp_path, monkeypatch, capfd, no_db):
    # Existing classification cannot recognize this exact interleaved title.
    # Record the limitation without changing the production classifier.
    pages = cases.mixed_portal()
    path = authored_image_pdf(tmp_path / "FAKE-image-portal.pdf", pages)
    authored_recognition(monkeypatch, pages)
    assert tool.main(["--slot", "work_proof", "--work-category", "직장가입자",
                      "--self-identity", str(path)]) == 0
    output = capfd.readouterr().out
    assert "document_status: NEEDS_REVIEW\n" in output
    assert "reason: UNKNOWN_DOCUMENT_TYPE NEEDS_REVIEW\n" in output
    assert "blockers: X\n" in output
    assert_safe(output)

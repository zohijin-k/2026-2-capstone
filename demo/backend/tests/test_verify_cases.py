"""Synthetic-only regression CLI tests; no real documents or private folders."""
from copy import deepcopy
from datetime import date
import json
import logging
import os
from pathlib import Path
import subprocess
import sys

from PIL import Image
import pytest

import demo.backend.ocr as chain
from demo.backend.ocr.base import OcrResult
from demo.backend.rules.doc_types import DocType
from demo.backend.tests.test_verify_upload import no_db, snapshot
from demo.backend.tools import verify_cases as tool, verify_upload as upload

SECRET = "FAKE-identity-value-must-stay-hidden"
FILENAME = "FAKE-filename-must-stay-hidden.png"


def write_manifest(path, cases):
    path.write_text(json.dumps({"schema_version": 1, "cases": cases}), encoding="utf-8")
    return path


def expected_path(path):
    return Path(str(path) + ".expected.json")


@pytest.fixture
def synthetic(tmp_path, monkeypatch, no_db):
    paths = [tmp_path / FILENAME, tmp_path / "FAKE-qualification.png", tmp_path / "FAKE-history.png"]
    for path in paths:
        Image.new("RGB", (1800, 2400), "white").save(path)
    state = {"confidence": .9}

    class AuthoredAdapter:
        name = "fixture"

        def read(self, file_path, expected):
            return OcrResult(
                expected, state["confidence"], image_quality=.9, issue_date=date(2026, 3, 2),
                fields={"성명": SECRET, "생년월일": "1990-01-01", "발급일": "2026-03-02",
                        "판독검증실패": "monthly_rows_found, name_found, " + SECRET,
                        "판독경고": "FAKE raw text 123,000"}, tier="fixture", engine="fixture",
            )

    monkeypatch.setattr(chain, "CHAIN", [AuthoredAdapter()])
    cases = [
        {"id": "case7", "slot": "resident_abstract", "self_identity": True, "file": paths[0].name},
        {"id": "work_case", "slot": "work_proof", "work_category": "직장가입자",
         "self_identity": True, "file": paths[0].name},
        {"id": "ok_income", "self_identity": True, "income": dict(zip(tool._INCOME_FILES, map(str, paths)))},
    ]
    manifest = write_manifest(tmp_path / "FAKE-cases.json", cases)
    return manifest, cases, paths, state


def invoke(path, record=False):
    return tool.main(["--cases", str(path), *(["--record"] if record else [])])


def assert_private(text, paths=()):
    for secret in (SECRET, FILENAME, "1990-01-01", "2026-03-03", "2026-03-02", "123,000", "FAKE raw text", *map(str, paths)):
        assert secret not in text
    assert "confidence" not in text


def load_expected(path):
    return json.loads(expected_path(path).read_text())


def save_expected(path, value):
    expected_path(path).write_text(json.dumps(value), encoding="utf-8")


def test_record_then_compare_all_modes_without_values(synthetic, monkeypatch, capfd):
    manifest, cases, paths, state = synthetic
    before = snapshot(manifest.parent)
    assert invoke(manifest, True) == 0
    assert capfd.readouterr().out == "case7 O\nwork_case O\nok_income O\n3/3\n"
    after = snapshot(manifest.parent)
    assert set(after) - set(before) == {expected_path(manifest).name}
    assert all(after[key] == value for key, value in before.items())
    record = load_expected(manifest)
    assert record["schema_version"] == 1
    assert record["cases"]["case7"]["identity"] == "O"
    document = record["cases"]["case7"]["documents"]["resident_abstract"]
    assert set(document) == {"detected_type", "document_status", "reason", "applicant_reason", "failed_validation"}
    assert "UNKNOWN_VALIDATION" in document["failed_validation"]
    assert document["applicant_reason"]
    assert "work_status" in record["cases"]["work_case"]
    assert set(record["cases"]["ok_income"]["documents"]) == {"nhis_payment", "nhis_qualification", "nhis_acquisition_loss"}
    assert "income_status" in record["cases"]["ok_income"]
    assert "work_status" not in record["cases"]["ok_income"]
    assert_private(expected_path(manifest).read_text(), [*paths, manifest])
    monkeypatch.chdir(manifest.parent.parent)
    assert invoke(manifest) == 0
    captured = capfd.readouterr()
    assert captured.out == "case7 O\nwork_case O\nok_income O\n3/3\n" and captured.err == ""
    assert snapshot(manifest.parent) == after


@pytest.mark.parametrize("direction", ["added", "removed"])
def test_code_delta_sign_and_only_affected_case(synthetic, capfd, direction):
    manifest, *_ = synthetic
    assert invoke(manifest, True) == 0
    capfd.readouterr()
    record = load_expected(manifest)
    reasons = record["cases"]["case7"]["documents"]["resident_abstract"]["reason"]
    if direction == "added":
        changed = reasons.pop()
        sign = "+"
    else:
        changed = {"code": "ALL_CLEAR", "severity": "INFO"}
        reasons.append(changed)
        sign = "-"
    save_expected(manifest, record)
    assert invoke(manifest) == 1
    output = capfd.readouterr()
    assert output.err == ""
    assert output.out == (f"case7 X\n{sign}resident_abstract.reason:{changed['code']}:{changed['severity']}\n"
                          "work_case O\nok_income O\n2/3\n")
    assert_private(output.out)


@pytest.mark.parametrize("field,value", [
    ("identity", "X"), ("blockers", "O"), ("work_status", "MET"),
    ("income_status", "MET"), ("work_reason", ["ALL_CLEAR"]), ("income_reason", ["ALL_CLEAR"]),
])
def test_case_level_deltas(synthetic, capfd, field, value):
    manifest, *_ = synthetic
    assert invoke(manifest, True) == 0
    capfd.readouterr()
    record = load_expected(manifest)
    case_id = "work_case" if field.startswith("work") else "ok_income" if field.startswith("income") else "case7"
    if field == "blockers":
        value = "X" if record["cases"][case_id][field] == "O" else "O"
    assert record["cases"][case_id][field] != value
    record["cases"][case_id][field] = value
    save_expected(manifest, record)
    assert invoke(manifest) == 1
    output = capfd.readouterr().out
    assert f"{case_id} X\n" in output and "2/3\n" in output
    assert any(line.startswith("-" + field.replace("_reason", "_reason:")) for line in output.splitlines())


@pytest.mark.parametrize("field", ["detected_type", "document_status", "reason", "applicant_reason", "failed_validation"])
def test_document_deltas(synthetic, capfd, field):
    manifest, *_ = synthetic
    assert invoke(manifest, True) == 0
    capfd.readouterr()
    record = load_expected(manifest)
    document = record["cases"]["case7"]["documents"]["resident_abstract"]
    if field == "detected_type":
        document[field] = "X"
    elif field == "document_status":
        document[field] = "PASS" if document[field] != "PASS" else "FAIL"
    elif field in {"reason", "applicant_reason"}:
        # Severity-only changes must retain the code identity in both tokens.
        document[field][0]["severity"] = "INFO" if document[field][0]["severity"] != "INFO" else "FAIL"
    else:
        document[field].append("months_continuous")
    save_expected(manifest, record)
    assert invoke(manifest) == 1
    output = capfd.readouterr().out
    assert "case7 X\n" in output and "work_case O\nok_income O\n2/3\n" in output
    assert any(line.startswith(f"-resident_abstract.{field}:") for line in output.splitlines())
    assert_private(output)


def test_confidence_and_order_jitter_ignored(synthetic, capfd):
    manifest, cases, paths, state = synthetic
    assert invoke(manifest, True) == 0
    capfd.readouterr()
    record = load_expected(manifest)
    for case in record["cases"].values():
        for document in case["documents"].values():
            for field in ("reason", "applicant_reason", "failed_validation"):
                document[field] = list(reversed(document[field])) * 2
    save_expected(manifest, record)
    write_manifest(manifest, list(reversed(cases)))
    state["confidence"] = .97
    assert invoke(manifest) == 0
    assert capfd.readouterr().out == "ok_income O\nwork_case O\ncase7 O\n3/3\n"


def test_case_membership_deltas_use_union(synthetic, capfd):
    manifest, cases, *_ = synthetic
    assert invoke(manifest, True) == 0
    capfd.readouterr()
    changed = deepcopy(cases[:2])
    changed[0]["id"] = "new_case"
    write_manifest(manifest, changed)
    assert invoke(manifest) == 1
    assert capfd.readouterr().out == ("new_case X\n+CASE_ADDED\nwork_case O\ncase7 X\n-CASE_REMOVED\n"
                                     "ok_income X\n-CASE_REMOVED\n1/4\n")


@pytest.mark.parametrize("record_mode", [False, True])
@pytest.mark.parametrize("error_class", [RuntimeError, ValueError, OSError])
def test_case_exceptions_show_class_only_and_preserve_record(synthetic, monkeypatch, capfd, record_mode, error_class):
    manifest, *_ = synthetic
    assert invoke(manifest, True) == 0
    capfd.readouterr()
    before = expected_path(manifest).read_bytes()
    original = upload.assess_document

    def fail_one(args, *context):
        if args.slot == "resident_abstract":
            print(SECRET)
            os.write(2, FILENAME.encode())
            logging.critical(SECRET)
            raise error_class(str(manifest) + SECRET)
        return original(args, *context)

    monkeypatch.setattr(upload, "assess_document", fail_one)
    assert invoke(manifest, record_mode) == 1
    output = capfd.readouterr()
    assert output.err == ""
    assert output.out == f"case7 X {error_class.__name__}\nwork_case O\nok_income O\n2/3\n"
    assert_private(output.out, [manifest])
    assert expected_path(manifest).read_bytes() == before


def test_new_record_case_error_creates_no_expected(synthetic, monkeypatch, capfd):
    manifest, *_ = synthetic
    monkeypatch.setattr(upload, "assess_document", lambda *a: (_ for _ in ()).throw(RuntimeError(SECRET)))
    assert invoke(manifest, True) == 1
    assert not expected_path(manifest).exists()
    assert "case7 X RuntimeError\n" in capfd.readouterr().out


def test_guard_blocks_swallowed_writes(synthetic, monkeypatch, capfd):
    manifest, *_ = synthetic
    original = upload.assess_document
    forbidden = manifest.parent / "FAKE-forbidden"

    def write_then_continue(*args):
        try:
            forbidden.write_text(SECRET)
        except Exception:
            pass
        return original(*args)

    monkeypatch.setattr(upload, "assess_document", write_then_continue)
    assert invoke(manifest, True) == 1
    output = capfd.readouterr()
    assert "case7 X VerificationError\n" in output.out and output.err == ""
    assert not forbidden.exists() and not expected_path(manifest).exists()


@pytest.mark.parametrize("operation", ["write", "replace"])
def test_record_io_failure_preserves_previous(synthetic, monkeypatch, capfd, operation):
    manifest, *_ = synthetic
    assert invoke(manifest, True) == 0
    capfd.readouterr()
    before = snapshot(manifest.parent)
    if operation == "replace":
        monkeypatch.setattr(tool.os, "replace", lambda *a: (_ for _ in ()).throw(OSError(SECRET)))
    else:
        monkeypatch.setattr(tool.json, "dump", lambda *a, **kw: (_ for _ in ()).throw(OSError(SECRET)))
    assert invoke(manifest, True) == 2
    output = capfd.readouterr()
    assert output.out == "RECORD_ERROR\n" and output.err == ""
    assert snapshot(manifest.parent) == before


@pytest.mark.parametrize("bad", [
    {}, {"schema_version": True, "cases": []}, {"schema_version": 2, "cases": []},
    {"schema_version": 1, "cases": []}, {"schema_version": 1, "cases": [None]},
    {"schema_version": 1, "cases": [{"id": "case1", "slot": "resident_abstract"}]},
    {"schema_version": 1, "cases": [{"id": "case1", "slot": "resident_abstract", "file": FILENAME, "extra": SECRET}]},
])
def test_invalid_manifest_shapes_do_not_echo(tmp_path, bad, capfd):
    manifest = tmp_path / FILENAME
    manifest.write_text(json.dumps(bad))
    assert invoke(manifest, True) == 2
    output = capfd.readouterr()
    assert output.out == "MANIFEST_INVALID\n" and output.err == ""


@pytest.mark.parametrize("bad_id", ["../secret.pdf", "case\nsecret", "", "a" * 65, SECRET + ".pdf", "가짜실명"])
def test_invalid_ids(tmp_path, bad_id, capfd):
    manifest = write_manifest(tmp_path / "FAKE.json", [{"id": bad_id, "slot": "resident_abstract", "file": FILENAME}])
    assert invoke(manifest, True) == 2
    assert capfd.readouterr().out == "MANIFEST_INVALID\n"


@pytest.mark.parametrize("change", ["duplicate-id", "self-string", "empty-income", "mixed", "duplicate-key"])
def test_ambiguous_or_malformed_cases(synthetic, capfd, change):
    manifest, cases, *_ = synthetic
    modified = deepcopy(cases)
    if change == "duplicate-id":
        modified[1]["id"] = modified[0]["id"]
    elif change == "self-string":
        modified[0]["self_identity"] = "false"
    elif change == "empty-income":
        modified[2]["income"] = {}
    elif change == "mixed":
        modified[2]["file"] = FILENAME
    if change == "duplicate-key":
        manifest.write_text('{"schema_version":1,"schema_version":1,"cases":[]}')
    else:
        write_manifest(manifest, modified)
    assert invoke(manifest, True) == 2
    assert capfd.readouterr().out == "MANIFEST_INVALID\n"


@pytest.mark.parametrize("change", ["extra", "code", "severity", "validation", "slot", "status", "version", "shape", "id", "duplicate"])
def test_baseline_injection_is_rejected_without_values(synthetic, capfd, change):
    manifest, *_ = synthetic
    assert invoke(manifest, True) == 0
    capfd.readouterr()
    raw = load_expected(manifest)
    case = raw["cases"]["case7"]
    document = case["documents"]["resident_abstract"]
    if change == "extra": document["raw"] = SECRET
    elif change == "code": document["reason"][0]["code"] = SECRET
    elif change == "severity": document["reason"][0]["severity"] = SECRET
    elif change == "validation": document["failed_validation"] = [SECRET]
    elif change == "slot": case["documents"][FILENAME] = case["documents"].pop("resident_abstract")
    elif change == "status": document["document_status"] = SECRET
    elif change == "version": raw["schema_version"] = 3
    elif change == "shape": raw["cases"] = []
    elif change == "id": raw["cases"][SECRET + ".pdf"] = raw["cases"].pop("case7")
    save_expected(manifest, raw)
    if change == "duplicate":
        expected_path(manifest).write_text('{"schema_version":1,"schema_version":1,"cases":{}}')
    before = expected_path(manifest).read_bytes()
    assert invoke(manifest) == 2
    captured = capfd.readouterr()
    assert captured.out == "EXPECTED_INVALID\n" and captured.err == ""
    assert expected_path(manifest).read_bytes() == before


def test_missing_baseline_never_records(synthetic, capfd):
    manifest, *_ = synthetic
    before = snapshot(manifest.parent)
    assert invoke(manifest) == 2
    assert capfd.readouterr().out == "EXPECTED_MISSING\n"
    assert snapshot(manifest.parent) == before


@pytest.fixture
def git_repo(tmp_path, monkeypatch):
    root = tmp_path / "FAKE-checkout"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
    (root / ".gitignore").write_text("ignored/\nonly.json\n")
    (root / "ignored").mkdir()
    monkeypatch.setattr(tool, "REPOSITORY_ROOT", root)
    return root


def test_location_uses_actual_paths_and_outside_never_runs_git(git_repo, tmp_path, monkeypatch):
    root = git_repo
    allowed = root / "ignored" / "FAKE.json"
    denied = root / "FAKE.json"
    allowed.write_text("{}")
    denied.write_text("{}")
    assert tool._private_location(allowed) == allowed
    with pytest.raises(tool.CasesError): tool._private_location(denied)
    subprocess.run(["git", "add", "-f", str(allowed)], cwd=root, check=True, capture_output=True)
    with pytest.raises(tool.CasesError): tool._private_location(allowed)
    outside = tmp_path / "FAKE-outside.json"
    outside.write_text("{}")
    inside_link = root / "FAKE-link.json"
    inside_link.symlink_to(outside)
    monkeypatch.setattr(tool.subprocess, "run", lambda *a, **kw: pytest.fail("Outside targets must not call Git"))
    assert tool._private_location(outside) == outside
    assert tool._private_location(inside_link) == outside


def test_external_symlink_to_checkout_enforces_git(git_repo, tmp_path):
    allowed = git_repo / "ignored" / "FAKE.json"
    denied = git_repo / "FAKE.json"
    for target in (allowed, denied): target.write_text("{}")
    good_link, bad_link = tmp_path / "FAKE-good.json", tmp_path / "FAKE-bad.json"
    good_link.symlink_to(allowed)
    bad_link.symlink_to(denied)
    assert tool._private_location(good_link) == allowed
    with pytest.raises(tool.CasesError): tool._private_location(bad_link)
    parent_link = tmp_path / "FAKE-parent"
    parent_link.symlink_to(git_repo, target_is_directory=True)
    with pytest.raises(tool.CasesError): tool._private_location(parent_link / "FAKE.json")
    assert tool._private_location(parent_link / "ignored" / "new.json") == git_repo / "ignored" / "new.json"


@pytest.mark.parametrize("returncode", [1, 128])
def test_git_check_failures_closed(git_repo, monkeypatch, returncode):
    monkeypatch.setattr(tool.subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(a[0], returncode))
    with pytest.raises(tool.CasesError): tool._private_location(git_repo / "ignored" / "FAKE.json")


def test_manifest_and_expected_locations_independent(git_repo, capfd):
    manifest = write_manifest(git_repo / "only.json", [{"id": "case1", "slot": "resident_abstract", "file": FILENAME}])
    assert invoke(manifest, True) == 2
    assert capfd.readouterr().out == "LOCATION_REJECTED\n"
    assert not expected_path(manifest).exists()


def test_safe_symlink_manifest_and_expected_record(synthetic, tmp_path, capfd):
    manifest, *_ = synthetic
    assert invoke(manifest, True) == 0
    capfd.readouterr()
    link_dir = tmp_path / "FAKE-links"
    link_dir.mkdir()
    manifest_link = link_dir / "FAKE-linked.json"
    manifest_link.symlink_to(manifest)
    expected_path(manifest_link).symlink_to(expected_path(manifest))
    assert invoke(manifest_link) == 0
    assert capfd.readouterr().out.endswith("3/3\n")
    assert invoke(manifest_link, True) == 0
    assert expected_path(manifest_link).is_symlink()
    assert capfd.readouterr().out.endswith("3/3\n")


def test_unignored_manifest_rejected_before_reading(git_repo, capfd):
    path = git_repo / FILENAME
    path.write_text(SECRET)
    assert invoke(path, True) == 2
    output = capfd.readouterr()
    assert output.out == "LOCATION_REJECTED\n" and output.err == ""


def test_standalone_entry_point_and_safe_help(tmp_path):
    from engine_v2.tests.fail_case_samples import encrypted_pdf
    source = encrypted_pdf(tmp_path / "FAKE-encrypted.pdf")
    manifest = write_manifest(tmp_path / "FAKE-cases.json", [{"id": "encrypted", "slot": "nhis_payment", "file": str(source)}])
    env = {**os.environ, "ENGINE_V2_OCR": "off", "JBAI_ALLOW_REAL_DOCS": "false"}
    root = Path(__file__).resolve().parents[3]
    for arguments, code in [(["--cases", str(manifest), "--record"], 0), (["--cases", str(manifest)], 0),
                            (["--bad", SECRET], 2), (["--help"], 0)]:
        completed = subprocess.run([sys.executable, "-B", "-m", "demo.backend.tools.verify_cases", *arguments],
                                   cwd=root, env=env, capture_output=True, text=True)
        assert completed.returncode == code
        assert completed.stderr == ""
        assert_private(completed.stdout, [source, manifest])


@pytest.mark.parametrize("record_mode", [False, True])
def test_expected_symlink_cannot_overwrite_source(synthetic, capfd, record_mode):
    manifest, cases, paths, state = synthetic
    original = paths[0].read_bytes()
    expected_path(manifest).symlink_to(paths[0])
    assert invoke(manifest, record_mode) == 2
    captured = capfd.readouterr()
    assert captured.out == "LOCATION_REJECTED\n" and captured.err == ""
    assert paths[0].read_bytes() == original
    assert expected_path(manifest).is_symlink()


def test_noisy_dependency_and_unreviewed_findings_never_escape(synthetic, monkeypatch, capfd):
    import ctypes
    from demo.backend import upload_assessment
    from demo.backend.rules.doc_check import CheckFinding, CheckResult

    manifest, cases, paths, state = synthetic
    write_manifest(manifest, cases[:1])
    sink = manifest.parent / "FAKE-existing.log"
    handler = logging.FileHandler(sink)
    logging.getLogger().addHandler(handler)

    class NoisyAdapter:
        name = "fixture"

        def read(self, file_path, expected):
            print(SECRET)
            print(FILENAME, file=sys.stderr)
            os.write(1, SECRET.encode())
            os.write(2, FILENAME.encode())
            ctypes.CDLL(None).printf((SECRET + "\n").encode())
            logging.critical(SECRET)
            return OcrResult(expected, .9, image_quality=.9, issue_date=date(2026, 3, 3),
                             fields={"성명": SECRET, "생년월일": "1990-01-01",
                                     "판독검증실패": SECRET}, tier="fixture")

    monkeypatch.setattr(chain, "CHAIN", [NoisyAdapter()])
    monkeypatch.setattr(upload_assessment, "check_document", lambda *a, **kw: CheckResult(
        "NEEDS_REVIEW", [CheckFinding(SECRET, str(paths[0]), severity=SECRET)],
    ))
    try:
        assert invoke(manifest, True) == 0
        assert invoke(manifest) == 0
    finally:
        logging.getLogger().removeHandler(handler)
        handler.close()
    captured = capfd.readouterr()
    assert captured.out == "case7 O\n1/1\ncase7 O\n1/1\n" and captured.err == ""
    record = load_expected(manifest)["cases"]["case7"]["documents"]["resident_abstract"]
    assert record["reason"] == [{"code": "UNKNOWN_CODE", "severity": "X"}]
    assert record["applicant_reason"] == [{"code": "UNKNOWN_CODE", "severity": "X"}]
    assert record["failed_validation"] == ["UNKNOWN_VALIDATION"]
    assert_private(expected_path(manifest).read_text(), [*paths, manifest])
    assert sink.read_bytes() == b""


@pytest.mark.parametrize("record_mode", [False, True])
def test_case_source_resolution_error_remains_case_error(synthetic, capfd, record_mode):
    manifest, cases, paths, state = synthetic
    assert invoke(manifest, True) == 0
    capfd.readouterr()
    before = expected_path(manifest).read_bytes()
    cases[0]["file"] = "\x00" + SECRET
    write_manifest(manifest, cases)
    assert invoke(manifest, record_mode) == 1
    captured = capfd.readouterr()
    assert captured.out == "case7 X ValueError\nwork_case O\nok_income O\n2/3\n"
    assert captured.err == ""
    assert expected_path(manifest).read_bytes() == before

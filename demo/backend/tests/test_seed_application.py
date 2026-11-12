"""Synthetic-only acceptance for the stage-two demo helper and its marker."""
from copy import deepcopy
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path

import pymupdf
import pytest
from sqlmodel import SQLModel, create_engine, select

from demo.backend import models
from demo.backend.api import applications, common, documents, forms, officer, review
from demo.backend.rules.criteria import ensure_defaults
from demo.backend.rules.programs import DOUBLE_SAVINGS, JOB_PACKAGE

MARKER_KEY = "_seed_application"
MARKER_VALUE = "seed-application-v1"
PRIVATE_NAME = "가짜인증비밀명"
PRIVATE_BIRTH = "1990-07-19"


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    database = create_engine(f"sqlite:///{tmp_path / 'demo.db'}")
    monkeypatch.setattr(models, "engine", database)
    storage = tmp_path / "storage"
    storage.mkdir()
    for module in (applications, common, documents, forms):
        monkeypatch.setattr(module, "STORAGE", storage)
    monkeypatch.setattr(applications, "SIGNATURES", storage / "signatures")
    monkeypatch.setattr(documents, "DOCUMENTS", storage / "documents")
    SQLModel.metadata.create_all(database)
    ensure_defaults()
    yield storage
    database.dispose()


def make_application(storage, *, program=DOUBLE_SAVINGS, verified=True, created_at=None):
    with models.get_session() as session:
        number = len(session.exec(select(models.Application)).all()) + 1
        no = f"FAKE-SEED-{number:04}"
        identity = {}
        if verified:
            pledge = storage / "signatures" / f"{no}_identity_pledge.png"
            pledge.parent.mkdir(exist_ok=True)
            pledge.write_bytes(b"FAKE-original-identity-pledge")
            identity = {"name": PRIVATE_NAME, "birth": PRIVATE_BIRTH,
                        "phone": "010-****-0000", "method": "demo",
                        "verified_at": "2026-11-13T12:00:00",
                        "pledge_signature_path": str(pledge.relative_to(storage.parent)),
                        "pledge_signature_kind": "electronic"}
        app = models.Application(application_no=no, program_code=program,
                                 identity_json=identity,
                                 form1_json=applications._lock_identity({}, identity),
                                 created_at=created_at or datetime.now())
        session.add(app)
        session.commit()
        session.refresh(app)
        return app.id


def get_application(aid):
    return common.load_application(aid)


def snapshot(root):
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob("*") if path.is_file()}


@pytest.mark.parametrize("program", [DOUBLE_SAVINGS, JOB_PACKAGE])
def test_marker_projection_gate(isolated, program):
    """Prove the marker is safe before introducing the seeding implementation."""
    aid = make_application(isolated, program=program)
    app = get_application(aid)
    before_complete = {name: forms._form_is_complete(app, name)
                       for name in forms.available_forms(app)}
    before_blockers = review.final_check(aid)["blockers"]
    app.form1_json = {**app.form1_json, MARKER_KEY: MARKER_VALUE}
    with models.get_session() as session:
        session.add(app)
        session.commit()
    app = get_application(aid)
    assert {name: forms._form_is_complete(app, name)
            for name in forms.available_forms(app)} == before_complete
    assert review.final_check(aid)["blockers"] == before_blockers
    output = applications.self_check(aid, applications.SelfCheckRequest(answers={}))
    assert MARKER_KEY not in json.dumps(output) and MARKER_VALUE not in json.dumps(output)
    exported_path, count = forms.snapshot_written_pdf(app)
    assert count == len(forms.available_forms(app))
    exported = isolated.parent / exported_path
    assert exported.parent == isolated / "forms_exports"
    raw = exported.read_bytes()
    with pymupdf.open(stream=raw, filetype="pdf") as pdf:
        text = "".join(page.get_text() for page in pdf)
    for marker in (MARKER_KEY, MARKER_VALUE):
        assert marker.encode() not in raw and marker not in text
        assert marker not in json.dumps(review.final_check(aid), ensure_ascii=False, default=str)
    with models.get_session() as session:
        app = session.get(models.Application, aid)
        app.status = models.STATUS_SUBMITTED
        session.add(app)
        session.commit()
    detail = officer.review_detail(aid, role="province")
    listing = officer.list_applications(role="province", status=None, ai_status=None,
                                       sort="submitted", page=1, page_size=20)
    for marker in (MARKER_KEY, MARKER_VALUE):
        assert marker not in json.dumps([detail, listing], ensure_ascii=False, default=str)


@pytest.fixture
def tool(isolated, monkeypatch):
    from demo.backend.tools import seed_application
    monkeypatch.setattr(seed_application, "EXPECTED_DB_PATH", Path(models.engine.url.database))
    return seed_application


def assert_private(captured):
    assert captured.err == ""
    assert PRIVATE_NAME not in captured.out
    assert PRIVATE_BIRTH not in captured.out
    assert "010-****-0000" not in captured.out


@pytest.mark.parametrize("program", [DOUBLE_SAVINGS, JOB_PACKAGE])
def test_seed_identity_only_and_exact_blockers(tool, isolated, program, capfd):
    aid = make_application(isolated, program=program)
    original = deepcopy(get_application(aid).identity_json)
    pledge = isolated.parent / original["pledge_signature_path"]
    pledge_bytes = pledge.read_bytes()
    assert tool.main(["--application-id", str(aid)]) == 0
    captured = capfd.readouterr()
    assert_private(captured)
    assert f"신청 ID: {aid}\n" in captured.out
    assert "1단계를 한 같은 탭 주소창에 http://localhost:5173/apply/upload 입력\n" in captured.out
    assert "처리 신청: 1\n" in captured.out
    expected_category = "미선택(3단계에서 선택)" if program == DOUBLE_SAVINGS else "해당 없음"
    assert f"근로유형: {expected_category}\n" in captured.out
    app = get_application(aid)
    assert app.identity_json == original and pledge.read_bytes() == pledge_bytes
    expected_birth = {"y": "1990", "m": "7", "d": "19"}
    assert app.form1_json["name"] == app.form5_json["name"] == original["name"]
    assert app.form1_json["birth"] == app.form5_json["birth"] == expected_birth
    assert app.form1_json[MARKER_KEY] == MARKER_VALUE
    assert app.form1_json["email"] == "seed@example.com"
    assert app.doc_context_json == {}
    assert tool._complete(app)
    assert all(forms._form_is_complete(app, name) for name in forms.available_forms(app))
    blockers = review.final_check(aid)["blockers"]
    actual = {(row["kind"], row["target"] if row["kind"] != "document" else "missing_upload") for row in blockers}
    expected = {("document", "missing_upload")}
    if program == DOUBLE_SAVINGS:
        expected.add(("context", "work_category"))
    assert actual == expected
    assert all(row["message"].endswith("아직 올리지 않았습니다.") for row in blockers if row["kind"] == "document")
    consents = common.list_consents(aid)
    assert all(row.agreed for row in consents)
    admin = next((row for row in consents if row.consent_type == "admin_info"), None)
    if admin:
        from PIL import Image
        with Image.open(isolated.parent / admin.signature_path) as image:
            assert image.format == "PNG" and image.size == (240, 80)
    # A person-completed application has no seed marker; reject it too.
    with models.get_session() as session:
        row = session.get(models.Application, aid)
        row.form1_json = {key: value for key, value in row.form1_json.items() if key != MARKER_KEY}
        session.add(row)
        session.commit()
    before = snapshot(isolated.parent)
    assert tool.main(["--application-id", str(aid)]) == 2
    assert capfd.readouterr().out == "error: STAGE_TWO_COMPLETE\n"
    assert snapshot(isolated.parent) == before


@pytest.mark.parametrize("program", [DOUBLE_SAVINGS, JOB_PACKAGE])
def test_default_address_passes_submission_region_judgment(tool, isolated, program, capfd):
    from demo.backend.engine_adapter import apply_runtime_overrides, to_engine_applicant
    from demo.backend.rules.facts import build_facts, extract_region
    from demo.backend.rules.programs import get_program
    from engine.stage2_eligibility_check import run_stage2
    aid = make_application(isolated, program=program)
    assert tool.main(["--application-id", str(aid)]) == 0
    capfd.readouterr()
    app = get_application(aid)
    configured = get_program(app.program_code)
    address = app.form1_json["address"]
    assert configured.target_regions[0] in address and "가상주소" in address
    applicant = to_engine_applicant(application_no=app.application_no, name=app.form1_json["name"],
        birth_date=build_facts(app.form1_json, []).birth_date,
        residence_region=extract_region(address, configured.target_regions),
        program=configured, income_percent=None)
    apply_runtime_overrides()
    result = run_stage2(applicant)
    assert result.status.value == "PASS"
    assert not any(finding.code.value == "NOT_TARGET_REGION" for finding in result.findings)


def test_address_frontend_override_and_preserved_upload_context(tool, isolated, capfd):
    aid = make_application(isolated)
    with models.get_session() as session:
        app = session.get(models.Application, aid)
        app.doc_context_json = {"work_category": "직장가입자", "workplace_count": 2}
        session.add(app)
        session.commit()
    assert tool.main(["--address", "전북특별자치도 익산시 SEED 가상주소 0",
                      "--frontend-url", "http://127.0.0.1:5175/", "--application-id", str(aid)]) == 0
    captured = capfd.readouterr()
    assert_private(captured)
    assert "근로유형: 직장가입자\n" in captured.out
    assert "http://127.0.0.1:5175/apply/upload 입력\n" in captured.out
    app = get_application(aid)
    assert app.form1_json["address"] == "전북특별자치도 익산시 SEED 가상주소 0"
    assert app.doc_context_json == {"work_category": "직장가입자", "workplace_count": 2}


def test_default_selection_skips_unverified_complete_and_submitted(tool, isolated, capfd):
    older = make_application(isolated, created_at=datetime.now() - timedelta(days=3))
    newest = make_application(isolated, created_at=datetime.now() - timedelta(days=2))
    complete = make_application(isolated, created_at=datetime.now() - timedelta(days=1))
    assert tool.main(["--application-id", str(complete)]) == 0
    capfd.readouterr()
    make_application(isolated, verified=False)
    submitted = make_application(isolated)
    with models.get_session() as session:
        app = session.get(models.Application, submitted)
        app.status = models.STATUS_SUBMITTED
        session.add(app)
        session.commit()
    assert tool.main([]) == 0
    assert f"신청 ID: {newest}\n" in capfd.readouterr().out
    assert MARKER_KEY not in get_application(older).form1_json
    assert MARKER_KEY not in get_application(submitted).form1_json


@pytest.mark.parametrize("case,code", [("absent", "APPLICATION_NOT_FOUND"),
                                        ("unverified", "IDENTITY_REQUIRED"),
                                        ("malformed", "IDENTITY_REQUIRED"),
                                        ("submitted", "DRAFT_REQUIRED"),
                                        ("empty", "NO_APPLICATION")])
def test_invalid_target_is_unchanged(tool, isolated, case, code, capfd):
    args = []
    if case != "empty":
        aid = make_application(isolated, verified=case != "unverified")
        args = ["--application-id", str(aid + 1 if case == "absent" else aid)]
        if case in {"malformed", "submitted"}:
            with models.get_session() as session:
                app = session.get(models.Application, aid)
                if case == "malformed":
                    app.identity_json = {"name": PRIVATE_NAME, "birth": "wrong"}
                else:
                    app.status = models.STATUS_SUBMITTED
                session.add(app)
                session.commit()
    before = snapshot(isolated.parent)
    assert tool.main(args) == 2
    captured = capfd.readouterr()
    assert_private(captured)
    assert captured.out == f"error: {code}\n"
    assert snapshot(isolated.parent) == before


@pytest.mark.parametrize("args", [["--work-category", "직장가입자"], ["--application-id", "private-invalid"],
    ["--application-id", "0"], ["--address", " "], ["--frontend-url", "javascript:private"],
    ["--frontend-url", "http://localhost:5173/?private=1"]])
def test_arguments_only_fixed_error(tool, isolated, args, capfd):
    before = snapshot(isolated.parent)
    assert tool.main(args) == 2
    captured = capfd.readouterr()
    assert captured.out == "error: ARGUMENT_ERROR\n"
    assert_private(captured)
    assert snapshot(isolated.parent) == before


@pytest.mark.parametrize("database", ["other", "memory", "uri", "symlink", "missing"])
def test_database_guard_before_connection(tool, isolated, database, monkeypatch, capfd):
    from sqlalchemy import event
    expected = tool.EXPECTED_DB_PATH
    target = expected.parent / "other.db"
    if database == "other":
        url = f"sqlite:///{target}"
    elif database == "memory":
        url = "sqlite://"
    elif database == "uri":
        url = f"sqlite:///{expected}?mode=rw&uri=true"
    elif database == "symlink":
        target.symlink_to(expected)
        monkeypatch.setattr(tool, "EXPECTED_DB_PATH", target)
        url = f"sqlite:///{target}"
    else:
        target = expected.parent / "missing.db"
        monkeypatch.setattr(tool, "EXPECTED_DB_PATH", target)
        url = f"sqlite:///{target}"
    replacement = create_engine(url)
    monkeypatch.setattr(models, "engine", replacement)
    def forbidden(*args):
        pytest.fail("Guard must reject before opening a database connection")
    event.listen(replacement, "connect", forbidden)
    before = snapshot(isolated.parent)
    assert tool.main([]) == 2
    captured = capfd.readouterr()
    assert captured.out == f"error: {'DEMO_DB_MISSING' if database == 'missing' else 'DEMO_DB_REQUIRED'}\n"
    assert captured.err == "" and snapshot(isolated.parent) == before
    replacement.dispose()


@pytest.mark.parametrize("failure", ["exception", "interrupt"])
def test_late_handler_failure_rolls_back_all_rows_and_files(tool, isolated, monkeypatch, capfd, failure):
    from demo.backend.api import subsidy
    aid = make_application(isolated, program=JOB_PACKAGE)
    original = get_application(aid).model_dump()
    before = snapshot(isolated.parent)
    real_save = subsidy.save_subsidy_items
    def broken(*args, **kwargs):
        real_save(*args, **kwargs)
        print(PRIVATE_NAME)
        import os
        os.write(2, PRIVATE_BIRTH.encode())
        if failure == "interrupt":
            raise KeyboardInterrupt()
        raise RuntimeError(PRIVATE_NAME + PRIVATE_BIRTH)
    monkeypatch.setattr(subsidy, "save_subsidy_items", broken)
    assert tool.main(["--application-id", str(aid)]) == 2
    captured = capfd.readouterr()
    assert_private(captured)
    assert captured.out == f"error: {'INTERRUPTED' if failure == 'interrupt' else 'SEED_ERROR'}\n"
    assert get_application(aid).model_dump() == original
    assert common.list_consents(aid) == [] and common.subsidy_rows(aid) == []
    assert snapshot(isolated.parent) == before
    # The context-local override must be reset after failure.
    with models.get_session() as session:
        assert session.bind is models.engine


def test_signature_overwrite_restored_on_failure(tool, isolated, monkeypatch, capfd):
    aid = make_application(isolated)
    app = get_application(aid)
    signature = isolated / "signatures" / f"{app.application_no}_admin_info.png"
    signature.write_bytes(b"FAKE-existing-signature")
    before = snapshot(isolated.parent)
    real_save = applications.save_consents
    def broken(*args):
        real_save(*args)
        assert signature.read_bytes() != b"FAKE-existing-signature"
        raise RuntimeError(PRIVATE_NAME)
    monkeypatch.setattr(applications, "save_consents", broken)
    assert tool.main(["--application-id", str(aid)]) == 2
    assert_private(capfd.readouterr())
    assert snapshot(isolated.parent) == before


def test_partial_stage_scan_uses_fake_electronic_signature_on_restore(tool, isolated, capfd):
    from demo.backend.forms.signature_scan import signature_scan_paths
    aid = make_application(isolated)
    original_app = get_application(aid)
    original, processed = signature_scan_paths(isolated, original_app.application_no)
    original.parent.mkdir()
    original.with_suffix(".jpg").write_bytes(b"FAKE-existing-stage-two-original")
    processed.write_bytes(b"FAKE-existing-stage-two-processed")
    pledge = isolated.parent / original_app.identity_json["pledge_signature_path"]
    pledge_bytes = pledge.read_bytes()
    assert tool.main(["--application-id", str(aid)]) == 0
    assert_private(capfd.readouterr())
    app = get_application(aid)
    assert not app.form5_json["signatureScanUploaded"]
    assert app.form5_json["signature"].startswith("data:image/png;base64,")
    assert not processed.exists() and list(original.parent.glob("scan-original.*")) == []
    admin = next(row for row in common.list_consents(aid) if row.consent_type == "admin_info")
    assert admin.signature_kind == "electronic"
    assert app.identity_json == original_app.identity_json and pledge.read_bytes() == pledge_bytes


def test_partial_stage_scan_restored_after_handler_failure(tool, isolated, monkeypatch, capfd):
    from demo.backend.forms.signature_scan import signature_scan_paths
    aid = make_application(isolated)
    app = get_application(aid)
    original, processed = signature_scan_paths(isolated, app.application_no)
    original.parent.mkdir()
    original.with_suffix(".jpg").write_bytes(b"FAKE-existing-original-jpg")
    original.with_suffix(".png").write_bytes(b"FAKE-existing-original-png")
    processed.write_bytes(b"FAKE-existing-processed")
    before = snapshot(isolated.parent)
    real_save = applications.save_consents
    def broken(*args):
        real_save(*args)
        assert not processed.exists()
        raise RuntimeError(PRIVATE_NAME)
    monkeypatch.setattr(applications, "save_consents", broken)
    assert tool.main(["--application-id", str(aid)]) == 2
    assert_private(capfd.readouterr())
    assert snapshot(isolated.parent) == before


def test_service_transaction_default_commits_and_nested_refusal(isolated):
    with models.get_session() as session:
        assert session.bind is models.engine
    with pytest.raises(RuntimeError, match="Nested"):
        with models.session_transaction():
            with models.session_transaction():
                pass
    with models.get_session() as session:
        assert session.bind is models.engine


def test_cleanup_all_rows_files_shared_and_unrelated_preserved(tool, isolated, capfd):
    seeded = make_application(isolated)
    other_seeded = make_application(isolated, program=JOB_PACKAGE)
    untouched = make_application(isolated)
    for aid in (seeded, other_seeded):
        assert tool.main(["--application-id", str(aid)]) == 0
    capfd.readouterr()
    unmarked = get_application(untouched).model_dump()
    keep_path = isolated / "documents" / "FAKE-unrelated" / "keep.pdf"
    keep_path.parent.mkdir(parents=True)
    keep_path.write_bytes(b"FAKE-keep")
    app = get_application(seeded)
    own_folder = isolated / "documents" / app.application_no / "slot"
    own_folder.mkdir(parents=True)
    own_upload = own_folder / "new.pdf"
    own_upload.write_bytes(b"FAKE-upload")
    merged = own_folder / "source.pdf"
    merged.write_bytes(b"FAKE-merged-original")
    shared = own_folder / "shared.pdf"
    shared.write_bytes(b"FAKE-shared")
    scan = isolated / "signatures" / app.application_no
    scan.mkdir()
    (scan / "scan-original.png").write_bytes(b"FAKE-scan")
    (scan / "scan-processed.png").write_bytes(b"FAKE-processed")
    export = isolated / "forms_exports"
    export.mkdir()
    (export / f"{app.application_no}.pdf").write_bytes(b"FAKE-export")
    (export / f"{app.application_no}.pdf.tmp").write_bytes(b"FAKE-export-temp")
    with models.get_session() as session:
        for aid, path in ((seeded, own_upload), (seeded, shared), (untouched, shared), (untouched, keep_path)):
            session.add(models.Document(application_id=aid, slot_key="fake", file_path=str(path.relative_to(isolated.parent)),
                source_file_path=str(merged.relative_to(isolated.parent)) if path == own_upload else None, file_format="pdf"))
        session.add(models.Review(application_id=seeded, final_status="NEEDS_REVIEW"))
        session.commit()
    assert tool.main(["--clean"]) == 0
    captured = capfd.readouterr()
    assert_private(captured)
    assert "삭제 신청: 2\n" in captured.out
    with models.get_session() as session:
        assert [app.id for app in session.exec(select(models.Application)).all()] == [untouched]
        for kind in (models.Consent, models.Document, models.SubsidyItem, models.Review):
            assert all(row.application_id == untouched for row in session.exec(select(kind)).all())
    assert get_application(untouched).model_dump() == unmarked
    assert shared.read_bytes() == b"FAKE-shared" and keep_path.read_bytes() == b"FAKE-keep"
    assert not own_upload.exists() and not merged.exists() and not scan.exists()
    assert list(export.iterdir()) == []
    assert (isolated.parent / unmarked["identity_json"]["pledge_signature_path"]).is_file()
    assert tool.main(["--clean"]) == 0
    assert capfd.readouterr().out == "삭제 신청: 0\n삭제 행: 0\n삭제 파일: 0\n"


def test_clean_id_does_not_expand_to_all(tool, isolated, capfd):
    aid = make_application(isolated)
    untouched = make_application(isolated)
    assert tool.main(["--application-id", str(aid)]) == 0
    capfd.readouterr()
    before = snapshot(isolated.parent)
    assert tool.main(["--clean", "--application-id", str(untouched)]) == 2
    assert capfd.readouterr().out == "error: NOT_SEEDED\n"
    assert snapshot(isolated.parent) == before
    assert tool.main(["--clean", "--application-id", str(aid)]) == 0
    assert "삭제 신청: 1\n" in capfd.readouterr().out
    assert get_application(untouched)


def test_cleanup_failure_restores_files_and_database(tool, isolated, monkeypatch, capfd):
    aid = make_application(isolated)
    assert tool.main(["--application-id", str(aid)]) == 0
    capfd.readouterr()
    before = snapshot(isolated.parent)
    from sqlmodel import Session
    def fail(*args):
        raise RuntimeError(PRIVATE_NAME)
    monkeypatch.setattr(Session, "commit", fail)
    assert tool.main(["--clean"]) == 2
    assert_private(capfd.readouterr())
    assert snapshot(isolated.parent) == before


@pytest.mark.parametrize("missing", ["transferIn", "employedAt", "receipt"])
def test_final_check_stage_two_requirements_affect_completion(tool, isolated, capfd, missing):
    program = JOB_PACKAGE if missing == "receipt" else DOUBLE_SAVINGS
    aid = make_application(isolated, program=program)
    assert tool.main(["--application-id", str(aid)]) == 0
    capfd.readouterr()
    with models.get_session() as session:
        app = session.get(models.Application, aid)
        if missing == "receipt":
            for row in session.exec(select(models.SubsidyItem)).all():
                session.delete(row)
            session.add(models.SubsidyItem(application_id=aid, item_type="photo", count_index=1))
        else:
            app.form1_json = {key: value for key, value in app.form1_json.items() if key != missing}
            session.add(app)
        session.commit()
    assert not tool._complete(get_application(aid))
    assert tool.main(["--application-id", str(aid)]) == 0
    assert_private(capfd.readouterr())
    assert tool._complete(get_application(aid))


def test_paper_signature_complete_is_rejected_incomplete_uses_electronic(tool, isolated, capfd):
    aid = make_application(isolated)
    app = get_application(aid)
    with models.get_session() as session:
        app.doc_context_json = {"work_category": "직장가입자", "workplace_count": 2,
                                "paper_forms": {"서식5": True}}
        session.add(app)
        session.commit()
    assert tool.main(["--application-id", str(aid)]) == 0
    capfd.readouterr()
    app = get_application(aid)
    assert app.doc_context_json["work_category"] == "직장가입자"
    assert app.doc_context_json["workplace_count"] == 2
    assert app.doc_context_json["paper_forms"] == {"서식5": False}
    # A genuinely complete paper-mode stage two need not have electronic admin consent.
    paper = isolated / "documents" / app.application_no / "admin_info_consent" / "FAKE.pdf"
    paper.parent.mkdir(parents=True)
    paper.write_bytes(b"FAKE-paper-consent")
    with models.get_session() as session:
        app = session.get(models.Application, aid)
        app.doc_context_json = {**app.doc_context_json, "paper_forms": {"서식5": True}}
        session.add(app)
        for row in session.exec(select(models.Consent).where(models.Consent.consent_type == "admin_info")).all():
            session.delete(row)
        session.add(models.Document(application_id=aid, slot_key="admin_info_consent",
            file_path=str(paper.relative_to(isolated.parent)), file_format="pdf", stage1_status="PASS"))
        session.commit()
    assert tool._complete(get_application(aid))
    before = snapshot(isolated.parent)
    assert tool.main(["--application-id", str(aid)]) == 2
    assert capfd.readouterr().out == "error: STAGE_TWO_COMPLETE\n"
    assert snapshot(isolated.parent) == before


@pytest.mark.parametrize("case", ["outside_namespace", "outside_storage", "symlink"])
def test_unsafe_cleanup_is_unchanged(tool, isolated, capfd, case):
    aid = make_application(isolated)
    assert tool.main(["--application-id", str(aid)]) == 0
    capfd.readouterr()
    app = get_application(aid)
    outsider = isolated / "FAKE-unrelated-orphan.pdf" if case != "outside_storage" else isolated.parent / "FAKE-private.pdf"
    outsider.write_bytes(b"FAKE-unrelated-preserve")
    if case == "symlink":
        path = isolated / "documents" / app.application_no
        path.parent.mkdir()
        path.symlink_to(isolated, target_is_directory=True)
    else:
        with models.get_session() as session:
            session.add(models.Document(application_id=aid, slot_key="fake",
                                        file_path=str(outsider), file_format="pdf"))
            session.commit()
    before = snapshot(isolated.parent)
    assert tool.main(["--clean"]) == 2
    assert capfd.readouterr().out == "error: STORAGE_UNSAFE\n"
    assert outsider.read_bytes() == b"FAKE-unrelated-preserve"
    assert snapshot(isolated.parent) == before


def test_cleanup_when_storage_was_already_removed(tool, isolated, capfd):
    import shutil
    aid = make_application(isolated)
    assert tool.main(["--application-id", str(aid)]) == 0
    capfd.readouterr()
    shutil.rmtree(isolated)
    assert tool.main(["--clean"]) == 0
    assert "삭제 파일: 0\n" in capfd.readouterr().out
    with models.get_session() as session:
        assert session.exec(select(models.Application)).all() == []


@pytest.mark.parametrize("program", [DOUBLE_SAVINGS, JOB_PACKAGE])
def test_filled_marker_never_leaks_into_exports_or_validation(tool, isolated, program, capfd):
    aid = make_application(isolated, program=program)
    assert tool.main(["--application-id", str(aid)]) == 0
    capfd.readouterr()
    app = get_application(aid)
    path, _ = forms.snapshot_written_pdf(app)
    raw = (isolated.parent / path).read_bytes()
    with pymupdf.open(stream=raw, filetype="pdf") as exported:
        text = "".join(page.get_text() for page in exported)
    result = review.final_check(aid)
    for marker in (MARKER_KEY, MARKER_VALUE):
        assert marker.encode() not in raw and marker not in text
        assert marker not in json.dumps(result, ensure_ascii=False, default=str)
    # Existing applicant save/read echoes intentionally retain the raw JSON contract.
    assert applications.read(aid)["form1_json"][MARKER_KEY] == MARKER_VALUE
    assert tool._complete(app)
    app.form1_json = {key: value for key, value in app.form1_json.items() if key != MARKER_KEY}
    with models.get_session() as session:
        session.add(app)
        session.commit()
    assert tool._complete(get_application(aid))
    assert review.final_check(aid)["blockers"] == result["blockers"]


def test_completed_legacy_criteria_lookup_cannot_mutate_on_refusal(tool, isolated, capfd):
    aid = make_application(isolated)
    assert tool.main(["--application-id", str(aid)]) == 0
    capfd.readouterr()
    with models.get_session() as session:
        for row in session.exec(select(models.ProgramCriteriaVersion)).all():
            session.delete(row)
        session.commit()
    before = snapshot(isolated.parent)
    assert tool.main(["--application-id", str(aid)]) == 2
    assert capfd.readouterr().out == "error: STAGE_TWO_COMPLETE\n"
    assert snapshot(isolated.parent) == before
    with models.get_session() as session:
        assert session.exec(select(models.ProgramCriteriaVersion)).all() == []


def test_frontend_path_override_rejected(tool, isolated, capfd):
    before = snapshot(isolated.parent)
    assert tool.main(["--frontend-url", "http://localhost:5173/nested"]) == 2
    assert capfd.readouterr().out == "error: ARGUMENT_ERROR\n"
    assert snapshot(isolated.parent) == before


@pytest.mark.parametrize("program", [DOUBLE_SAVINGS, JOB_PACKAGE])
def test_frontend_shaped_patch_without_marker_is_missed_by_cleanup(tool, isolated, capfd, program):
    """Document the existing whole-form replacement contract, without changing it."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    aid = make_application(isolated, program=program)
    assert tool.main(["--application-id", str(aid)]) == 0
    capfd.readouterr()
    app = get_application(aid)
    identity = deepcopy(app.identity_json)
    body = {"form1": {key: value for key, value in app.form1_json.items() if key != MARKER_KEY},
            "self_check": deepcopy(app.self_check_json), "form5": deepcopy(app.form5_json)}
    api = FastAPI()
    api.include_router(applications.router)
    with TestClient(api) as client:
        response = client.patch(f"/api/applications/{aid}", json=body)
    assert response.status_code == 200
    assert MARKER_KEY not in response.json()["form1_json"]
    assert MARKER_KEY not in get_application(aid).form1_json
    assert get_application(aid).identity_json == identity
    rows_before = {kind: [row.model_dump() for row in _rows_for_application(kind, aid)]
                   for kind in (models.Consent, models.Document, models.SubsidyItem, models.Review)}
    before_clean = snapshot(isolated.parent)
    capfd.readouterr()
    assert tool.main(["--clean"]) == 0
    assert capfd.readouterr().out == "삭제 신청: 0\n삭제 행: 0\n삭제 파일: 0\n"
    assert get_application(aid).identity_json == identity
    for kind, rows in rows_before.items():
        assert [row.model_dump() for row in _rows_for_application(kind, aid)] == rows
    assert snapshot(isolated.parent) == before_clean
    assert tool.main(["--clean", "--application-id", str(aid)]) == 2
    assert capfd.readouterr().out == "error: NOT_SEEDED\n"
    assert snapshot(isolated.parent) == before_clean


def _rows_for_application(kind, application_id):
    with models.get_session() as session:
        return session.exec(select(kind).where(kind.application_id == application_id)).all()


@pytest.mark.parametrize("failure", ["after_consent", "partial_signature_write", "outer_commit"])
def test_new_placeholder_file_is_removed_on_rollback(tool, isolated, monkeypatch, capfd, failure):
    """Fail after actual PNG creation, including partial writes and outer commit."""
    from sqlalchemy import event

    aid = make_application(isolated)
    app = get_application(aid)
    signature = isolated / "signatures" / f"{app.application_no}_admin_info.png"
    assert not signature.exists()
    original = app.model_dump()
    before = snapshot(isolated.parent)
    observed = []

    if failure == "after_consent":
        real_save = applications.save_consents

        def broken(*args, **kwargs):
            real_save(*args, **kwargs)
            observed.append(signature.read_bytes())
            raise RuntimeError(PRIVATE_NAME)

        monkeypatch.setattr(applications, "save_consents", broken)
    elif failure == "partial_signature_write":
        real_write = Path.write_bytes

        def broken(path, data):
            if path == signature:
                real_write(path, data[:16])
                observed.append(path.read_bytes())
                raise OSError(PRIVATE_NAME)
            return real_write(path, data)

        monkeypatch.setattr(Path, "write_bytes", broken)
    else:
        def broken(connection):
            observed.append(signature.read_bytes())
            raise RuntimeError(PRIVATE_NAME)

        event.listen(models.engine, "commit", broken)
    try:
        assert tool.main(["--application-id", str(aid)]) == 2
    finally:
        if failure == "outer_commit":
            event.remove(models.engine, "commit", broken)
    captured = capfd.readouterr()
    assert_private(captured)
    assert captured.out == "error: SEED_ERROR\n"
    assert observed and observed[0].startswith(b"\x89PNG")
    assert not signature.exists()
    assert get_application(aid).model_dump() == original
    assert common.list_consents(aid) == []
    assert snapshot(isolated.parent) == before

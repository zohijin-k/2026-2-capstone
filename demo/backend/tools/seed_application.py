"""Fill stage two of an already identity-verified demo application.

Run with python -B -m. This is a single-threaded developer CLI: dependency
stdout/stderr (including native output) is discarded. Identity is never created
or modified; --clean explicitly deletes the entire marked test application.
"""
from __future__ import annotations

import sys
sys.dont_write_bytecode = True

import argparse
import base64
from contextlib import contextmanager
import io
import logging
from pathlib import Path
import tempfile
from urllib.parse import urlsplit

EXPECTED_DB_PATH = Path(__file__).resolve().parents[2] / "demo.db"
MARKER_KEY = "_seed_application"
MARKER_VALUE = "seed-application-v1"
ERROR_CODES = frozenset({"ARGUMENT_ERROR", "DEMO_DB_REQUIRED", "DEMO_DB_MISSING",
                         "APPLICATION_NOT_FOUND", "IDENTITY_REQUIRED", "STAGE_TWO_COMPLETE",
                         "DRAFT_REQUIRED", "NO_APPLICATION", "NOT_SEEDED", "STORAGE_UNSAFE",
                         "SEED_ERROR", "INTERRUPTED"})


class SeedError(Exception):
    """Only fixed error codes may cross the output boundary."""


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        raise SeedError("ARGUMENT_ERROR")


@contextmanager
def quiet_dependencies():
    from engine_v2.tools.private_bench import quiet_dependencies as quiet
    disabled = logging.root.manager.disable
    logging.disable(sys.maxsize)
    try:
        with quiet():
            yield
    finally:
        logging.disable(disabled)


def parser():
    p = SafeParser(prog="seed_application", description="데모 신청 2단계 시험값 채우기")
    p.add_argument("--application-id", type=int, metavar="ID")
    p.add_argument("--frontend-url", default="http://localhost:5173", metavar="URL")
    p.add_argument("--address", metavar="ADDRESS")
    p.add_argument("--clean", action="store_true")
    return p


def _guard_database():
    from .. import models
    url = models.engine.url
    wanted = EXPECTED_DB_PATH.absolute()
    if (url.drivername != "sqlite" or url.host or url.query or not url.database
            or Path(url.database).absolute() != wanted
            or wanted.is_symlink() or wanted.resolve() != wanted):
        raise SeedError("DEMO_DB_REQUIRED")
    if not wanted.is_file():
        raise SeedError("DEMO_DB_MISSING")


def _complete(app):
    """Ask existing validators rather than reimplementing form requirements."""
    from ..api.forms import _form_is_complete
    from ..api.review import _blockers
    from ..forms.values import available_forms
    from ..rules.self_check import evaluate
    if not evaluate(app.self_check_json or {}, app.program_code).eligible:
        return False
    if not all(_form_is_complete(app, name) for name in available_forms(app)):
        return False
    return not any(
        row["kind"] in {"form", "consent", "subsidy"} for row in _blockers(app))


def _verified(app):
    from ..rules.identity import identity_of
    identity = identity_of(app.identity_json)
    raw = app.identity_json or {}
    return bool(identity and identity.name and raw.get("verified_at")
                and raw.get("pledge_signature_path") and raw.get("method"))


def _select(application_id):
    from sqlmodel import select
    from .. import models
    with models.get_session() as session:
        if application_id is not None:
            app = session.get(models.Application, application_id)
            if app is None:
                raise SeedError("APPLICATION_NOT_FOUND")
            if not _verified(app):
                raise SeedError("IDENTITY_REQUIRED")
            if app.status != models.STATUS_DRAFT:
                raise SeedError("DRAFT_REQUIRED")
            if _complete(app):
                raise SeedError("STAGE_TWO_COMPLETE")
            return app
        rows = session.exec(select(models.Application).where(
            models.Application.status == models.STATUS_DRAFT
        ).order_by(models.Application.created_at.desc(), models.Application.id.desc())).all()
        for app in rows:
            if _verified(app) and not _complete(app):
                return app
    raise SeedError("NO_APPLICATION")


def _safe_no(app):
    no = app.application_no
    if not no or no in {".", ".."} or Path(no).name != no or "/" in no or "\\" in no:
        raise SeedError("STORAGE_UNSAFE")
    return no


def _owned_path(path, storage):
    path = Path(path).absolute()
    root = storage.absolute()
    if (root.is_symlink() or root.resolve() != root or root not in path.parents
            or path.resolve() != path):
        raise SeedError("STORAGE_UNSAFE")
    return path


def _signature():
    from PIL import Image, ImageDraw
    output = io.BytesIO()
    image = Image.new("RGB", (240, 80), "white")
    ImageDraw.Draw(image).text((12, 25), "SEED / FAKE SIGNATURE", fill="black")
    image.save(output, format="PNG")
    return "data:image/png;base64," + base64.b64encode(output.getvalue()).decode("ascii")


def _values(app, address):
    from ..rules.programs import get_program
    program = get_program(app.program_code)
    raw = app.identity_json
    year, month, day = raw["birth"].split("-")
    birth = {"y": year, "m": str(int(month)), "d": str(int(day))}
    signature = _signature()
    form1 = {**(app.form1_json or {}),
             "name": raw["name"], "birth": birth,
             "address": address or f"전북특별자치도 {program.target_regions[0]} 가짜시험로 0 (SEED 시험용 가상주소)",
             "mobile": "010-0000-0000", "email": "seed@example.com",
             "bankName": "가짜은행(SEED)", "accountNo": "000-000000-00000",
             "accountHolder": raw["name"], "bankbookFileName": "SEED-FAKE-bankbook.png",
             "savingPurpose": "기타 꿈을 위한 준비자금", "priorJoined": "미참여",
             "gender": "남", "householdType": "그 외 일반 가구", "householdSize": "1인",
             "workType": "기타(상용직, 임시직, 일용직 혼합)",
             "workplaceRegion": "전북특별자치도 내 지역",
             # These are synthetic scoring inputs, not evidence of residence/work.
             "transferIn": {"y": "2020", "m": "1", "d": "1"},
             "employedAt": {"y": "2020", "m": "1", "d": "1"},
             "job.signature": signature, "consent.job.signature": signature,
             "job.interview.1.company": "SEED 가짜회사", "job.interview.1.location": "SEED 가상면접장",
             "job.interview.1.date": "2026-01-01", MARKER_KEY: MARKER_VALUE}
    # Clear an incomplete optional contact group rather than inventing a person.
    for key in ("ecName", "ecRelation", "ecContact"):
        form1[key] = ""
    form5 = {"agree": "동의함", "name": raw["name"], "birth": birth,
             "phone": "010-0000-0000", "signature": signature}
    return form1, form5, signature


def _fill(app, address):
    from starlette.requests import Request
    from .. import models
    from ..api import applications, common, documents, forms, subsidy
    from ..forms.signature_scan import signature_scan_paths
    from ..rules.programs import get_program
    from ..rules.self_check import item_numbers
    program = get_program(app.program_code)
    no = _safe_no(app)
    form1, form5, signature = _values(app, address)
    # Retain overwritten consent signatures and replaced stage-two scans exactly.
    paths = [_owned_path(applications.SIGNATURES / f"{no}_{kind}.png", common.STORAGE)
             for kind in program.consent_types]
    scan_paths = []
    if "admin_info" in program.consent_types:
        original, processed = signature_scan_paths(common.STORAGE, no)
        _owned_path(original.parent, common.STORAGE)
        scan_paths = [_owned_path(path, common.STORAGE)
                      for path in original.parent.glob("scan-original.*")]
        scan_paths.append(_owned_path(processed, common.STORAGE))
        if any(path.exists() and not path.is_file() for path in scan_paths):
            raise SeedError("STORAGE_UNSAFE")
        paths.extend(scan_paths)
    previous = {path: path.read_bytes() if path.is_file() else None for path in paths}
    existed = applications.SIGNATURES.exists()
    try:
        with models.session_transaction():
            paper_forms = (app.doc_context_json or {}).get("paper_forms") or {}
            if paper_forms.get("서식5"):
                # This is a stage-two signing choice, not a work-category change.
                documents.set_doc_context(app.id, documents.DocContextRequest(
                    **{**(app.doc_context_json or {}), "paper_forms": {**paper_forms, "서식5": False}}))
            if any(previous[path] is not None for path in scan_paths):
                # Restore must select our electronic placeholder, not an old scan.
                forms.delete_signature_scan_route(app.id)
            applications.patch(app.id, applications.PatchRequest(form1=form1, form5=form5))
            applications.self_check(app.id, applications.SelfCheckRequest(
                answers={str(no): "예" for no in item_numbers(app.program_code)}))
            request = Request({"type": "http", "headers": [(b"user-agent", b"seed-application-v1")],
                               "client": ("127.0.0.1", 0)})
            applications.save_consents(app.id, applications.ConsentRequest(consents=[
                applications.ConsentItem(consent_type=kind, agreed=True,
                                         signature_data_url=signature if kind == "admin_info" else None,
                                         signature_kind="electronic" if kind == "admin_info" else None)
                for kind in program.consent_types]), request)
            if program.has_subsidy_items:
                subsidy.save_subsidy_items(app.id, subsidy.SubsidyRequest(items=[
                    subsidy.SubsidyItemRequest(item_type="interview", count=1)]))
            if not _complete(common.load_application(app.id)):
                raise SeedError("SEED_ERROR")
    except BaseException:
        for path, content in previous.items():
            if content is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(content)
        if not existed and applications.SIGNATURES.is_dir():
            applications.SIGNATURES.rmdir()
        raise


def _recorded_paths(app, consents, documents, storage):
    values = [app.written_forms_archive_path, (app.identity_json or {}).get("pledge_signature_path")]
    values.extend(c.signature_path for c in consents)
    for row in documents:
        values.extend([row.file_path, row.source_file_path])
    no = _safe_no(app)
    paths = {_owned_path(storage.parent / value, storage) for value in values if value}
    folders = (storage / "documents" / no, storage / "signatures" / no)
    exact = {storage / "signatures" / f"{no}_{kind}.{ext}"
             for kind in ("privacy", "unique_id", "third_party", "admin_info", "identity_pledge")
             for ext in ("png", "jpg", "pdf")}
    exact.update(storage / "forms_exports" / f"{no}.{ext}" for ext in ("pdf", "pdf.tmp"))
    if any(path not in exact and not any(folder in path.parents for folder in folders) for path in paths):
        raise SeedError("STORAGE_UNSAFE")
    return paths


def _clean(application_id):
    from sqlmodel import select
    from .. import models
    from ..api.common import STORAGE
    with models.get_session() as session:
        apps = session.exec(select(models.Application)).all()
        marked = [app for app in apps if (app.form1_json or {}).get(MARKER_KEY) == MARKER_VALUE
                  and (application_id is None or app.id == application_id)]
        if application_id is not None and not marked:
            raise SeedError("NOT_SEEDED")
        rows = {kind: session.exec(select(kind)).all()
                for kind in (models.Consent, models.Document, models.SubsidyItem, models.Review)}
        ids = {app.id for app in marked}
        protected = set()
        for app in apps:
            if app.id not in ids:
                # Unrelated historical paths may be outside storage; protect them
                # by resolving only, without requiring ownership or touching them.
                values = [app.written_forms_archive_path, (app.identity_json or {}).get("pledge_signature_path")]
                values += [row.signature_path for row in rows[models.Consent] if row.application_id == app.id]
                for row in rows[models.Document]:
                    if row.application_id == app.id:
                        values += [row.file_path, row.source_file_path]
                protected.update((STORAGE.parent / value).resolve() for value in values if value)
        candidates = set()
        folders = set()
        for app in marked:
            no = _safe_no(app)
            candidates.update(_recorded_paths(app,
                [row for row in rows[models.Consent] if row.application_id == app.id],
                [row for row in rows[models.Document] if row.application_id == app.id], STORAGE))
            for folder in (STORAGE / "documents" / no, STORAGE / "signatures" / no):
                _owned_path(folder, STORAGE)
                if folder.exists():
                    for item in folder.rglob("*"):
                        _owned_path(item, STORAGE)
                        if item.is_file():
                            candidates.add(item)
                        elif item.is_dir():
                            folders.add(item)
                    folders.add(folder)
            for kind in (*("privacy", "unique_id", "third_party", "admin_info"), "identity_pledge"):
                for ext in ("png", "jpg", "pdf"):
                    candidates.add(_owned_path(STORAGE / "signatures" / f"{no}_{kind}.{ext}", STORAGE))
            for ext in ("pdf", "pdf.tmp"):
                candidates.add(_owned_path(STORAGE / "forms_exports" / f"{no}.{ext}", STORAGE))
        candidates = sorted(path for path in candidates if path.is_file() and path.resolve() not in protected)
        if not marked:
            return 0, 0, 0
        # Move owned files aside first; restore on DB failure or interruption.
        moved = []
        with tempfile.TemporaryDirectory(prefix=".seed-clean-", dir=STORAGE.parent) as temporary:
            try:
                for index, path in enumerate(candidates):
                    dest = Path(temporary) / str(index)
                    path.replace(dest)
                    moved.append((path, dest))
                count = 0
                for kind_rows in rows.values():
                    for row in kind_rows:
                        if row.application_id in ids:
                            session.delete(row)
                            count += 1
                for app in marked:
                    session.delete(app)
                session.commit()
            except BaseException:
                session.rollback()
                for path, dest in reversed(moved):
                    dest.replace(path)
                raise
        for folder in sorted(folders, key=lambda p: len(p.parts), reverse=True):
            if folder.is_dir() and not any(folder.iterdir()):
                folder.rmdir()
        return len(marked), count + len(marked), len(moved)


def main(argv=None):
    try:
        args = parser().parse_args(argv)
        url = urlsplit(args.frontend_url)
        if (args.application_id is not None and args.application_id <= 0
                or not url.netloc or url.scheme not in {"http", "https"}
                or url.path not in {"", "/"} or url.query or url.fragment or url.username or url.password
                or any(c.isspace() for c in args.frontend_url)
                or args.address is not None and not args.address.strip()):
            raise SeedError("ARGUMENT_ERROR")
        with quiet_dependencies():
            _guard_database()
            if args.clean:
                apps, rows, files = _clean(args.application_id)
                output = f"삭제 신청: {apps}\n삭제 행: {rows}\n삭제 파일: {files}"
            else:
                from .. import models
                # Some historical criteria lookups lazily create defaults.
                # Selection is strictly read-only even when those helpers write.
                with models.session_transaction() as connection:
                    app = _select(args.application_id)
                    connection.rollback()
                _fill(app, args.address)
                from ..rules.programs import get_program
                from ..rules.required_docs import WorkCategory
                category = (app.doc_context_json or {}).get("work_category")
                category = category if category in {str(c) for c in WorkCategory} else "미선택(3단계에서 선택)"
                if not get_program(app.program_code).has_work_requirement:
                    category = "해당 없음"
                output = (f"신청 ID: {app.id}\n근로유형: {category}\n"
                          f"1단계를 한 같은 탭 주소창에 {args.frontend_url.rstrip('/')}/apply/upload 입력\n"
                          "처리 신청: 1")
        print(output)
        return 0
    except SeedError as exc:
        code = exc.args[0] if exc.args and exc.args[0] in ERROR_CODES else "SEED_ERROR"
        print(f"error: {code}")
        return 2
    except KeyboardInterrupt:
        print("error: INTERRUPTED")
        return 2
    except Exception:
        print("error: SEED_ERROR")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

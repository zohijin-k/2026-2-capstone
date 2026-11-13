"""Compare private case verdicts without recording document values.

Use ``python -B -m``. Case IDs must be nonidentifying ASCII labels. Relative
source paths are relative to the resolved manifest's directory. Assessments
are sequential because the shared quiet/read-only boundary is process global.
"""
from __future__ import annotations

import sys
sys.dont_write_bytecode = True

import json
import os
from pathlib import Path
import re
import subprocess
from types import SimpleNamespace
import uuid

from . import verify_upload as upload


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_ID = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}\Z")
_INCOME_FILES = ("payment", "qualification", "acquisition_loss")
_SEVERITIES = frozenset({"PASS", "FAIL", "NEEDS_REVIEW", "INFO", "X"})
_DOCUMENT_STATUSES = frozenset({"PASS", "FAIL", "NEEDS_REVIEW", "X"})
_INCOME_STATUSES = frozenset({"MET", "OVER_LIMIT", "UNDETERMINED", "X"})
_WORK_STATUSES = frozenset({"MET", "NOT_MET", "UNDETERMINED", "X"})


class CasesError(Exception):
    """An internal fixed diagnostic, never a dependency message."""


def _fail(code):
    raise CasesError(code)


def _private_location(path):
    """Apply repository policy to actual targets, including nonexistent outputs."""
    actual = Path(path).resolve()
    root = REPOSITORY_ROOT.resolve()
    if not actual.is_relative_to(root):
        return actual
    relative = str(actual.relative_to(root))
    result = subprocess.run(
        ["git", "check-ignore", "-q", "--", relative], cwd=root,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
    )
    # Default check-ignore semantics exclude tracked files, even force-added
    # ignored files. Never use --no-index here.
    if result.returncode != 0:
        _fail("LOCATION_REJECTED")
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", relative], cwd=root,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
    )
    if tracked.returncode != 1:
        _fail("LOCATION_REJECTED")
    return actual


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _fail("JSON_INVALID")
        result[key] = value
    return result


def _read_json(path, code):
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except (OSError, ValueError, CasesError):
        _fail(code)


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _manifest(path):
    raw = _read_json(path, "MANIFEST_INVALID")
    if (not isinstance(raw, dict) or set(raw) != {"schema_version", "cases"}
            or type(raw["schema_version"]) is not int or raw["schema_version"] != 1
            or not isinstance(raw["cases"], list) or not raw["cases"]):
        _fail("MANIFEST_INVALID")
    ids = set()
    common = {"id", "program", "work_category", "self_identity"}
    for case in raw["cases"]:
        if not isinstance(case, dict):
            _fail("MANIFEST_INVALID")
        case_id = case.get("id")
        if not isinstance(case_id, str) or not _ID.fullmatch(case_id) or case_id in ids:
            _fail("MANIFEST_INVALID")
        ids.add(case_id)
        if ("program" in case and not _text(case["program"])) or (
            case.get("work_category") is not None and not _text(case["work_category"])
        ) or ("self_identity" in case and type(case["self_identity"]) is not bool):
            _fail("MANIFEST_INVALID")
        if "income" in case:
            income = case["income"]
            valid = (set(case) <= common | {"income"} and isinstance(income, dict)
                     and set(income) == set(_INCOME_FILES)
                     and all(_text(value) for value in income.values()))
        else:
            valid = (set(case) <= common | {"slot", "file"}
                     and _text(case.get("slot")) and _text(case.get("file")))
        if not valid:
            _fail("MANIFEST_INVALID")
    return raw["cases"]


def _arguments(case, directory):
    def source(value):
        path = Path(value)
        return str(path if path.is_absolute() else directory / path)

    return SimpleNamespace(
        program=case.get("program", "double_savings"), work_category=case.get("work_category"),
        self_identity=case.get("self_identity", False), slot=case.get("slot"),
        file=source(case["file"]) if "file" in case else None,
        income=[source(case["income"][key]) for key in _INCOME_FILES] if "income" in case else None,
    )


def _vocabulary():
    """Obtain canonical slots from the same supported CLI contexts."""
    from ..rules.doc_types import DocType
    from ..rules.programs import PROGRAMS
    from ..rules.required_docs import WorkCategory
    slots = set()
    for code, program in PROGRAMS.items():
        categories = [None, *WorkCategory] if program.has_work_requirement else [None]
        for category in categories:
            args = SimpleNamespace(program=code, work_category=category)
            checklist = upload._context(args)[3]
            slots.update(req.slot_key for req in checklist if req.upload)
    return {str(kind) for kind in DocType} | {"X"}, slots


def _reason_pairs(findings):
    pairs = {
        (upload._code(finding.get("code")), upload._enum(finding.get("severity"), _SEVERITIES))
        for finding in findings if isinstance(finding, dict)
    }
    return [{"code": code, "severity": severity} for code, severity in sorted(pairs)]


def _snapshot(assessment, types):
    from ..api.common import applicant_findings
    documents = {}
    for req, ocr, row, result in assessment.documents:
        findings = row.findings_json or []
        documents[req.slot_key] = {
            "detected_type": upload._enum(row.doc_type, types),
            "document_status": upload._enum(row.stage1_status, _DOCUMENT_STATUSES),
            "reason": _reason_pairs(findings),
            "applicant_reason": _reason_pairs(applicant_findings(findings)),
            "failed_validation": sorted(upload._failed_validation_names(
                (row.ocr_json or {}).get("fields") or {},
            )),
        }
    snapshot = {
        "identity": "O" if assessment.identity else "X", "documents": documents,
        "blockers": "O" if assessment.blocked else "X",
    }
    if assessment.income is not None:
        snapshot["income_status"] = upload._enum(assessment.income.status, _INCOME_STATUSES)
        snapshot["income_reason"] = sorted({upload._code(code) for code in assessment.income.reason_codes})
    if assessment.work is not None:
        work = assessment.work
        snapshot["work_status"] = upload._enum(work.status, _WORK_STATUSES)
        snapshot["work_reason"] = sorted({
            upload._code(code) for code in [work.reason_code, *work.detail_codes] if code
        })
    return snapshot


def _validate_expected(raw, types, slots):
    def require(condition):
        if not condition:
            _fail("EXPECTED_INVALID")

    def member(value, allowed):
        return isinstance(value, str) and value in allowed

    def codes(value, allowed):
        return isinstance(value, list) and all(member(code, allowed) for code in value)

    require(isinstance(raw, dict) and set(raw) == {"schema_version", "cases"})
    require(type(raw["schema_version"]) is int and raw["schema_version"] == 1)
    require(isinstance(raw["cases"], dict) and bool(raw["cases"]))
    for case_id, case in raw["cases"].items():
        require(bool(_ID.fullmatch(case_id)) and isinstance(case, dict))
        required = {"identity", "documents", "blockers"}
        optional = {"income_status", "income_reason", "work_status", "work_reason"}
        require(required <= set(case) <= required | optional)
        require(member(case["identity"], {"O", "X"}) and member(case["blockers"], {"O", "X"}))
        require(isinstance(case["documents"], dict) and bool(case["documents"]))
        for slot, document in case["documents"].items():
            require(slot in slots and isinstance(document, dict))
            require(set(document) == {"detected_type", "document_status", "reason", "applicant_reason", "failed_validation"})
            require(member(document["detected_type"], types))
            require(member(document["document_status"], _DOCUMENT_STATUSES))
            require(codes(document["failed_validation"], upload.SAFE_VALIDATIONS | {"UNKNOWN_VALIDATION"}))
            for name in ("reason", "applicant_reason"):
                require(isinstance(document[name], list))
                for finding in document[name]:
                    require(isinstance(finding, dict) and set(finding) == {"code", "severity"})
                    require(member(finding["code"], upload.SAFE_CODES | {"UNKNOWN_CODE"}))
                    require(member(finding["severity"], _SEVERITIES))
        for prefix, statuses in (("income", _INCOME_STATUSES), ("work", _WORK_STATUSES)):
            status, reason = prefix + "_status", prefix + "_reason"
            require((status in case) == (reason in case))
            if status in case:
                require(member(case[status], statuses))
                require(codes(case[reason], upload.SAFE_CODES | {"UNKNOWN_CODE"}))
    return raw["cases"]


def _tokens(snapshot):
    tokens = {f"identity:{snapshot['identity']}", f"blockers:{snapshot['blockers']}"}
    for slot, document in snapshot["documents"].items():
        for field in ("detected_type", "document_status"):
            tokens.add(f"{slot}.{field}:{document[field]}")
        for field in ("reason", "applicant_reason"):
            tokens.update(f"{slot}.{field}:{item['code']}:{item['severity']}" for item in document[field])
        tokens.update(f"{slot}.failed_validation:{name}" for name in document["failed_validation"])
    for prefix in ("income", "work"):
        if prefix + "_status" in snapshot:
            tokens.add(f"{prefix}_status:{snapshot[prefix + '_status']}")
            tokens.update(f"{prefix}_reason:{code}" for code in snapshot[prefix + "_reason"])
    return tokens


def _record(expected, cases):
    temporary = None
    created = False
    try:
        temporary = _private_location(expected.with_name(f".{expected.name}.{uuid.uuid4().hex}.tmp"))
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        created = True
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump({"schema_version": 1, "cases": cases}, output, ensure_ascii=False, indent=2)
            output.write("\n")
        os.replace(temporary, expected)
    except Exception:
        _fail("RECORD_ERROR")
    finally:
        if created and temporary is not None and temporary.exists():
            temporary.unlink()


def _exception_name(exc):
    name = type(exc).__name__
    return name if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", name) else "Exception"


def parser():
    result = upload.SafeParser(prog="verify_cases", description="Value-free private case regression")
    result.add_argument("--cases", required=True, metavar="JSON")
    result.add_argument("--record", action="store_true")
    return result


def main(argv=None):
    try:
        args = parser().parse_args(argv)
        requested = Path(args.cases).absolute()
        manifest = _private_location(requested)
        expected = _private_location(Path(str(requested) + ".expected.json"))
        if manifest == expected:
            _fail("LOCATION_REJECTED")
        cases = _manifest(manifest)
        path_errors = {}
        for case in cases:
            try:
                case_args = _arguments(case, manifest.parent)
                sources = case_args.income or [case_args.file]
                collision = any(Path(source).resolve() == expected for source in sources)
            except Exception as exc:
                path_errors[case["id"]] = _exception_name(exc)
                continue
            if collision:
                _fail("LOCATION_REJECTED")
        with upload.quiet_assessment():
            types, slots = _vocabulary()
        baseline = {}
        if not args.record:
            if not expected.is_file():
                _fail("EXPECTED_MISSING")
            baseline = _validate_expected(_read_json(expected, "EXPECTED_INVALID"), types, slots)
        current, errors = {}, path_errors
        for case in cases:
            case_id = case["id"]
            if case_id in errors:
                continue
            try:
                with upload.quiet_assessment():
                    case_args = _arguments(case, manifest.parent)
                    context = upload._context(case_args)
                    assess = upload.assess_income if case_args.income else upload.assess_document
                    current[case_id] = _snapshot(assess(case_args, *context), types)
            except Exception as exc:
                errors[case_id] = _exception_name(exc)
        if args.record and not errors:
            _record(expected, current)
        matching = 0
        ids = [case["id"] for case in cases]
        if not args.record:
            ids += sorted(set(baseline) - set(ids))
        for case_id in ids:
            if case_id in errors:
                print(f"{case_id} X {errors[case_id]}")
                continue
            if args.record:
                print(f"{case_id} O")
                matching += 1
                continue
            if case_id not in baseline:
                changes = ["+CASE_ADDED"]
            elif case_id not in current:
                changes = ["-CASE_REMOVED"]
            else:
                old, new = _tokens(baseline[case_id]), _tokens(current[case_id])
                changes = ["-" + token for token in sorted(old - new)] + ["+" + token for token in sorted(new - old)]
            print(f"{case_id} {'X' if changes else 'O'}")
            for change in changes:
                print(change)
            matching += not changes
        print(f"{matching}/{len(ids)}")
        return 0 if matching == len(ids) else 1
    except CasesError as exc:
        print(exc.args[0])
        return 2
    except upload.VerificationError:
        print("ARGUMENT_ERROR")
        return 2
    except KeyboardInterrupt:
        print("INTERRUPTED")
        return 2
    except Exception:
        print("INPUT_ERROR")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

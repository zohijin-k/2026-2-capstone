"""Value-free, read-only verification through the explicit-slot upload path.

Use python -B -m to suppress interpreter startup bytecode writes as well.
Only main() emits output; all dependency output is discarded, including native
stdio. This process-global boundary belongs to a single-threaded CLI only.
"""
from __future__ import annotations

import sys
sys.dont_write_bytecode = True

import argparse
from contextlib import contextmanager
from datetime import date
import json
import logging
import math
import os
from pathlib import Path
import re


class VerificationError(Exception):
    """A fixed code, never an input value or dependency exception message."""


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        raise VerificationError("ARGUMENT_ERROR")


_WRITE_EVENTS = frozenset({
    "os.mkdir", "os.remove", "os.rmdir", "os.rename", "os.link", "os.symlink",
    "os.truncate", "os.chmod", "os.chown", "os.utime", "os.system",
    "subprocess.Popen", "os.exec", "os.posix_spawn", "sqlite3.connect",
})
_GUARDS: list[dict[str, bool]] = []
_HOOK_INSTALLED = False


def _deny_writes(event, args):
    if not _GUARDS:
        return
    denied = event in _WRITE_EVENTS
    if event == "open":
        mode, flags = args[1:3]
        denied = (isinstance(mode, str) and any(char in mode for char in "wax+")) or (
            isinstance(flags, int) and bool(flags & (
                os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
            ))
        )
    if denied:
        for guard in _GUARDS:
            guard["attempted"] = True
        raise VerificationError("WRITE_ATTEMPT_BLOCKED")


@contextmanager
def read_only_assessment():
    """Reject filesystem mutations and DB connections, even if OCR swallows errors."""
    global _HOOK_INSTALLED
    if not _HOOK_INSTALLED:
        sys.addaudithook(_deny_writes)
        _HOOK_INSTALLED = True
    guard = {"attempted": False}
    _GUARDS.append(guard)
    try:
        yield
    finally:
        _GUARDS.pop()
        if guard["attempted"]:
            raise VerificationError("WRITE_ATTEMPT_BLOCKED")


@contextmanager
def quiet_assessment():
    # Reuse the existing native/Python suppression boundary; the null sink is
    # opened before the read-only guard, and never stores document contents.
    from engine_v2.tools.private_bench import quiet_dependencies
    disabled = logging.root.manager.disable
    logging.disable(sys.maxsize)
    try:
        with quiet_dependencies(), read_only_assessment():
            yield
    finally:
        logging.disable(disabled)


def _enum(value, allowed, missing="X"):
    return str(value) if isinstance(value, str) and value in allowed else missing


def _code(value):
    return _enum(value, SAFE_CODES, "UNKNOWN_CODE")


def _count(value):
    return str(value) if type(value) is int and 0 <= value < 1000 else "X"


def _confidence(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "X"
    return f"{value:.2f}" if math.isfinite(value) and 0 <= value <= 1 else "X"


def _redact(text):
    return re.sub(r"\d{4,}", "X", text)


def _identity_from_ocr(ocr, program=None):
    from ..rules.doc_types import DocType
    from ..rules.identity import identity_of
    name, birth = ocr.fields.get("성명"), ocr.fields.get("생년월일")
    if not isinstance(name, str) or not name.strip():
        return None
    if not birth and ocr.detected_doc_type == DocType.DAILY_WORK_RECORD and program is not None:
        printed = ocr.fields.get("생년월일표기")
        if not isinstance(printed, str) or not re.fullmatch(r"[0-9]{2}-[0-9]{2}-[0-9]{2}", printed):
            return None
        yy, mm, dd = (int(part) for part in printed.split("-"))
        expected = []
        for century in (1900, 2000):
            try:
                expected.append(date(century + yy, mm, dd).isoformat())
            except ValueError:
                pass
        try:
            candidates = json.loads(ocr.fields.get("생년월일후보", "null"))
        except (ValueError, TypeError):
            return None
        # Accept the extractor's complete candidate set only. The program may
        # select a temporary CLI reference; the OCR fields remain unresolved.
        if (not expected or not isinstance(candidates, list)
                or len(candidates) != len(expected)
                or any(not isinstance(value, str) for value in candidates)
                or set(candidates) != set(expected)):
            return None
        lower, upper = program.birth_range
        in_range = [value for value in candidates if lower <= date.fromisoformat(value) <= upper]
        if len(in_range) != 1:
            return None
        birth = in_range[0]
    if not isinstance(birth, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", birth):
        return None
    identity = {"name": name, "birth": birth}
    return identity if identity_of(identity) is not None else None


def _context(args):
    from ..api.common import checklist_from_inputs
    from ..rules.criteria import default_criteria
    from ..rules.programs import PROGRAMS, get_program
    from ..rules.required_docs import ApplicantDocInput, WorkCategory
    if args.program not in PROGRAMS:
        raise VerificationError("PROGRAM_UNKNOWN")
    program = get_program(args.program)
    try:
        category = WorkCategory(args.work_category) if args.work_category else None
    except ValueError:
        raise VerificationError("WORK_CATEGORY_UNKNOWN") from None
    if category and not program.has_work_requirement:
        raise VerificationError("WORK_CATEGORY_NOT_APPLICABLE")
    criteria = default_criteria(program.code)
    checklist = checklist_from_inputs(
        program, ApplicantDocInput(work_category=category), criteria,
        date.fromisoformat(criteria["application_period"][0]),
    )
    return program, category, criteria, checklist


def _requirement(checklist, slot):
    from ..rules.required_docs import find_slot
    req = find_slot(checklist, slot)
    if req is None or not req.upload:
        raise VerificationError("UPLOAD_SLOT_UNKNOWN")
    return req


def _input_path(value):
    from ..rules.required_docs import ACCEPTED_FORMATS
    path = Path(value)
    if path.suffix.lstrip(".").lower() not in ACCEPTED_FORMATS:
        raise VerificationError("FORMAT_UNSUPPORTED")
    if not path.is_file():
        raise VerificationError("INPUT_UNAVAILABLE")
    return path


def _row(req, path, ocr, result):
    from ..api.documents import _ocr_json
    from ..models import Document
    return Document(
        slot_key=req.slot_key, doc_type=str(ocr.detected_doc_type) if ocr.detected_doc_type else None,
        expected_doc_type=str(req.doc_type), file_path=str(path),
        file_format=path.suffix.lstrip(".").lower(), ocr_json=_ocr_json(ocr),
        stage1_status=result.status, findings_json=[finding.as_dict() for finding in result.findings],
    )


def _refresh_pairs(identity, checklist, documents):
    from ..rules.identity import identity_of
    from ..upload_assessment import assess_nhis_identity
    results = assess_nhis_identity(identity_of(identity), checklist, documents)
    for row, result in results:
        row.stage1_status = result.status
        row.findings_json = [finding.as_dict() for finding in result.findings]
    return results


def _additional_page_count(ocr):
    try:
        pages = json.loads(ocr.fields.get("추가첨부쪽", "[]"))
    except (TypeError, ValueError):
        return "X"
    return _count(len(pages)) if isinstance(pages, list) else "X"


def _document(args, program, category, criteria, checklist):
    from ..api.common import document_fact
    from ..api.review import document_blockers
    from ..rules.doc_types import DocType
    from ..rules.eligibility_blockers import eligibility_blockers
    from ..rules.identity import identity_of
    from ..rules.work_continuity import assess_work
    from ..upload_assessment import assess_upload
    if not args.slot or not args.file:
        raise VerificationError("ARGUMENT_ERROR")
    if args.slot.startswith("work_proof") and category is None:
        raise VerificationError("WORK_CATEGORY_REQUIRED")
    req = _requirement(checklist, args.slot)
    path = _input_path(args.file)
    identity = None

    def own_identity(ocr):
        nonlocal identity
        identity = _identity_from_ocr(ocr, program)
        return identity_of(identity)

    ocr, result = assess_upload(
        path, req, checklist=checklist,
        identity_from_ocr=own_identity if args.self_identity else None,
    )
    row = _row(req, path, ocr, result)
    refreshed = _refresh_pairs(identity, checklist, [row])
    if refreshed:
        result = refreshed[0][1]
    rows = [document_fact(row)]
    blocked = any(item["target"] == req.slot_key for item in document_blockers(checklist, [row]))
    eligibility = eligibility_blockers(program, {}, identity, rows, category, criteria)
    work = None
    blocked |= any(item["target"] == "work" for item in eligibility)
    work_types = {DocType.INSURANCE_4, DocType.DAILY_WORK_RECORD,
                  DocType.NHIS_ACQUISITION_LOSS, DocType.BIZ_REG_PROOF}
    if program.has_work_requirement and (req.slot_key.startswith("work_proof") or ocr.detected_doc_type in work_types):
        work = assess_work(program, date.fromisoformat(criteria["announcement_date"]), category, rows, identity)
    lines = [
        f"tier: {_enum(ocr.tier, {'fixture', 'localocr', 'pdftext', 'jbai', 'upstage', 'none'})}",
        f"detected_type: {_enum(ocr.detected_doc_type, {str(kind) for kind in DocType})}",
        f"confidence: {_confidence(ocr.confidence)}",
        f"pages: {_count(ocr.page_count)}",
        f"open_failed: {'O' if ocr.is_encrypted else 'X'}",
        f"identity: {'O' if identity else '본인정보 없음'}",
        f"document_status: {_enum(result.status, {'PASS', 'FAIL', 'NEEDS_REVIEW'})}",
    ]
    for finding in result.findings:
        lines.append(f"reason: {_code(finding.code)} {_enum(finding.severity, {'PASS', 'FAIL', 'NEEDS_REVIEW', 'INFO'})}")
    lines.append(f"additional_pages: {_additional_page_count(ocr)}")
    if work is not None:
        lines.append(f"work_status: {_enum(work.status, {'MET', 'NOT_MET', 'UNDETERMINED'})}")
        if work.reason_code:
            lines.append(f"work_reason: {_code(work.reason_code)}")
        lines.extend(f"work_reason: {_code(code)}" for code in work.detail_codes)
    lines.append(f"blockers: {'O' if blocked else 'X'}")
    return "\n".join(lines)


def _income(args, program, category, criteria, checklist):
    from ..api.common import document_fact
    from ..api.review import document_blockers
    from ..rules.eligibility_blockers import eligibility_blockers
    from ..rules.facts import build_facts
    from ..rules.identity import identity_of
    from ..rules.scoring import score_income
    from ..upload_assessment import assess_upload
    if not program.has_income_requirement:
        raise VerificationError("INCOME_NOT_APPLICABLE")
    if args.file or args.slot:
        raise VerificationError("ARGUMENT_ERROR")
    slots = ("nhis_payment", "nhis_qualification", "nhis_acquisition_loss")
    reads = []
    identity = None
    for slot, value in zip(slots, args.income):
        req, path = _requirement(checklist, slot), _input_path(value)

        def own_identity(ocr):
            nonlocal identity
            identity = _identity_from_ocr(ocr, program)
            return identity_of(identity)

        ocr, result = assess_upload(
            path, req, checklist=checklist, identity=identity_of(identity),
            identity_from_ocr=own_identity if slot == slots[0] and args.self_identity else None,
        )
        reads.append((req, path, ocr, result))
    documents = [_row(req, path, ocr, result) for req, path, ocr, result in reads]
    _refresh_pairs(identity, checklist, documents)
    facts_rows = [document_fact(row) for row in documents]
    facts = build_facts({}, facts_rows, criteria["nhis_payment_months"])
    income = score_income(facts)
    eligibility = eligibility_blockers(program, {}, identity, facts_rows, category, criteria)
    blocked = (any(item["target"] in slots for item in document_blockers(checklist, documents))
               or any(item["target"] == "income" for item in eligibility))
    lines = [f"membership: {_enum(facts.insurance_type, {'직장', '지역', '모름'})}",
             f"income_status: {_enum(income.status, {'MET', 'OVER_LIMIT', 'UNDETERMINED'})}"]
    codes = list(dict.fromkeys([
        *income.reason_codes,
        *(finding["code"] for row in documents for finding in row.findings_json),
    ]))
    lines.extend(f"reason: {_code(code)}" for code in codes)
    lines.append(f"blockers: {'O' if blocked else 'X'}")
    return "\n".join(lines)


def parser():
    p = SafeParser(prog="verify_upload", description="값 없는 업로드 판정")
    p.add_argument("--program", default="double_savings", metavar="CODE")
    p.add_argument("--slot", metavar="KEY")
    p.add_argument("--work-category", metavar="CATEGORY")
    p.add_argument("--self-identity", action="store_true")
    p.add_argument("--slots-list", action="store_true")
    p.add_argument("--income", nargs=3, metavar=("PAYMENT", "QUALIFICATION", "HISTORY"))
    p.add_argument("file", nargs="?", metavar="FILE")
    return p


def main(argv=None):
    try:
        args = parser().parse_args(argv)
        with quiet_assessment():
            program, category, criteria, checklist = _context(args)
            if args.slots_list:
                if args.file or args.slot or args.income or args.self_identity:
                    raise VerificationError("ARGUMENT_ERROR")
                output = "\n".join(f"{row.slot_key}: {row.label}" for row in checklist if row.upload)
            elif args.income:
                output = _income(args, program, category, criteria, checklist)
            else:
                output = _document(args, program, category, criteria, checklist)
        print(_redact(output))
        return 0
    except VerificationError as exc:
        # Exception strings from dependencies never reach this branch.
        code = exc.args[0] if exc.args and exc.args[0] in ERROR_CODES else "ASSESSMENT_ERROR"
        print(f"error: {code}")
        return 2
    except Exception:
        print("error: ASSESSMENT_ERROR")
        return 2
    except KeyboardInterrupt:
        print("error: INTERRUPTED")
        return 2


ERROR_CODES = frozenset({
    "ARGUMENT_ERROR", "PROGRAM_UNKNOWN", "WORK_CATEGORY_UNKNOWN", "WORK_CATEGORY_NOT_APPLICABLE",
    "UPLOAD_SLOT_UNKNOWN", "FORMAT_UNSUPPORTED", "INPUT_UNAVAILABLE", "WORK_CATEGORY_REQUIRED",
    "INCOME_NOT_APPLICABLE", "WRITE_ATTEMPT_BLOCKED", "ASSESSMENT_ERROR", "INTERRUPTED",
})
# Fixed production code vocabulary; never accept arbitrary OCR strings as codes.
SAFE_CODES = frozenset("""
ADMIN_CONSENT_IDENTITY_MISMATCH
ADMIN_CONSENT_IDENTITY_UNCERTAIN
ADMIN_CONSENT_IDENTITY_UNREADABLE
ADMIN_CONSENT_MARK_UNREADABLE
ADMIN_CONSENT_NOT_GIVEN
ADMIN_CONSENT_SIGNATURE_UNREADABLE
ALL_CLEAR
DAILY_RECORDS_PARTIALLY_SELECTED
DECLARED_DATE_MISMATCH
DECLARED_DATE_UNCERTAIN
DOCUMENT_ISSUED_AFTER_APPLICATION
DOCUMENT_ISSUED_TOO_EARLY
DUPLICATE_APPLICATION
EXCEEDED_SUPPORT_COUNT
FAIL
HOUSEHOLD_SIZE_UNCONFIRMED
HOUSEHOLD_SIZE_UNSUPPORTED
IDENTITY_MISMATCH
IDENTITY_UNCERTAIN
IMAGE_RESOLUTION_TOO_LOW
INCOME_ABOVE_ALL_LIMITS
INCOME_ABOVE_BOTH_LIMITS
INCOME_ABOVE_CATEGORY_LIMIT
INCOME_AT_OR_BELOW_BOTH_LIMITS
INCOME_AT_OR_BELOW_CATEGORY_LIMIT
INCOME_MIXED_POSSIBLE
INCOME_OVER_THRESHOLD
INFO
INSURANCE_EVIDENCE_CONFLICT
INSURANCE_EVIDENCE_INSUFFICIENT
INSURANCE_EXPLICIT_CONFLICT
INSURANCE_TYPE_UNSUPPORTED
LOW_IMAGE_QUALITY
LOW_OCR_CONFIDENCE
MET
MISSING
MISSING_ADDRESS_DATES
MISSING_ADDRESS_HISTORY
MISSING_BILLING_MONTHS
MISSING_REQUIRED_DOC
MISSING_REQUIRED_FIELD
MISSING_SIGNATURE
NEEDS_REVIEW
NHIS_DEPENDENT_INSURED_PERSON
NHIS_HISTORY_PERIOD_MISSING
NHIS_HISTORY_PERIOD_UNREADABLE
NHIS_SUBSCRIBER_IDENTITY_REVIEW
NOT_MET
NOT_TARGET_AGE
NOT_TARGET_REGION
OTHER_PROGRAM_CONFLICT
OVER_LIMIT
PAGES_DUPLICATED
PAGES_INCOMPLETE
PAGES_UNREADABLE
PASS
PAST_ADDRESS_OMISSION_SUSPECTED
PREMIUM_AMOUNT_INVALID
PREMIUM_AMOUNT_UNCONFIRMED
PREMIUM_MONTHS_INVALID
PREMIUM_MONTH_MISSING
PREMIUM_UNTRUSTED
READABLE
RECEIPT_AMOUNT_MISMATCH
RECEIPT_AMOUNT_UNREADABLE
RECEIPT_OCR_UNAVAILABLE
REQUIRED_FIELD_UNREADABLE
RESIDENT_APPLICANT_UNREADABLE
SCREEN_CAPTURE_SUSPECTED
UNDETERMINED
UNKNOWN_DOCUMENT_TYPE
UNREADABLE_FILE
WORK_ACTIVE_INSURANCE_COVERS_PERIOD
WORK_ALL_ACQUISITIONS_AFTER_START
WORK_BUSINESS_OPENED_IN_TIME
WORK_BUSINESS_OPENED_TOO_LATE
WORK_BUSINESS_OPENING_UNREADABLE
WORK_BUSINESS_STATUS_UNREADABLE
WORK_BUSINESS_SUSPENDED_OR_CLOSED
WORK_CONTINUITY_NOT_MET
WORK_CONTINUITY_UNDETERMINED
WORK_DAILY_COPIES_UNCONFIRMED
WORK_DAILY_MONTHS_COVERED
WORK_DAILY_MONTHS_MISSING
WORK_DAILY_PERIOD_OR_TABLE_UNREADABLE
WORK_DAILY_QUERY_PERIOD_TOO_SHORT
WORK_DOCUMENTS_CONFLICT
WORK_EVIDENCE_MISSING
WORK_HISTORY_AMBIGUOUS_INTERVALS
WORK_HISTORY_COVERAGE_UNCONFIRMED
WORK_HISTORY_COVERS_PERIOD
WORK_HISTORY_GAP
WORK_HISTORY_HAS_NO_WORKPLACE_ROWS
WORK_HISTORY_START_NOT_COVERED
WORK_HISTORY_UNREADABLE
WORK_IDENTITY_UNCONFIRMED
WORK_INSURANCE_ROWS_UNREADABLE
WORK_INSURANCE_ROW_IDENTITY_UNCONFIRMED
WORK_ISSUE_BEFORE_NOTICE_OR_UNREADABLE
WORK_NOT_ACTIVE_AT_NOTICE
WORK_POLICY_UNCONFIGURED
WORK_SOURCE_CONFIDENCE_UNCONFIRMED
WORK_STRUCTURE_UNCONFIRMED
WORK_DAILY_SELECTION_INCOMPLETE
WORK_DAILY_SELECTION_UNCONFIRMED
WRONG_DOCUMENT_TYPE
""".split())

if __name__ == "__main__":
    raise SystemExit(main())

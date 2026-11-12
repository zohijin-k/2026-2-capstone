"""잠정 work continuity, separate from the unchanged employment scoring rules."""
from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date
import json
import math
import re
from typing import Any

from ..engine_adapter import engine_config
from .doc_types import DocType
from .identity import Identity, identity_of, norm_name
from .programs import ProgramConfig
from .required_docs import WorkCategory


@dataclass(frozen=True)
class WorkContinuityResult:
    status: str
    reason_code: str | None
    detail_codes: list[str]
    basis: str
    period_start: date | None
    period_end: date | None
    evidence: list[dict[str, Any]] = field(default_factory=list)
    missing_months: list[str] = field(default_factory=list)
    provisional: bool = True

    @property
    def review_status(self) -> str:
        return {"MET": "PASS", "NOT_MET": "FAIL", "UNDETERMINED": "NEEDS_REVIEW"}[self.status]

    def as_dict(self) -> dict[str, Any]:
        return {"status": self.status, "reason_code": self.reason_code,
                "detail_codes": self.detail_codes, "basis": self.basis,
                "period_start": self.period_start.isoformat() if self.period_start else None,
                "period_end": self.period_end.isoformat() if self.period_end else None,
                "evidence": self.evidence, "missing_months": self.missing_months,
                "provisional": self.provisional}


def _date(value: Any) -> date | None:
    if type(value) is date:
        return value
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _months_before(day: date, months: int) -> date:
    ordinal = day.year * 12 + day.month - 1 - months
    year, month = divmod(ordinal, 12)
    return date(year, month + 1, min(day.day, calendar.monthrange(year, month + 1)[1]))


def _json(fields, key):
    try:
        return json.loads(fields.get(key, ""))
    except (TypeError, ValueError):
        return None


def _complete(fields):
    if "양식판독상태" in fields:
        return fields["양식판독상태"] == "완전"
    # Government24's existing reader predates the complete-structure marker.
    # Its explicit all-checks-passed count still proves validation occurred.
    match = re.fullmatch(r"([1-9]\d*)/([1-9]\d*) 통과", str(fields.get("판독검증", "")))
    return bool(match and match[1] == match[2])


def _date_confident(row, key):
    # Historical already-validated rows predate token provenance; fresh readers
    # always serialize it, so a present missing/invalid value cannot bypass it.
    if key not in row:
        return True
    value=row[key]
    try:
        return (not isinstance(value,bool) and math.isfinite(float(value)) and
                float(value)>=engine_config.OCR_CONFIDENCE_THRESHOLD)
    except (TypeError,ValueError):
        return False


def _trust_issue(doc, fields, identity: Identity | None, end: date) -> str | None:
    if identity is None:
        return "WORK_IDENTITY_UNCONFIRMED"
    if not isinstance(fields.get("성명"),str) or norm_name(fields.get("성명")) != identity.name:
        return "WORK_IDENTITY_UNCONFIRMED"
    printed_birth = _date(fields.get("생년월일"))
    candidates = _json(fields, "생년월일후보")
    birth_matches = printed_birth == identity.birth
    if printed_birth is None and isinstance(candidates, list):
        birth_matches = (all(_date(value) is not None for value in candidates) and
                         identity.birth.isoformat() in candidates)
    if not birth_matches:
        return "WORK_IDENTITY_UNCONFIRMED"
    try:
        confidence = doc.get("confidence")
        trusted_confidence = (not isinstance(confidence, bool) and math.isfinite(float(confidence)) and
                              float(confidence) >= engine_config.OCR_CONFIDENCE_THRESHOLD)
    except (TypeError, ValueError):
        trusted_confidence = False
    if "image_quality" in doc:
        try:
            quality = doc["image_quality"]
            trusted_confidence &= (not isinstance(quality,bool) and math.isfinite(float(quality)) and
                                   float(quality)>=engine_config.IMAGE_QUALITY_THRESHOLD)
        except (TypeError,ValueError):
            trusted_confidence = False
    if (doc.get("status") not in {None, "PASS"} or not trusted_confidence or
            not _complete(fields) or fields.get("판독검증실패")):
        return "WORK_STRUCTURE_UNCONFIRMED"
    issue = _date(doc.get("issue_date")) or _date(fields.get("발급일"))
    if issue is None or issue < end:
        return "WORK_ISSUE_BEFORE_NOTICE_OR_UNREADABLE"
    return None


def _insurance(fields, start, end):
    rows = _json(fields, "가입내역")
    if (not isinstance(rows, list) or len(rows) != 4 or
            any(not isinstance(row, dict) or not isinstance(row.get("보험"),str) for row in rows) or
            {row.get("보험") for row in rows} != {"국민연금", "건강보험", "고용보험", "산재보험"}):
        return "UNDETERMINED", "WORK_INSURANCE_ROWS_UNREADABLE", {}, []
    work = []
    for row in rows:
        if not isinstance(row.get("상태"),str) or row.get("상태") not in {"가입", "미가입"}:
            return "UNDETERMINED", "WORK_INSURANCE_ROWS_UNREADABLE", {}, []
        if not isinstance(row.get("가입자종별"),str):
            return "UNDETERMINED", "WORK_INSURANCE_ROWS_UNREADABLE", {}, []
        if row["상태"] == "가입" and (
                (row["보험"] == "국민연금" and row.get("가입자종별") == "사업장가입자") or
                (row["보험"] == "건강보험" and row.get("가입자종별") == "직장가입자") or
                row["보험"] in {"고용보험", "산재보험"}):
            if not isinstance(row.get("성명"),str) or norm_name(row["성명"]) != norm_name(fields["성명"]):
                return "UNDETERMINED", "WORK_INSURANCE_ROW_IDENTITY_UNCONFIRMED", {}, []
            acquired = _date(row.get("자격취득일"))
            if acquired is None or acquired > end or not _date_confident(row,"자격취득일신뢰도"):
                return "UNDETERMINED", "WORK_INSURANCE_ROWS_UNREADABLE", {}, []
            work.append(acquired)
    if not work:
        return "UNDETERMINED", "WORK_INSURANCE_ROWS_UNREADABLE", {}, []
    dates = sorted({value.isoformat() for value in work})
    evidence = {"acquired_dates": dates, "active_at_notice": True}
    if any(value <= start for value in work):
        return "MET", "WORK_ACTIVE_INSURANCE_COVERS_PERIOD", evidence, []
    return "NOT_MET", "WORK_ALL_ACQUISITIONS_AFTER_START", evidence, []


def _history(fields, start, end):
    data = _json(fields, "자격이력자료")
    if not isinstance(data, dict) or not isinstance(data.get("rows"), list) or not data["rows"]:
        return "UNDETERMINED", "WORK_HISTORY_UNREADABLE", {}, []
    period = data.get("period")
    complete_coverage = data.get("coverage_basis") == "full_history"
    if period is not None:
        if (not isinstance(period, list) or len(period) != 2 or any(_date(value) is None for value in period) or
                _date(period[0])>_date(period[1])):
            return "UNDETERMINED", "WORK_HISTORY_UNREADABLE", {}, []
        complete_coverage = _date(period[0]) <= start and _date(period[1]) >= end
    elif data.get("recent_five_years_covered") is True:
        complete_coverage = True
    intervals = []
    for row in data["rows"]:
        if not isinstance(row, dict):
            return "UNDETERMINED", "WORK_HISTORY_UNREADABLE", {}, []
        acquired, lost = _date(row.get("acquired")), _date(row.get("lost"))
        if (acquired is None or (row.get("lost") not in (None, "") and lost is None) or
                (lost is not None and acquired > lost) or
                not _date_confident(row,"acquired_confidence") or
                (lost is not None and not _date_confident(row,"lost_confidence"))):
            return "UNDETERMINED", "WORK_HISTORY_UNREADABLE", {}, []
        if not isinstance(row.get("category"),str):
            return "UNDETERMINED", "WORK_HISTORY_UNREADABLE", {}, []
        if row.get("category") in {"직장", "직장가입자"}:
            intervals.append((acquired, lost))
    if not intervals:
        return "UNDETERMINED", "WORK_HISTORY_HAS_NO_WORKPLACE_ROWS", {}, []
    if len({a for a,b in intervals}) != len(intervals):
        return "UNDETERMINED", "WORK_HISTORY_AMBIGUOUS_INTERVALS", {}, []
    evidence = {"intervals": [[a.isoformat(), b.isoformat() if b else None] for a,b in sorted(intervals,key=lambda item:item[0])],
                "history_covers_period": complete_coverage}
    relevant = sorted(((a,b) for a,b in intervals if a <= end and (b is None or b >= start)),key=lambda item:item[0])
    # A current interval can prove a positive result even without a printed
    # query period. A negative needs coverage of the entire relevant history.
    covered_until = start
    started = False
    gap = False
    for acquired,lost in relevant:
        if acquired > covered_until:
            gap = True
            break
        started = True
        if lost is None or lost > end:
            return "MET", "WORK_HISTORY_COVERS_PERIOD", evidence, []
        covered_until = max(covered_until, lost)
    if not complete_coverage:
        return "UNDETERMINED", "WORK_HISTORY_COVERAGE_UNCONFIRMED", evidence, []
    detail = ("WORK_HISTORY_GAP" if gap and started else
              "WORK_HISTORY_START_NOT_COVERED" if not started else "WORK_NOT_ACTIVE_AT_NOTICE")
    return "NOT_MET", detail, evidence, []


def _daily(fields, start, end):
    data = _json(fields, "일용근로내역자료")
    if not isinstance(data, dict) or data.get("copies_consistent") is not True:
        return "UNDETERMINED", "WORK_DAILY_COPIES_UNCONFIRMED", {}, []
    period, rows = data.get("period"), data.get("rows")
    if (not isinstance(period, list) or len(period) != 2 or
            any(not isinstance(value,str) or not re.fullmatch(r"20\d{2}-(?:0[1-9]|1[0-2])",value) for value in period) or
            period[0] > period[1] or not isinstance(rows,list) or not rows):
        return "UNDETERMINED", "WORK_DAILY_PERIOD_OR_TABLE_UNREADABLE", {}, []
    present = set()
    observed = []
    for row in rows:
        if not isinstance(row, dict):
            return "UNDETERMINED", "WORK_DAILY_PERIOD_OR_TABLE_UNREADABLE", {}, []
        month, days, dates = row.get("month"), row.get("days"), row.get("work_dates")
        if (not isinstance(month,str) or not re.fullmatch(r"20\d{2}-(?:0[1-9]|1[0-2])",month) or
                not period[0] <= month <= period[1] or type(days) is not int or days < 0 or
                not isinstance(dates,list) or any(type(value) is not int or value < 1 or
                    value > calendar.monthrange(int(month[:4]),int(month[5:]))[1] for value in dates) or
                len(set(dates)) != days or len(dates) != days or
                not isinstance(row.get("workplace"),str) or not row["workplace"].strip()):
            return "UNDETERMINED", "WORK_DAILY_PERIOD_OR_TABLE_UNREADABLE", {}, []
        observed.append({"month":month,"days":days,"workplace":row["workplace"]})
        if days >= 1:
            present.add(month)
    evidence = {"query_period":period,"monthly_work":observed}
    if period[0] > start.strftime("%Y-%m") or period[1] < end.strftime("%Y-%m"):
        return "NOT_MET", "WORK_DAILY_QUERY_PERIOD_TOO_SHORT", evidence, []
    required = []
    cursor = date(start.year,start.month,1)
    until = date(end.year,end.month,1)
    while cursor < until:
        required.append(cursor.strftime("%Y-%m"))
        cursor = date(cursor.year + (cursor.month == 12),cursor.month % 12 + 1,1)
    missing = [month for month in required if month not in present]
    if missing:
        return "NOT_MET", "WORK_DAILY_MONTHS_MISSING", evidence, missing
    return "MET", "WORK_DAILY_MONTHS_COVERED", evidence, []


def _business(fields, program):
    opened = _date(fields.get("개업일"))
    cutoff = program.business_opening_deadline
    evidence = {"opened":opened.isoformat() if opened else None,
                "opening_deadline":cutoff.isoformat() if cutoff else None,
                "business_status":fields.get("사업자상태")}
    status=fields.get("사업자상태")
    if status is not None and (not isinstance(status,str) or status not in {"휴업","폐업","계속사업자","정상"}):
        return "UNDETERMINED", "WORK_BUSINESS_STATUS_UNREADABLE", evidence, []
    if status in ("휴업", "폐업"):
        return "NOT_MET", "WORK_BUSINESS_SUSPENDED_OR_CLOSED", evidence, []
    if fields.get("사업자상태_상태") == "못 읽음":
        return "UNDETERMINED", "WORK_BUSINESS_STATUS_UNREADABLE", evidence, []
    if opened is None or cutoff is None:
        return "UNDETERMINED", "WORK_BUSINESS_OPENING_UNREADABLE", evidence, []
    return ("MET", "WORK_BUSINESS_OPENED_IN_TIME", evidence, []) if opened <= cutoff else (
        "NOT_MET", "WORK_BUSINESS_OPENED_TOO_LATE", evidence, [])


def assess_work(program: ProgramConfig, announcement_date: date, work_category: str | None,
                documents: list[dict[str,Any]], identity: Identity | dict[str,Any] | None) -> WorkContinuityResult:
    """Assess only certain applicant-matched document evidence (잠정 five months)."""
    if not program.has_work_requirement:
        return WorkContinuityResult("MET",None,[],"이 사업에는 근로 계속성 요건이 없습니다.",None,None,provisional=False)
    months = program.work_continuity_months
    if type(months) is not int or months < 1:
        return WorkContinuityResult("UNDETERMINED","WORK_CONTINUITY_UNDETERMINED",["WORK_POLICY_UNCONFIGURED"],
                                    "근로 계속성 기준을 확인해야 합니다.",None,announcement_date)
    start,end = _months_before(announcement_date,months),announcement_date
    identity = identity if isinstance(identity,Identity) else identity_of(identity)
    relevant = ({DocType.BIZ_REG_PROOF} if work_category == WorkCategory.BUSINESS else
                {DocType.DAILY_WORK_RECORD,DocType.INSURANCE_4,DocType.NHIS_ACQUISITION_LOSS}
                if work_category in {WorkCategory.EMPLOYEE,WorkCategory.LOCAL} else set())
    results = []
    for doc in documents:
        if doc.get("doc_type") not in relevant:
            continue
        fields = doc.get("fields") or {}
        if not isinstance(fields,dict):
            continue
        issue = _trust_issue(doc,fields,identity,end)
        if issue:
            outcome = ("UNDETERMINED",issue,{},[])
        elif doc["doc_type"] == DocType.INSURANCE_4:
            outcome = _insurance(fields,start,end)
        elif doc["doc_type"] == DocType.NHIS_ACQUISITION_LOSS:
            outcome = _history(fields,start,end)
        elif doc["doc_type"] == DocType.DAILY_WORK_RECORD:
            outcome = _daily(fields,start,end)
        else:
            outcome = _business(fields,program)
        results.append({"status":outcome[0],"detail_code":outcome[1],"document_id":doc.get("document_id"),
                        "doc_type":str(doc["doc_type"]),**outcome[2],"missing_months":outcome[3]})
    determinate = [result for result in results if result["status"] != "UNDETERMINED"]
    states = {result["status"] for result in determinate}
    status = next(iter(states)) if len(states) == 1 else "UNDETERMINED"
    details = ["WORK_DOCUMENTS_CONFLICT"] if len(states) > 1 else list(dict.fromkeys(
        result["detail_code"] for result in (determinate or results))) or ["WORK_EVIDENCE_MISSING"]
    missing = sorted({month for result in determinate for month in result["missing_months"]})
    prefix = f"잠정 근로 계속성 기준 구간 {start.isoformat()}~{end.isoformat()} · "
    intervals = []
    for item in determinate:
        if item.get("acquired_dates"):
            intervals.append("서류 자격취득일 " + ", ".join(item["acquired_dates"]))
        if item.get("intervals"):
            intervals.append("서류 근로기간 " + ", ".join(f"{a}~{b or '가입 중'}" for a,b in item["intervals"]))
        if item.get("opened"):
            intervals.append(f"개업일 {item['opened']} · 인정 기준 {item['opening_deadline']}")
        if item.get("query_period"):
            intervals.append("조회기간 " + "~".join(item["query_period"]))
    basis = prefix + (" · ".join(intervals) + " · " if intervals else "")
    if status == "MET":
        basis += "서류에서 근로 계속성 요건을 충족하는 내역을 확인했습니다."
    elif status == "NOT_MET":
        basis += ("근로 기록 없는 달 " + ", ".join(missing) + " · " if missing else "")
        basis += "서류에서 근로 계속성 요건 불충족을 확인했습니다."
        if "WORK_DAILY_QUERY_PERIOD_TOO_SHORT" in details:
            basis += " 조회기간을 기준 구간 전체로 늘려 다시 발급받아 주세요."
        if "WORK_HISTORY_GAP" in details:
            basis += " 자격상실일과 다음 취득일 사이에 공백이 있습니다."
        if "WORK_BUSINESS_SUSPENDED_OR_CLOSED" in details:
            basis += " 휴업 또는 폐업 표시를 확인했습니다."
    else:
        basis += ("서류별 근로 계속성 결과가 서로 다릅니다. " if len(states) > 1 else
                  "근로 계속성을 확정할 서류 근거가 부족합니다. ") + "담당자가 원본을 확인합니다."
    return WorkContinuityResult(status,"WORK_CONTINUITY_NOT_MET" if status == "NOT_MET" else
                                "WORK_CONTINUITY_UNDETERMINED" if status == "UNDETERMINED" else None,
                                details,basis,start,end,results,missing)

"""면접확인서 판독기 — 면접비·면접정장비 지원의 면접 증빙.

사업계획서 서식(demo/fixtures/templates/job_interview_confirmation.pdf)은 면접자·면접기업·면접현황
세 칸과 확인 문장, 확인일, 아래 회사명·담당자 서명란으로 되어 있다. 면접기업·면접현황 칸은 기업이
채운다. 기업이 자체 양식을 쓰는 경우도 있어 좌표 대신 라벨로 읽는다 (`job_common`).

추출 필드: 성명 · 생년월일(date) · 회사명 · 업태업종 · 면접일(date) · 면접시간 · 면접장소 · 응시직군 · 확인일(date)
읽지 않는 것: 면접자 주소·연락처·이메일, 기업 소재지·담당자 이름·연락처 (판정에 쓰지 않는 개인정보)
서류 안 검증: 성명·회사명·면접일을 찾음, 면접일이 오늘 이후가 아님, 면접일 ≤ 확인일,
            위 회사명 = 아래 서명란 회사명
서명·직인 여부와 아르바이트 의심 업종 판단은 하지 않는다 (서명 규칙·도청 업종 목록 뒤에).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from ..pipeline.layout import Word, line_text, squash
from ..pipeline.ocr import OcrResult
from ..pipeline.preprocess import PageImage
from ..schemas.models import DocType, ExtractedField
from . import job_common as job
from . import nhis_common as common
from .resident_abstract import kst_today

TITLE_HINTS = ("면접확인서", "면접참석확인서", "면접사실확인서")
NAME_LABELS = ("면접자성명", "성명", "이름")
BIRTH_LABELS = ("생년월일",)
COMPANY_LABELS = ("회사명", "기업명", "업체명", "사업장명", "상호")
INDUSTRY_LABELS = ("업태/업종", "업태업종", "업종", "업태")
INTERVIEW_DATE_LABELS = ("면접일시", "면접일자", "면접일")
TIME_LABELS = ("면접시간",)
PLACE_LABELS = ("면접장소",)
JOB_LABELS = ("응시직군", "응시분야", "지원분야", "모집분야", "지원직무", "직무")
#: 확인 문장. 확인일은 이 문장 아래(또는 같은 줄)의 라벨 없는 날짜다.
CONFIRM_HINTS = ("확인합니다", "확인함", "확인하였", "참석하였음")
OTHER_LABELS = ("주소", "소재지", "연락처", "이메일", "담당자", "면접자", "면접기업", "면접현황",
                "대표자", "전화")
STOP = job.stop_pattern(NAME_LABELS + BIRTH_LABELS + COMPANY_LABELS + INDUSTRY_LABELS
                        + INTERVIEW_DATE_LABELS + TIME_LABELS + PLACE_LABELS + JOB_LABELS + OTHER_LABELS)


@dataclass
class InterviewConfirmationResult:
    detected_type: DocType
    type_confidence: float
    fields: dict[str, ExtractedField]
    validations: list[common.Validation]
    warnings: list[str] = field(default_factory=list)
    diagnostics: dict[str, str] = field(default_factory=dict)


def _time_range(text: str) -> str | None:
    span = job.TIME_RANGE_RE.search(text)
    return f"{squash(span.group(1))}~{squash(span.group(2))}" if span else None


def _confirm_date(lines: list[list[Word]]) -> job.Hit | None:
    start = job.line_index_of(lines, CONFIRM_HINTS)
    if start is None:
        return None
    labeled = tuple(squash(label) for label in INTERVIEW_DATE_LABELS + BIRTH_LABELS)
    for line in lines[start:]:
        if any(label in squash(line_text(line)) for label in labeled):
            continue
        for value, words in job.dates_in_line(line):
            return job.Hit(value, " ".join(word.text for word in words), words, "(확인 문장 아래)", same_line=False)
    return None


def _companies(lines: list[list[Word]]) -> list[job.Hit]:
    """회사명 칸과 아래 서명란 회사명. 위치(쪽·세로) 순서로 돌려준다."""
    hits = job.find_all(lines, COMPANY_LABELS, job.parse_text, stop=STOP, below=False)
    unique: list[job.Hit] = []
    for hit in hits:
        if not any(hit.words and other.words and hit.words[0] is other.words[0] for other in unique):
            unique.append(hit)
    return sorted(unique, key=lambda hit: (hit.words[0].page, hit.words[0].cy) if hit.words else (0, 0.0))


def extract(pages: list[tuple[PageImage, OcrResult]], today: date | None = None) -> InterviewConfirmationResult:
    today = today or kst_today()
    page_map = {page.page: page for page, _ in pages}
    sources = common.sources_by_page(pages)
    lines, rrn_birth = job.page_lines(pages)
    flat = squash(job.text_of(lines))
    hint = job.find_hint(flat, TITLE_HINTS)
    detected = DocType.INTERVIEW_CONFIRM if hint else DocType.UNKNOWN
    type_confidence = 0.95 if hint else 0.2
    evidence = f"'{hint}' 단서" if hint else "면접확인서 단서를 찾지 못함"
    fields: dict[str, ExtractedField] = {}
    warnings: list[str] = []
    diagnostics: dict[str, str] = {"서류종류": evidence}

    name = job.find(lines, NAME_LABELS, job.parse_name, stop=STOP, below=False)
    birth = job.find(lines, BIRTH_LABELS, job.parse_date, stop=STOP, below=False)
    companies = _companies(lines)
    company = companies[0] if companies else None
    signed_company = companies[-1] if len(companies) > 1 else None
    industry = job.find(lines, INDUSTRY_LABELS, job.parse_text, stop=STOP, below=False)
    interview = job.find(lines, INTERVIEW_DATE_LABELS, job.parse_date, stop=STOP, below=False)
    place = job.find(lines, PLACE_LABELS, job.parse_text, stop=STOP, below=False)
    applied = job.find(lines, JOB_LABELS, job.parse_text, stop=STOP, below=False)
    confirmed = _confirm_date(lines)

    not_future = None if interview is None else interview.value <= today
    in_order = None if interview is None or confirmed is None else interview.value <= confirmed.value
    names_match = None if company is None or signed_company is None else job.same_company(
        str(company.value), str(signed_company.value))

    validations = [
        common.Validation("document_type", detected == DocType.INTERVIEW_CONFIRM, evidence),
        common.Validation("name_found", name is not None),
        common.Validation("company_found", company is not None),
        common.Validation("interview_date_found", interview is not None),
    ]
    if not_future is not None:
        validations.append(common.Validation("interview_date_not_future", not_future))
    if in_order is not None:
        validations.append(common.Validation("interview_not_after_confirmation", in_order))
    if names_match is not None:
        validations.append(common.Validation("company_names_match", names_match))

    if name is not None:
        fields["성명"] = job.to_field(name, [job.ocr_ok(name)], page_map, sources)
    else:
        diagnostics["성명"] = "라벨 '성명' 또는 값을 찾지 못함"
        warnings.append("성명을 찾지 못해 담당자 확인이 필요합니다.")
    if birth is not None:
        fields["생년월일"] = job.to_field(birth, [job.ocr_ok(birth)], page_map, sources)
    elif rrn_birth is not None:
        fields["생년월일"] = job.raw_field(rrn_birth, rrn_birth.isoformat(), [], [True], page_map, sources)
    if company is not None:
        checks = [job.ocr_ok(company)] + ([names_match] if names_match is not None else [])
        fields["회사명"] = job.to_field(company, checks, page_map, sources)
    else:
        diagnostics["회사명"] = "라벨 '회사명·기업명' 또는 값을 찾지 못함"
        warnings.append("회사명을 찾지 못해 담당자 확인이 필요합니다.")
    for label, hit in (("업태업종", industry), ("면접장소", place), ("응시직군", applied)):
        if hit is not None:
            fields[label] = job.to_field(hit, [job.ocr_ok(hit)], page_map, sources)
    if interview is not None:
        checks = [bool(not_future), job.ocr_ok(interview)] + ([in_order] if in_order is not None else [])
        fields["면접일"] = job.to_field(interview, checks, page_map, sources)
    if interview is not None and (time_text := _time_range(interview.raw)):
        fields["면접시간"] = job.raw_field(time_text, interview.raw, interview.words, [job.ocr_ok(interview)],
                                         page_map, sources)
    elif (time_hit := job.find(lines, TIME_LABELS, _time_range, stop=STOP, below=False)) is not None:
        fields["면접시간"] = job.to_field(time_hit, [job.ocr_ok(time_hit)], page_map, sources)
    if interview is None:
        diagnostics["면접일"] = "라벨 '면접일시' 또는 날짜를 찾지 못함 (서식의 '2026. 00. 00.' 그대로면 빈칸)"
        warnings.append("면접일을 찾지 못해 담당자 확인이 필요합니다.")
    if confirmed is not None:
        fields["확인일"] = job.to_field(confirmed, [confirmed.value <= today, job.ocr_ok(confirmed)],
                                        page_map, sources)

    if not_future is False:
        warnings.append("면접일이 오늘 이후로 읽혔습니다. 날짜를 잘못 읽었을 수 있습니다.")
    if in_order is False:
        warnings.append("면접일이 확인일보다 뒤입니다. 담당자가 확인합니다.")
    if names_match is False:
        warnings.append("면접기업 칸의 회사명과 서명란 회사명이 다릅니다. 담당자가 확인합니다.")

    return InterviewConfirmationResult(detected, type_confidence, fields, validations,
                                       list(dict.fromkeys(warnings)), diagnostics)

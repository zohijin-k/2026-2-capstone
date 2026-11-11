"""응시확인서·성적표 판독기 — 자격증 응시료 지원의 응시 증빙.

사업계획서는 '응시확인서 또는 성적표(응시일 표기 필수)'를 요구한다. 시행기관마다 서식이 달라
좌표를 고정하지 않고 라벨로 읽는다 (`job_common`). 한 부품이 두 서류를 판별한다(건강보험 두 서류가
`nhis_common`을 함께 쓰는 것과 같은 방식). 수험표는 시험 전에 받는 서류라 응시 사실을 증명하지
않으므로 응시서류로 판별하지 않는다.

추출 필드: 성명 · 생년월일(date) · 시험명 · 응시일(date) · 발급일(date)
서류 안 검증: 성명·응시일·시험명을 찾음, 응시일이 오늘 이후가 아님, 응시일 ≤ 발급일
인정 시험 목록·모집기간 대조는 하지 않는다 (도청 원본 목록을 받은 뒤 규칙에서).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from ..pipeline.layout import squash
from ..pipeline.ocr import OcrResult
from ..pipeline.preprocess import PageImage
from ..schemas.models import DocType, ExtractedField
from . import job_common as job
from . import nhis_common as common
from .resident_abstract import kst_today

EXAM_DOC_TYPES = (DocType.EXAM_ADMISSION, DocType.EXAM_SCORE)
ADMISSION_HINTS = ("응시확인서", "응시사실확인서", "응시증명서")
SCORE_HINTS = ("성적표", "성적통지서", "성적증명서", "성적확인서")
#: 수험표는 응시 사실을 증명하지 않는다.
NOT_EXAM_HINTS = ("수험표",)

NAME_LABELS = ("응시자성명", "수험자성명", "성명", "응시자", "수험자", "이름")
BIRTH_LABELS = ("생년월일",)
EXAM_NAME_LABELS = ("시험명", "자격종목", "응시종목", "시험종목", "검정종목", "종목명", "자격명", "종목")
EXAM_DATE_LABELS = ("응시일자", "응시일", "시험일자", "시험일시", "시험일", "검정일자", "검정일",
                    "시험시행일", "시행일자", "시행일")
ISSUE_LABELS = ("발급일자", "발급일시", "발급일", "발행일자", "발행일", "출력일자", "출력일시", "출력일")
OTHER_LABELS = ("수험번호", "응시번호", "시험장소", "고사장", "주소", "점수", "총점", "득점", "합격여부",
                "주민등록번호")
STOP = job.stop_pattern(NAME_LABELS + BIRTH_LABELS + EXAM_NAME_LABELS + EXAM_DATE_LABELS + ISSUE_LABELS
                        + OTHER_LABELS)


@dataclass
class ExamDocResult:
    detected_type: DocType
    type_confidence: float
    fields: dict[str, ExtractedField]
    validations: list[common.Validation]
    warnings: list[str] = field(default_factory=list)
    diagnostics: dict[str, str] = field(default_factory=dict)


def _detect(flat: str) -> tuple[DocType, float, str]:
    # 데모 분류(pdftext.DOC_TYPE_KEYWORDS)와 같은 순서: 응시확인서 → 성적표 → 수험표
    if hint := job.find_hint(flat, ADMISSION_HINTS):
        return DocType.EXAM_ADMISSION, 0.95, f"'{hint}' 단서"
    if hint := job.find_hint(flat, SCORE_HINTS):
        return DocType.EXAM_SCORE, 0.95, f"'{hint}' 단서"
    if hint := job.find_hint(flat, NOT_EXAM_HINTS):
        return DocType.UNKNOWN, 0.2, f"'{hint}' 단서 — 수험표는 응시 사실을 증명하지 않음"
    return DocType.UNKNOWN, 0.2, "응시확인서·성적표 단서를 찾지 못함"


def extract(pages: list[tuple[PageImage, OcrResult]], today: date | None = None) -> ExamDocResult:
    today = today or kst_today()
    page_map = {page.page: page for page, _ in pages}
    sources = common.sources_by_page(pages)
    lines, rrn_birth = job.page_lines(pages)
    flat = squash(job.text_of(lines))
    detected, type_confidence, evidence = _detect(flat)
    fields: dict[str, ExtractedField] = {}
    warnings: list[str] = []
    diagnostics: dict[str, str] = {"서류종류": evidence}
    if detected == DocType.UNKNOWN and job.find_hint(flat, NOT_EXAM_HINTS):
        warnings.append("수험표로 보입니다. 수험표는 응시 사실을 증명하지 않아 응시확인서 또는 성적표가 필요합니다.")

    name = job.find(lines, NAME_LABELS, job.parse_name, stop=STOP, below=False)
    birth = job.find(lines, BIRTH_LABELS, job.parse_date, stop=STOP, below=False)
    exam_name = job.find(lines, EXAM_NAME_LABELS, job.parse_text, stop=STOP, below=False)
    exam_date = job.find(lines, EXAM_DATE_LABELS, job.parse_date, stop=STOP)
    issue = job.find(lines, ISSUE_LABELS, job.parse_date, stop=STOP)

    not_future = None if exam_date is None else exam_date.value <= today
    in_order = None if exam_date is None or issue is None else exam_date.value <= issue.value

    validations = [
        common.Validation("document_type", detected in EXAM_DOC_TYPES, evidence),
        common.Validation("name_found", name is not None),
        common.Validation("exam_date_found", exam_date is not None),
        common.Validation("exam_name_found", exam_name is not None),
    ]
    if not_future is not None:
        validations.append(common.Validation("exam_date_not_future", not_future))
    if in_order is not None:
        validations.append(common.Validation("exam_date_not_after_issue", in_order))

    if name is not None:
        fields["성명"] = job.to_field(name, [job.ocr_ok(name)], page_map, sources)
    else:
        diagnostics["성명"] = "라벨 '성명' 또는 값을 찾지 못함"
        warnings.append("성명을 찾지 못해 담당자 확인이 필요합니다.")
    if birth is not None:
        fields["생년월일"] = job.to_field(birth, [job.ocr_ok(birth)], page_map, sources)
    elif rrn_birth is not None:
        fields["생년월일"] = job.raw_field(rrn_birth, rrn_birth.isoformat(), [], [True], page_map, sources)
    if exam_name is not None:
        fields["시험명"] = job.to_field(exam_name, [job.ocr_ok(exam_name)], page_map, sources)
    else:
        diagnostics["시험명"] = "라벨 '시험명·종목' 또는 값을 찾지 못함"
    if exam_date is not None:
        checks = [exam_date.same_line, bool(not_future), job.ocr_ok(exam_date)]
        if in_order is not None:
            checks.append(in_order)
        fields["응시일"] = job.to_field(exam_date, checks, page_map, sources)
    else:
        diagnostics["응시일"] = "라벨 '응시일·시험일' 또는 날짜를 찾지 못함"
        warnings.append("응시일을 찾지 못해 담당자 확인이 필요합니다.")
    if issue is not None:
        fields["발급일"] = job.to_field(issue, [issue.value <= today, job.ocr_ok(issue)], page_map, sources)

    if not_future is False:
        warnings.append("응시일이 오늘 이후로 읽혔습니다. 날짜를 잘못 읽었을 수 있습니다.")
    if in_order is False:
        warnings.append("응시일이 발급일보다 뒤입니다. 날짜를 잘못 읽었을 수 있습니다.")

    return ExamDocResult(detected, type_confidence, fields, validations, list(dict.fromkeys(warnings)), diagnostics)

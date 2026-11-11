"""결제영수증 판독기 — 면접정장비·면접사진비·자격증 응시료 실비의 근거 서류.

영수증은 가게·결제수단마다 모양이 달라 좌표를 고정하지 않고 라벨로 읽는다 (`job_common`).
카드 매출전표, 간이영수증, 온라인 결제 완료 화면, 계좌이체 확인증을 같은 부품이 읽는다.
접수확인서는 결제영수증을 대신할 수 없으므로(도청 문제 제안서) 영수증으로 판별하지 않는다.

추출 필드: 결제금액(int) · 결제일(date) · 상호 · 받는분(계좌이체) · 사업자등록번호 · 결제수단 ·
          공급가액(int) · 부가세(int) · 품목수(int)
서류 안 검증: 사업자등록번호 검증숫자, 공급가액+부가세=합계, 합계 표기 일치, 결제일이 오늘 이후가 아님,
            결제 취소 전표가 아님, 품목이 하나(여러 건 일괄결제가 아님)
지원 한도·지원연도·신청 금액 대조는 하지 않는다. 데모 기준 버전과 규칙팩이 본다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from ..pipeline.layout import Word, line_text, squash
from ..pipeline.ocr import OcrResult
from ..pipeline.preprocess import PageImage
from ..schemas.models import DocType, ExtractedField
from . import job_common as job
from . import nhis_common as common
from .resident_abstract import kst_today

TITLE_HINTS = ("영수증", "매출전표", "신용승인", "카드승인", "결제가완료", "결제완료", "결제내역",
               "이체확인증", "이체결과")
#: 제목이 잘린 카드 전표 사진·결제 화면: 결제 단서가 둘 이상이면 영수증으로 본다.
WEAK_HINTS = ("승인번호", "승인일시", "거래일시", "가맹점", "결제금액", "승인금액", "합계금액",
              "카드번호", "공급가액", "부가세", "사업자등록번호", "사업자번호")
#: 접수확인서는 결제영수증을 대신할 수 없다 (도청 문제 제안서).
NOT_RECEIPT_HINTS = ("접수확인서",)
CANCEL_HINTS = ("승인취소", "취소승인", "취소전표", "결제취소", "취소완료")

TOTAL_LABELS = ("총결제금액", "결제금액", "승인금액", "합계금액", "청구금액", "이체금액", "판매금액",
                "결제할금액", "받을금액", "총금액", "총액", "합계")
#: 표 머리 '금액' 아래 값은 합계 라벨이 하나도 없을 때만 쓴다.
AMOUNT_LABELS = TOTAL_LABELS + ("금액",)
AMOUNT_EXCLUDE = ("공급가액", "공급가", "부가세", "부가가치세", "봉사료", "할인", "받은금액", "받은돈",
                  "거스름", "잔액", "면세", "과세", "단가", "포인트", "적립", "수수료")
SUPPLY_LABELS = ("공급가액", "공급가")
VAT_LABELS = ("부가가치세", "부가세")
PAY_DATE_LABELS = ("결제일시", "결제일자", "결제일", "승인일시", "승인일자", "거래일시", "거래일자",
                   "이체일시", "이체일자", "판매일시", "판매일자", "구매일시", "구매일자", "주문일시",
                   "일시", "일자")
STORE_LABELS = ("가맹점명", "가맹점", "상호명", "상호", "판매자", "업체명", "매장명")
PAYEE_LABELS = ("받는분", "받는사람", "입금받는분", "수취인", "예금주")
BRN_LABELS = ("사업자등록번호", "사업자번호", "등록번호")
OTHER_LABELS = ("대표자", "주소", "전화", "카드종류", "카드번호", "승인번호", "할부", "주문번호", "상품명",
                "품목", "수량", "단가", "결제수단", "입금은행", "출금계좌", "입금계좌", "보내는분", "카드사")
PAYMENT_METHODS = (
    ("계좌이체", ("계좌이체", "이체확인", "이체금액", "이체일시", "무통장입금")),
    ("간편결제", ("카카오페이", "네이버페이", "토스페이", "페이코", "간편결제")),
    ("카드", ("신용카드", "체크카드", "카드승인", "신용승인", "카드번호", "카드종류", "매출전표")),
    ("현금", ("현금영수증", "현금")),
)
#: 품목으로 세지 않는 줄 (합계·세금·결제 정보 줄)
NOT_ITEM = tuple(squash(label) for label in TOTAL_LABELS + SUPPLY_LABELS + VAT_LABELS + PAY_DATE_LABELS
                 + BRN_LABELS + AMOUNT_EXCLUDE
                 + ("승인번호", "카드번호", "주문번호", "전화", "TEL", "대표", "주소", "할부", "금액"))
BULK_RE = re.compile(r"외\s*\d+\s*(?:건|개|종)")
STOP = job.stop_pattern(AMOUNT_LABELS + SUPPLY_LABELS + VAT_LABELS + PAY_DATE_LABELS + STORE_LABELS
                        + PAYEE_LABELS + BRN_LABELS + OTHER_LABELS)


@dataclass
class ReceiptResult:
    detected_type: DocType
    type_confidence: float
    fields: dict[str, ExtractedField]
    validations: list[common.Validation]
    warnings: list[str] = field(default_factory=list)
    diagnostics: dict[str, str] = field(default_factory=dict)


def _detect(flat: str) -> tuple[DocType, float, str]:
    if hint := job.find_hint(flat, NOT_RECEIPT_HINTS):
        return DocType.UNKNOWN, 0.2, f"'{hint}' 단서 — 접수확인서는 결제영수증을 대신할 수 없음"
    if hint := job.find_hint(flat, TITLE_HINTS):
        return DocType.RECEIPT, 0.95, f"'{hint}' 단서"
    weak = [hint for hint in WEAK_HINTS if squash(hint) in flat]
    if len(weak) >= 2:
        return DocType.RECEIPT, 0.75, f"제목 없이 결제 단서 {len(weak)}개 ({', '.join(weak[:3])})"
    return DocType.UNKNOWN, 0.2, "영수증 단서를 찾지 못함"


def _payment_method(flat: str) -> str | None:
    for method, hints in PAYMENT_METHODS:
        if job.find_hint(flat, hints):
            return method
    return None


def _item_lines(lines: list[list[Word]]) -> list[list[Word]]:
    """품목 줄: 품목 이름(글자)과 금액(쉼표 또는 '원')이 함께 있는 줄."""
    items = []
    for line in lines:
        text = line_text(line)
        flat = squash(text)
        if any(token in flat for token in NOT_ITEM) or not re.search(r"[가-힣A-Za-z]", text):
            continue
        if job.ITEM_AMOUNT_RE.search(text):
            items.append(line)
    return items


def _single_dated(lines: list[list[Word]]) -> job.Hit | None:
    """결제일 라벨이 없을 때: 서류에 날짜가 하나뿐이면 그 날짜."""
    found: dict[date, list[Word]] = {}
    for line in lines:
        for value, words in job.dates_in_line(line):
            found.setdefault(value, words)
    if len(found) != 1:
        return None
    value, words = next(iter(found.items()))
    return job.Hit(value, " ".join(word.text for word in words), words, "(라벨 없음)", same_line=False)


def extract(pages: list[tuple[PageImage, OcrResult]], today: date | None = None) -> ReceiptResult:
    today = today or kst_today()
    page_map = {page.page: page for page, _ in pages}
    sources = common.sources_by_page(pages)
    lines, _ = job.page_lines(pages)
    flat = squash(job.text_of(lines))
    detected, type_confidence, evidence = _detect(flat)
    fields: dict[str, ExtractedField] = {}
    warnings: list[str] = []
    diagnostics: dict[str, str] = {"서류종류": evidence}
    if detected == DocType.UNKNOWN and job.find_hint(flat, NOT_RECEIPT_HINTS):
        warnings.append("접수확인서로 보입니다. 접수확인서는 결제영수증을 대신할 수 없어 결제일이 적힌 영수증이 필요합니다.")

    amount = job.find(lines, AMOUNT_LABELS, job.parse_amount, stop=STOP, exclude=AMOUNT_EXCLUDE)
    totals = {hit.value for hit in job.find_all(lines, TOTAL_LABELS, job.parse_amount,
                                                stop=STOP, exclude=AMOUNT_EXCLUDE)}
    supply = job.find(lines, SUPPLY_LABELS, lambda text: job.parse_amount(text, minimum=0), stop=STOP)
    vat = job.find(lines, VAT_LABELS, lambda text: job.parse_amount(text, minimum=0), stop=STOP)
    paid = job.find(lines, PAY_DATE_LABELS, job.parse_short_year_date, stop=STOP)
    paid_labeled = paid is not None
    if paid is None:
        paid = _single_dated(lines)
    store = job.find(lines, STORE_LABELS, job.parse_text, stop=STOP, below=False)
    payee = job.find(lines, PAYEE_LABELS, job.parse_text, stop=STOP, below=False)
    brn = job.find(lines, BRN_LABELS, job.parse_brn, stop=STOP)
    method = _payment_method(flat)
    items = _item_lines(lines)
    bulk_mark = BULK_RE.search(job.text_of(lines))
    cancelled = job.find_hint(flat, CANCEL_HINTS)

    single_total = len(totals) <= 1
    vat_ok = None if amount is None or supply is None or vat is None else supply.value + vat.value == amount.value
    brn_ok = None if brn is None else job.brn_is_valid(str(brn.value))
    not_future = None if paid is None else paid.value <= today
    single_item = len(items) <= 1 and bulk_mark is None

    validations = [
        common.Validation("document_type", detected == DocType.RECEIPT, evidence),
        common.Validation("amount_found", amount is not None),
        common.Validation("payment_date_found", paid is not None),
    ]
    if not_future is not None:
        validations.append(common.Validation("payment_date_not_future", not_future))
    validations.append(common.Validation("single_total", single_total,
                                         "" if single_total else f"합계 표기 {len(totals)}가지"))
    if vat_ok is not None:
        validations.append(common.Validation("supply_plus_vat_matches", vat_ok))
    if brn_ok is not None:
        validations.append(common.Validation("brn_checksum", brn_ok))
    validations.append(common.Validation("not_cancelled", cancelled is None, cancelled or ""))
    validations.append(common.Validation("single_item", single_item, f"품목 줄 {len(items)}개"))

    if amount is not None:
        checks = [amount.label != "금액", single_total, job.ocr_ok(amount)]
        if vat_ok is not None:
            checks.append(vat_ok)
        fields["결제금액"] = job.to_field(amount, checks, page_map, sources)
    else:
        diagnostics["결제금액"] = "합계·결제금액 라벨 또는 값을 찾지 못함"
        warnings.append("결제금액을 찾지 못해 담당자 확인이 필요합니다.")
    if paid is not None:
        fields["결제일"] = job.to_field(paid, [paid_labeled, bool(not_future), job.ocr_ok(paid)],
                                        page_map, sources)
        if not paid_labeled:
            warnings.append("결제일 라벨이 없어 서류에 하나뿐인 날짜를 결제일로 읽었습니다.")
    else:
        diagnostics["결제일"] = "결제일·거래일시 라벨 또는 날짜를 찾지 못함"
        warnings.append("결제일을 찾지 못해 담당자 확인이 필요합니다.")
    if store is not None:
        fields["상호"] = job.to_field(store, [job.ocr_ok(store)] + ([brn_ok] if brn_ok is not None else []),
                                      page_map, sources)
    if payee is not None:
        fields["받는분"] = job.to_field(payee, [job.ocr_ok(payee)], page_map, sources)
    if brn is not None:
        fields["사업자등록번호"] = job.to_field(brn, [bool(brn_ok), job.ocr_ok(brn)], page_map, sources)
    if method is not None:
        fields["결제수단"] = job.raw_field(method, method, [], [True], page_map, sources)
    for name, hit in (("공급가액", supply), ("부가세", vat)):
        if hit is not None:
            fields[name] = job.to_field(hit, [vat_ok is not False, job.ocr_ok(hit)], page_map, sources)
    if items:
        item_words = [word for line in items for word in line]
        fields["품목수"] = job.raw_field(len(items), str(len(items)), item_words, [True], page_map, sources)

    if not single_total:
        warnings.append("영수증에 서로 다른 합계 금액이 있습니다. 담당자가 확인합니다.")
    if vat_ok is False:
        warnings.append("공급가액과 부가세의 합이 합계와 다릅니다. 금액을 잘못 읽었을 수 있습니다.")
    if brn_ok is False:
        warnings.append("사업자등록번호 검증숫자가 맞지 않습니다(오독이거나 잘못된 번호).")
    if not_future is False:
        warnings.append("결제일이 오늘 이후로 읽혔습니다. 날짜를 잘못 읽었을 수 있습니다.")
    if cancelled:
        warnings.append("결제 취소 전표로 보입니다. 담당자가 확인합니다.")
    if not single_item:
        count = f"{len(items)}개" if len(items) > 1 else "'외 n건' 표기"
        warnings.append(f"품목이 여러 개인 영수증입니다({count}). 여러 건을 한 번에 결제했다면 항목별 금액을 담당자가 확인합니다.")

    return ReceiptResult(detected, type_confidence, fields, validations, list(dict.fromkeys(warnings)), diagnostics)

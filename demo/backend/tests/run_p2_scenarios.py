"""P2 게이트 검증 스크립트.

저장소 루트에서:
    python -m demo.backend.tests.run_p2_scenarios

확인하는 것:
  1. 근로유형을 바꾸면 체크리스트가 실제로 바뀐다 (R3.2)
  2. 시나리오 S3~S6이 각각 WRONG_DOCUMENT_TYPE / DOCUMENT_ISSUED_TOO_EARLY /
     DECLARED_DATE_MISMATCH / UNREADABLE_FILE 로 판정된다 (R2.3)
  3. Tier2(PyMuPDF)가 실제 PDF에서 문서종류·발급일·가구원수·건보료·주소이력을 읽는다
  4. 암호 PDF·화면 캡처·병합 PDF 분리가 동작한다

pytest 없이 돌아간다. 더미 PDF는 실행 중에 만들고 끝나면 지운다 — 실제 서류나
개인정보는 쓰지 않는다.
"""

import shutil
import tempfile
from datetime import date
from pathlib import Path

from ..engine_adapter import apply_runtime_overrides
from ..ocr import read_document, split_pdf_pages
from ..ocr.fixture import FIXTURES
from ..rules.doc_check import (
    CODE_MISSING_ADDRESS_HISTORY,
    CODE_SCREEN_CAPTURE,
    check_document,
)
from ..rules.doc_types import DocType
from ..rules.programs import DOUBLE_SAVINGS, PROGRAMS
from ..rules.required_docs import (
    ApplicantDocInput,
    WorkCategory,
    build_checklist,
    find_slot,
    upload_slots,
)

PROGRAM = PROGRAMS[DOUBLE_SAVINGS]

_passed = 0
_failed: list[str] = []


def check(name: str, actual: object, expected: object) -> None:
    global _passed
    if actual == expected:
        _passed += 1
        print(f"  [OK]   {name}: {actual}")
    else:
        _failed.append(name)
        print(f"  [FAIL] {name}: 기대={expected!r} 실제={actual!r}")


def check_true(name: str, value: object) -> None:
    check(name, bool(value), True)


# ---------------------------------------------------------------- 더미 PDF 생성


def make_pdf(path: Path, lines: list[str], *, password: str | None = None) -> Path:
    """한글 텍스트 레이어가 있는 더미 PDF. 실제 서류가 아니라 문구만 흉내낸 것이다."""
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    writer = fitz.TextWriter(page.rect)
    font = fitz.Font("cjk")
    y = 80.0
    for line in lines:
        writer.append((60, y), line, font=font, fontsize=11)
        y += 24
    writer.write_text(page)
    if password:
        doc.save(path, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw=password)
    else:
        doc.save(path)
    doc.close()
    return path


def make_screenshot(path: Path) -> Path:
    """카메라 정보 없는 1920x1080 이미지 = 모니터 화면 캡처 휴리스틱 대상."""
    from PIL import Image

    Image.new("RGB", (1920, 1080), "white").save(path)
    return path


ABSTRACT_LINES = [
    "주민등록표 초본",
    "성명 : 홍길동",
    "주소변동 사항",
    "2020년 11월 20일 전입 전라북도 전주시 완산구",
    "발급일자 : 2026년 3월 5일",
]

NHIS_QUAL_LINES = [
    "건강보험 자격확인서",
    "성명 : 홍길동",
    "세대원수 : 4",
    "발급일자 : 2026년 3월 5일",
]

NHIS_PAY_LINES = [
    "건강보험료 납부확인서",
    "성명 : 홍길동",
    "고지금액 : 200,000",
    "발급일자 : 2026년 3월 5일",
]

CERTIFICATE_LINES = [
    "주민등록표 등본",
    "성명 : 홍길동",
    "세대주 및 관계",
    "발급일자 : 2026년 3월 5일",
]


# ---------------------------------------------------------------- 1. 체크리스트


def test_checklist() -> None:
    print("\n[1] 근로유형별 체크리스트 (R3.2)")

    base = build_checklist(PROGRAM, ApplicantDocInput())
    check("근로유형 미선택 시 업로드 슬롯 수", len(upload_slots(base)), 4)

    by_category: dict[str, list[str]] = {}
    for category in WorkCategory:
        items = build_checklist(PROGRAM, ApplicantDocInput(work_category=category))
        proof = find_slot(items, "work_proof")
        by_category[str(category)] = [str(r.doc_type) for r in upload_slots(items)]
        check(f"{category} → 근로확인서류", str(proof.doc_type) if proof else None, {
            WorkCategory.EMPLOYEE: str(DocType.INSURANCE_4),
            WorkCategory.LOCAL: str(DocType.DAILY_WORK_RECORD),
            WorkCategory.BUSINESS: str(DocType.BIZ_REG_PROOF),
            WorkCategory.FARM: str(DocType.FARM_BIZ_CERT),
            WorkCategory.FISHERY: str(DocType.FISHERY_BIZ_CERT),
        }[category])

    check("근로유형 5종의 목록이 모두 서로 다름", len({tuple(v) for v in by_category.values()}), 5)

    admin = build_checklist(
        PROGRAM,
        ApplicantDocInput(work_category=WorkCategory.EMPLOYEE, admin_fixed_term=True),
    )
    check_true("행정기관 기간제 → 근로계약서 추가", find_slot(admin, "labor_contract"))

    multi = build_checklist(
        PROGRAM,
        ApplicantDocInput(work_category=WorkCategory.EMPLOYEE, workplace_count=2),
    )
    check_true("복수 사업장 → work_proof_2 생성", find_slot(multi, "work_proof_2"))

    consent = find_slot(base, "admin_info_consent")
    check("서식5는 업로드 대상이 아님(전자서명 대체)", consent.upload if consent else None, False)

    handwritten = build_checklist(
        PROGRAM, ApplicantDocInput(handwritten_admin_consent=True)
    )
    slot = find_slot(handwritten, "admin_info_consent")
    check("자필 토글 시 서식5가 업로드 대상", slot.upload if slot else None, True)


# ---------------------------------------------------------------- 2. S3~S6


def test_scenarios_fixture() -> None:
    print("\n[2] 시나리오 S3~S6 — Tier1 fixture")
    checklist = build_checklist(
        PROGRAM, ApplicantDocInput(work_category=WorkCategory.EMPLOYEE)
    )
    abstract = find_slot(checklist, "resident_abstract")
    assert abstract is not None

    # S3 초본 자리에 등본
    ocr = FIXTURES["S3_주민등록등본_오제출"]
    r = check_document(abstract, ocr, date(2026, 3, 5))
    check("S3 상태", r.status, "FAIL")
    check("S3 사유", "WRONG_DOCUMENT_TYPE" in r.codes, True)

    # S4 공고일 이전 발급
    ocr = FIXTURES["S4_주민등록초본_발급일이전"]
    r = check_document(abstract, ocr, date(2026, 2, 28))
    check("S4 상태", r.status, "FAIL")
    check("S4 사유", "DOCUMENT_ISSUED_TOO_EARLY" in r.codes, True)

    # S5 입력 발급일 != 서류상 발급일 (사용자는 3/5로 입력, 서류는 3/10)
    ocr = FIXTURES["S5_주민등록초본_발급일불일치"]
    r = check_document(abstract, ocr, date(2026, 3, 5))
    check("S5 상태", r.status, "FAIL")
    check("S5 사유", "DECLARED_DATE_MISMATCH" in r.codes, True)

    # S6 암호 PDF
    ocr = FIXTURES["S6_주민등록초본_암호"]
    r = check_document(abstract, ocr, date(2026, 3, 5))
    check("S6 상태", r.status, "FAIL")
    check("S6 사유", "UNREADABLE_FILE" in r.codes, True)

    # S2 완전 적합
    ocr = FIXTURES["S2_주민등록초본_적합"]
    r = check_document(abstract, ocr, date(2026, 3, 5))
    check("S2 상태", r.status, "PASS")

    # S8 저신뢰 → 담당자 큐
    ocr = FIXTURES["S8_주민등록초본_저해상도"]
    r = check_document(abstract, ocr, date(2026, 3, 5))
    check("S8 상태", r.status, "NEEDS_REVIEW")
    check("S8 사유", "LOW_OCR_CONFIDENCE" in r.codes, True)

    # 공고문 미비 예시 ② 주소이력 미포함
    ocr = FIXTURES["S11_주민등록초본_주소이력없음"]
    r = check_document(abstract, ocr, date(2026, 3, 5))
    check("주소이력 미포함 사유", CODE_MISSING_ADDRESS_HISTORY in r.codes, True)

    # 공고문 미비 예시 ⑤ 화면 캡처 → 자동 반려가 아니라 담당자 확인
    ocr = FIXTURES["S12_주민등록초본_화면캡처"]
    r = check_document(abstract, ocr, date(2026, 3, 5))
    check("화면캡처 상태", r.status, "NEEDS_REVIEW")
    check("화면캡처 사유", CODE_SCREEN_CAPTURE in r.codes, True)

    # 해결 방법이 비어 있으면 안 된다 (R2.2)
    ocr = FIXTURES["S3_주민등록등본_오제출"]
    r = check_document(abstract, ocr, date(2026, 3, 5))
    check("S3 해결방법 제공", bool(r.findings[0].how_to_fix), True)
    check("S3 발급처 링크", r.findings[0].link, "https://www.gov.kr")


# ---------------------------------------------------------------- 3. Tier2


def test_pdftext(tmp: Path) -> None:
    print("\n[3] Tier2 — 실제 PDF 텍스트 판독 (PyMuPDF)")
    checklist = build_checklist(
        PROGRAM, ApplicantDocInput(work_category=WorkCategory.EMPLOYEE)
    )
    abstract = find_slot(checklist, "resident_abstract")
    qualification = find_slot(checklist, "nhis_qualification")
    payment = find_slot(checklist, "nhis_payment")
    assert abstract and qualification and payment

    path = make_pdf(tmp / "초본_실제.pdf", ABSTRACT_LINES)
    ocr = read_document(str(path), DocType.RESIDENT_ABSTRACT)
    check("Tier 확인", ocr.tier, "pdftext")
    check("문서종류 판별", str(ocr.detected_doc_type), str(DocType.RESIDENT_ABSTRACT))
    check("발급일 추출", ocr.issue_date, date(2026, 3, 5))
    check("주소변동내역", ocr.fields.get("주소변동내역"), "포함")
    check_true("발급일 bbox 확보", ocr.bboxes.get("발급일"))
    check("5초 이내 판독", ocr.elapsed_ms < 5000, True)
    check("판정", check_document(abstract, ocr, date(2026, 3, 5)).status, "PASS")

    path = make_pdf(tmp / "자격확인서_실제.pdf", NHIS_QUAL_LINES)
    ocr = read_document(str(path), DocType.NHIS_QUALIFICATION)
    check("자격확인서 판별", str(ocr.detected_doc_type), str(DocType.NHIS_QUALIFICATION))
    check("가구원수 추출", ocr.fields.get("가구원수"), "4")

    path = make_pdf(tmp / "납부확인서_실제.pdf", NHIS_PAY_LINES)
    ocr = read_document(str(path), DocType.NHIS_PAYMENT)
    check("납부확인서 판별", str(ocr.detected_doc_type), str(DocType.NHIS_PAYMENT))
    check("건보료 고지금액 추출", ocr.fields.get("건강보험료"), "200000")

    # S3을 실제 파일로도 재현 — 등본 PDF를 초본 슬롯에
    path = make_pdf(tmp / "등본_실제.pdf", CERTIFICATE_LINES)
    ocr = read_document(str(path), DocType.RESIDENT_ABSTRACT)
    check("등본 판별", str(ocr.detected_doc_type), str(DocType.RESIDENT_CERTIFICATE))
    r = check_document(abstract, ocr, date(2026, 3, 5))
    check("S3(실파일) 사유", "WRONG_DOCUMENT_TYPE" in r.codes, True)

    # S6을 실제 파일로도 재현 — 암호 PDF
    path = make_pdf(tmp / "초본_암호.pdf", ABSTRACT_LINES, password="1234")
    ocr = read_document(str(path), DocType.RESIDENT_ABSTRACT)
    check("암호 PDF 감지", ocr.is_encrypted, True)
    r = check_document(abstract, ocr, date(2026, 3, 5))
    check("S6(실파일) 사유", "UNREADABLE_FILE" in r.codes, True)

    # 화면 캡처 휴리스틱
    shot = make_screenshot(tmp / "capture.png")
    ocr = read_document(str(shot), DocType.RESIDENT_ABSTRACT)
    check("화면캡처 휴리스틱", ocr.is_screen_capture, True)
    r = check_document(abstract, ocr, None, "png")
    check("화면캡처는 자동반려 아님", r.status, "NEEDS_REVIEW")


# ---------------------------------------------------------------- 4. 병합 PDF


def test_merged(tmp: Path) -> None:
    print("\n[4] 병합 PDF 페이지 자동 분리 (R3.5)")
    import fitz

    parts = [
        make_pdf(tmp / "m1.pdf", ABSTRACT_LINES),
        make_pdf(tmp / "m2.pdf", NHIS_QUAL_LINES),
        make_pdf(tmp / "m3.pdf", NHIS_PAY_LINES),
    ]
    merged = fitz.open()
    for part in parts:
        with fitz.open(part) as d:
            merged.insert_pdf(d)
    merged_path = tmp / "merged.pdf"
    merged.save(merged_path)
    merged.close()

    out = tmp / "split"
    pages = split_pdf_pages(str(merged_path), out, "merged")
    check("분리된 페이지 수", len(pages), 3)
    check(
        "페이지별 문서종류",
        [str(r.detected_doc_type) for _, _, r in pages],
        [
            str(DocType.RESIDENT_ABSTRACT),
            str(DocType.NHIS_QUALIFICATION),
            str(DocType.NHIS_PAYMENT),
        ],
    )
    check("쪼갠 파일 실제 생성", all(p.exists() for _, p, _ in pages), True)

    # 슬롯 자동 배정 (documents.py 의 배정 로직과 같은 규칙)
    checklist = build_checklist(
        PROGRAM, ApplicantDocInput(work_category=WorkCategory.EMPLOYEE)
    )
    taken: set[str] = set()
    assigned: list[str] = []
    for _, _, ocr in pages:
        for candidate in checklist:
            if (
                candidate.upload
                and candidate.doc_type == ocr.detected_doc_type
                and candidate.slot_key not in taken
            ):
                taken.add(candidate.slot_key)
                assigned.append(candidate.slot_key)
                break
    check(
        "자동 배정된 슬롯",
        assigned,
        ["resident_abstract", "nhis_qualification", "nhis_payment"],
    )


def main() -> int:
    apply_runtime_overrides()
    tmp = Path(tempfile.mkdtemp(prefix="p2-scenarios-"))
    try:
        test_checklist()
        test_scenarios_fixture()
        test_pdftext(tmp)
        test_merged(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n통과 {_passed} / 실패 {len(_failed)}")
    if _failed:
        for name in _failed:
            print(f"  - {name}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

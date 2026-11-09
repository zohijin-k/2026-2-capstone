"""P8 검증 — 로컬 OCR 계층(engine_v2) 연결.

저장소 루트에서:
    python -m demo.backend.tests.run_p8_localocr_scenarios

확인하는 것:
  1. 텍스트 레이어가 없는 초본 PDF(브라우저 인쇄본)가 Tier1.5에서 읽힌다
     — 성명·생년월일·발급일·전북 연속 거주 시작일·주소변동내역, 그리고 원본 좌표
  2. 그 판독 결과로 데모 서류 판정(check_document)이 적합이 된다
  3. 등본을 올리면 오분류로 잡힌다
  4. 쪽마다 발급일이 다르게 읽히면 '부적합'이 아니라 '확인필요'로 간다 (오독 보호)
  5. OCR을 끄거나 서류를 못 알아보면 기존 계층으로 그대로 넘어간다 (회귀 없음)
  6. 텍스트 PDF 초본의 실제 제목 표기 "주민등록표 ( 초 본 )"를 Tier2가 분류한다
  7. 발급일 직접 입력 2차 검증: 판독이 확실할 때만 '불일치'로 반려하고,
     판독이 불확실하면 올바르게 입력한 신청자를 반려하지 않고 담당자 확인으로 보낸다
  8. 신청자 화면 응답에는 신청자가 확인할 값(발급일·성명 등)만 실린다

실제 OCR 엔진 대신, 실측 레이아웃을 본뜬 가짜 OCR 결과를 돌려주는 엔진을 끼운다.
개인정보·실물 서류는 쓰지 않는다. 임시 파일은 끝나면 지운다.
"""

import os
import shutil
import tempfile
from datetime import date
from pathlib import Path

from ..engine_adapter import apply_runtime_overrides
from ..ocr import read_document
from ..ocr.localocr import ENGINE_ENV
from ..rules.doc_check import check_document
from ..rules.doc_types import DocType
from ..rules.programs import DOUBLE_SAVINGS, PROGRAMS
from ..rules.required_docs import ApplicantDocInput, WorkCategory, build_checklist, find_slot

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


# ------------------------------------------------------------- 가짜 OCR 엔진

def install_fake_ocr(pages_words: list) -> None:
    """engine_v2 OCR 레지스트리에 'fake' 엔진을 끼운다. 호출될 때마다 다음 쪽을 돌려준다."""
    from engine_v2.pipeline import ocr as v2ocr

    it = iter(pages_words)
    v2ocr.ENGINES["fake"] = lambda png, size: next(it, [])
    os.environ[ENGINE_ENV] = "fake"


def fake_abstract_words(**kw) -> list:
    """engine_v2 테스트의 가짜 초본 3쪽 (실측 좌표 기반, 이름·주소는 가상)."""
    from engine_v2.tests.test_resident_abstract import build

    return [r.words for _, r in build(**kw)]


def make_image_pdf(path: Path, pages: int = 3) -> Path:
    """텍스트 레이어 없이 페이지 전체를 덮는 이미지 1장씩 — 브라우저 인쇄 초본과 같은 구조."""
    import fitz

    doc = fitz.open()
    for _ in range(pages):
        page = doc.new_page(width=595, height=842)
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 2066, 2923), False)
        pix.clear_with(245)
        page.insert_image(page.rect, pixmap=pix)
    doc.save(path)
    doc.close()
    return path


def make_text_pdf(path: Path, lines: list[str]) -> Path:
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    writer = fitz.TextWriter(page.rect)
    font = fitz.Font("cjk")
    for i, line in enumerate(lines):
        writer.append((60, 80 + 24 * i), line, font=font, fontsize=11)
    writer.write_text(page)
    doc.save(path)
    doc.close()
    return path


def abstract_slot():
    items = build_checklist(PROGRAM, ApplicantDocInput(work_category=WorkCategory.EMPLOYEE))
    return find_slot(items, "resident_abstract")


# ------------------------------------------------------------------ 시나리오

def test_image_abstract(tmp: Path) -> None:
    print("\n[1] 이미지 초본 PDF → 로컬 OCR 판독")
    pdf = make_image_pdf(tmp / "초본_이미지.pdf")
    install_fake_ocr(fake_abstract_words())
    ocr = read_document(str(pdf), DocType.RESIDENT_ABSTRACT)

    check("판독 계층", ocr.tier, "localocr")
    check("문서 종류", ocr.detected_doc_type, DocType.RESIDENT_ABSTRACT)
    check("발급일", ocr.issue_date, date(2026, 11, 10))
    check("성명", ocr.fields.get("성명"), "김전북")
    check("생년월일", ocr.fields.get("생년월일"), "1999-01-01")
    check("전북 연속 거주 시작(전입일)", ocr.fields.get("전입일"), "2023-08-30")
    check("주소변동내역", ocr.fields.get("주소변동내역"), "포함")
    check("현주소 시도", ocr.fields.get("현주소시도"), "전북")
    check("서류 내부 검증", ocr.fields.get("판독검증"), "9/9 통과")
    check("쪽 수", ocr.page_count, 3)
    check_true("신뢰도 ≥ 0.85 (엔진 임계값)", ocr.confidence >= 0.85)
    check_true("화질 ≥ 0.6", ocr.image_quality >= 0.6)
    for key in ("발급일", "성명", "전입일"):
        check_true(f"'{key}' 원본 좌표", key in ocr.bboxes)
    check_true("주민번호 뒷자리 미보존", all("1234567" not in v for v in ocr.fields.values()))

    print("\n[2] 그 판독으로 서류 판정")
    r = check_document(abstract_slot(), ocr, date(2026, 11, 10))
    check("판정", r.status, "PASS")


def test_register_instead(tmp: Path) -> None:
    print("\n[3] 이미지 등본을 초본 자리에")
    pdf = make_image_pdf(tmp / "등본_이미지.pdf")
    install_fake_ocr(fake_abstract_words(title="등 본"))
    ocr = read_document(str(pdf), DocType.RESIDENT_ABSTRACT)
    check("문서 종류", ocr.detected_doc_type, DocType.RESIDENT_CERTIFICATE)
    r = check_document(abstract_slot(), ocr, date(2026, 11, 10))
    check("판정", r.status, "FAIL")
    check_true("오분류 코드", any("WRONG" in c for c in r.codes))


def test_misread_goes_to_review(tmp: Path) -> None:
    print("\n[4] 한 쪽 발급일 오독 → 확인필요 (부적합 단정 금지)")
    pdf = make_image_pdf(tmp / "초본_오독.pdf")
    words = fake_abstract_words()
    for w in words[1]:
        if "년" in w.text and "월" in w.text:
            w.text = "2026년 11월 18일"
    install_fake_ocr(words)
    ocr = read_document(str(pdf), DocType.RESIDENT_ABSTRACT)
    check("발급일(다수결)", ocr.issue_date, date(2026, 11, 10))
    check_true("신뢰도 < 0.85", ocr.confidence < 0.85)
    check_true("검증 실패 항목 노출", "issue_date_consistent" in ocr.fields.get("판독검증실패", ""))
    r = check_document(abstract_slot(), ocr, date(2026, 11, 10))
    check("판정", r.status, "NEEDS_REVIEW")


def test_fallthrough(tmp: Path) -> None:
    print("\n[5] 로컬 OCR이 손 떼는 경우 → 기존 계층 그대로")
    pdf = make_image_pdf(tmp / "초본_ocr끔.pdf")
    os.environ[ENGINE_ENV] = "off"
    ocr = read_document(str(pdf), DocType.RESIDENT_ABSTRACT)
    check("OCR 끔 → 판독 실패 계층", ocr.tier, "none")

    from PIL import Image

    png = tmp / "화면캡처.png"
    Image.new("RGB", (1920, 1080), "white").save(png)
    install_fake_ocr([[]])  # 아무것도 못 읽음
    ocr = read_document(str(png), DocType.RESIDENT_ABSTRACT)
    check("못 알아본 사진 → Tier2", ocr.tier, "pdftext")
    check_true("화면 캡처 휴리스틱 유지", ocr.is_screen_capture)

    text_pdf = make_text_pdf(tmp / "초본_텍스트.pdf", ["주민등록표초본", "발급일자 : 2026년 3월 5일"])
    install_fake_ocr(fake_abstract_words())
    ocr = read_document(str(text_pdf), DocType.RESIDENT_ABSTRACT)
    check("텍스트 PDF → Tier2", ocr.tier, "pdftext")


def test_title_with_parentheses(tmp: Path) -> None:
    print("\n[6] Tier2: 실제 제목 표기 '주민등록표 ( 초 본 )'")
    os.environ[ENGINE_ENV] = "off"
    lines = ["이 초본은 개인별 주민등록표의 기재 내용을 그대로 증명합니다.",
             "주민등록표", "( 초   본 )", "2026년 11월 10일"]
    ocr = read_document(str(make_text_pdf(tmp / "초본_괄호.pdf", lines)), DocType.RESIDENT_ABSTRACT)
    check("문서 종류", ocr.detected_doc_type, DocType.RESIDENT_ABSTRACT)
    lines[0] = "이 등본은 세대별 주민등록표의 기재 내용을 그대로 증명합니다."
    lines[2] = "( 등   본 )"
    ocr = read_document(str(make_text_pdf(tmp / "등본_괄호.pdf", lines)), DocType.RESIDENT_ABSTRACT)
    check("등본 구분", ocr.detected_doc_type, DocType.RESIDENT_CERTIFICATE)


def test_declared_date_second_check(tmp: Path) -> None:
    print("\n[7] 발급일 직접 입력 2차 검증")
    slot = abstract_slot()

    install_fake_ocr(fake_abstract_words())
    ocr = read_document(str(make_image_pdf(tmp / "초본_정상.pdf")), DocType.RESIDENT_ABSTRACT)
    check("입력 = 판독 → 판정", check_document(slot, ocr, date(2026, 11, 10)).status, "PASS")

    install_fake_ocr(fake_abstract_words())
    ocr = read_document(str(make_image_pdf(tmp / "초본_입력오류.pdf")), DocType.RESIDENT_ABSTRACT)
    r = check_document(slot, ocr, date(2026, 11, 9))
    check("판독 확실 + 입력 틀림 → 판정", r.status, "FAIL")
    check_true("사유: DECLARED_DATE_MISMATCH", "DECLARED_DATE_MISMATCH" in r.codes)

    # 3쪽 중 2쪽의 발급일을 OCR이 잘못 읽음 → 다수결도 틀린 값, 쪽 간 불일치로 신뢰도 낮음
    words = fake_abstract_words()
    for page in (1, 2):
        for w in words[page]:
            if "년" in w.text and "월" in w.text:
                w.text = "2026년 11월 1일"
    install_fake_ocr(words)
    ocr = read_document(str(make_image_pdf(tmp / "초본_다수오독.pdf")), DocType.RESIDENT_ABSTRACT)
    check("다수결 발급일 (오독)", ocr.issue_date, date(2026, 11, 1))
    check_true("신뢰도 < 0.85", ocr.confidence < 0.85)
    r = check_document(slot, ocr, date(2026, 11, 10))
    check("판독 불확실 + 입력 맞음 → 판정", r.status, "NEEDS_REVIEW")
    check_true("사유: DECLARED_DATE_UNCERTAIN", "DECLARED_DATE_UNCERTAIN" in r.codes)
    check_true("'불일치' 단정 안 함", "DECLARED_DATE_MISMATCH" not in r.codes)


def test_applicant_payload() -> None:
    print("\n[8] 신청자 응답 — 담당자용 판독값 미포함")
    from datetime import datetime

    from ..api.common import APPLICANT_VISIBLE_FIELDS, document_dict
    from ..models import Document

    row = Document(
        application_id=1, slot_key="resident_abstract", file_path="초본.pdf", file_format="pdf",
        uploaded_at=datetime(2026, 11, 10, 9, 0),
        ocr_json={"tier": "localocr", "confidence": 0.95, "fields": {
            "발급일": "2026-11-10", "성명": "김전북", "생년월일": "1999-01-01", "전입일": "2023-08-30",
            "현주소시도": "전북", "주소이력건수": "9", "판독검증": "9/9 통과", "건강보험료": "200000",
        }},
    )
    shown = document_dict(row)["extracted"]
    check("신청자에게 보이는 판독값", sorted(shown), ["발급일", "성명"])
    check_true("허용 목록 밖의 값 없음", set(shown) <= set(APPLICANT_VISIBLE_FIELDS))


def main() -> int:
    apply_runtime_overrides()
    saved = os.environ.get(ENGINE_ENV)
    tmp = Path(tempfile.mkdtemp(prefix="p8-localocr-"))
    try:
        test_image_abstract(tmp)
        test_register_instead(tmp)
        test_misread_goes_to_review(tmp)
        test_fallthrough(tmp)
        test_title_with_parentheses(tmp)
        test_declared_date_second_check(tmp)
        test_applicant_payload()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        if saved is None:
            os.environ.pop(ENGINE_ENV, None)
        else:
            os.environ[ENGINE_ENV] = saved

    print(f"\n통과 {_passed} / 실패 {len(_failed)}")
    if _failed:
        for name in _failed:
            print(f"  - {name}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

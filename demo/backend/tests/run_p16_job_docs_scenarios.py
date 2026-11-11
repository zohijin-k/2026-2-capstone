"""P16 검증 — 취업지원패키지 추가서류 판독(engine_v2 receipt·exam_docs·interview_confirmation) 연결.

저장소 루트에서:
    python -m demo.backend.tests.run_p16_job_docs_scenarios

확인하는 것:
  1. 텍스트 PDF 영수증·면접확인서를 engine_v2 판독기가 읽어 데모 필드(결제금액·결제일·면접일 등)를 채운다
  2. 사진·스캔(이미지 PDF)도 같은 판독기로 읽힌다 — 카드 매출전표처럼 '영수증'이라는 말이 없어도 결제영수증
  3. 접수확인서·수험표를 올리면 '다른 서류'로 잡힌다 (초본 칸의 등본과 같은 처리)
  4. 이미지에서 응시일을 못 읽으면 부적합이 아니라 담당자 확인, 텍스트 PDF에 응시일이 없으면 지금처럼 부적합
  5. 필수 항목을 못 읽으면 문서 신뢰도가 올라가지 않는다

실제 OCR 엔진 대신 engine_v2 테스트의 가짜 OCR 결과를 돌려주는 엔진을 끼운다(p8과 같은 방식).
모든 이름·상호·번호는 가상이다. 임시 파일은 끝나면 지운다.
"""

import os
import random
import shutil
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

from ..engine_adapter import apply_runtime_overrides
from ..ocr import read_document
from ..ocr.localocr import ENGINE_ENV
from ..rules.doc_check import check_document
from ..rules.doc_types import DocType
from ..rules.identity import Identity
from ..rules.programs import JOB_PACKAGE, PROGRAMS
from ..rules.required_docs import ApplicantDocInput, build_checklist, find_slot
from ..rules.subsidy import Selection, SubsidyType

IDENTITY = Identity("김가상", date(1999, 1, 1))
#: 가짜 이미지 크기 = 250dpi A4 (데모 화질 기준에 걸리지 않게 p8과 같은 크기)
IMAGE_SIZE = (2066, 2923)

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


# ------------------------------------------------------------- 가짜 OCR·파일

def install_fake_ocr(pages_words: list) -> None:
    """engine_v2 OCR 레지스트리에 'fake' 엔진을 끼운다. 호출될 때마다 다음 쪽을 돌려준다."""
    from engine_v2.pipeline import ocr as v2ocr

    it = iter(pages_words)
    v2ocr.ENGINES["fake"] = lambda png, size: next(it, [])
    os.environ[ENGINE_ENV] = "fake"


def scaled(words: list, size: tuple[int, int]) -> list:
    """engine_v2 테스트의 가짜 단어(1000×1400 기준)를 가짜 이미지 크기로 옮긴다."""
    from engine_v2.pipeline.ocr import OcrWord

    sx, sy = IMAGE_SIZE[0] / size[0], IMAGE_SIZE[1] / size[1]
    return [OcrWord(w.text, w.confidence, (w.bbox_px[0] * sx, w.bbox_px[1] * sy, w.bbox_px[2] * sx, w.bbox_px[3] * sy))
            for w in words]


def make_image_pdf(path: Path) -> Path:
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, *IMAGE_SIZE), False)
    pix.clear_with(245)
    page.insert_image(page.rect, pixmap=pix)
    doc.save(path)
    doc.close()
    return path


def save_generated(layout, path: Path, seed: int = 1) -> dict:
    """engine_v2 합성기(make_job_docs)의 서류 모양 하나를 글자층 PDF로 저장하고 정답을 돌려준다."""
    doc, gt, _, _ = layout(random.Random(seed))
    doc.save(path)
    doc.close()
    return gt


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


def slots():
    items = build_checklist(PROGRAMS[JOB_PACKAGE], ApplicantDocInput(subsidy_selections=[
        Selection(SubsidyType.INTERVIEW, 1),
        Selection(SubsidyType.SUIT, 1, receipts=[45000]),
        Selection(SubsidyType.CERTIFICATE, 1, receipts=[19400]),
    ]))
    return {key: find_slot(items, key) for key in ("interview_1_confirmation", "suit_1_receipt", "certificate_1_exam")}


def codes(result) -> list[str]:
    return [finding.code for finding in result.findings]


# ------------------------------------------------------------------ 시나리오

def test_text_pdfs(tmp: Path) -> None:
    from engine_v2.tools import make_job_docs

    print("\n[1] 텍스트 PDF → engine_v2 패키지 판독기")
    gt = save_generated(make_job_docs.receipt_card, tmp / "card.pdf")
    ocr = read_document(str(tmp / "card.pdf"), DocType.PAYMENT_RECEIPT)
    check("영수증 판독 계층", (ocr.tier, ocr.engine), ("localocr", "pdftext"))
    check("영수증 종류", ocr.detected_doc_type, DocType.PAYMENT_RECEIPT)
    check("결제금액", ocr.fields.get("결제금액"), gt["amount"])
    check("결제일", ocr.fields.get("결제일"), gt["payment_date"])
    check("상호", ocr.fields.get("상호"), gt["store"])
    check_true("결제금액 원본 위치", ocr.bboxes.get("결제금액"))
    check("영수증 판정", check_document(slots()["suit_1_receipt"], ocr, None, "pdf", IDENTITY).status, "PASS")

    gt = save_generated(make_job_docs.interview_official, tmp / "interview.pdf")
    ocr = read_document(str(tmp / "interview.pdf"), DocType.INTERVIEW_CONFIRMATION)
    check("면접확인서 종류", ocr.detected_doc_type, DocType.INTERVIEW_CONFIRMATION)
    check("면접일", ocr.fields.get("면접일"), gt["interview_date"])
    check("회사명", ocr.fields.get("회사명"), gt["company"])
    check_true("주소·연락처는 읽지 않음", not {"주소", "연락처", "이메일"} & set(ocr.fields))
    owner = Identity(gt["name"], date.fromisoformat(gt["birth_date"]))
    check("면접확인서 판정", check_document(slots()["interview_1_confirmation"], ocr, None, "pdf", owner).status, "PASS")

    make_text_pdf(tmp / "exam_no_date.pdf", ["응 시 확 인 서", "성명 김가상", "종목명 정보처리기능사",
                                              "발급일자 2026. 4. 30.", "위 사실을 확인합니다."])
    ocr = read_document(str(tmp / "exam_no_date.pdf"), DocType.EXAM_CONFIRMATION)
    result = check_document(slots()["certificate_1_exam"], ocr, None, "pdf", IDENTITY)
    check("텍스트 PDF에 응시일 없음 → 부적합(그대로)", (result.status, codes(result)), ("FAIL", ["MISSING_REQUIRED_FIELD"]))


def test_image_receipt_without_title_word(tmp: Path) -> None:
    from engine_v2.tests.test_receipt import card_slip_words

    print("\n[2] 이미지 카드 매출전표 ('영수증'이라는 말 없음) → 결제영수증")
    install_fake_ocr([scaled(card_slip_words(), (1000, 1400))])
    ocr = read_document(str(make_image_pdf(tmp / "slip.pdf")), DocType.PAYMENT_RECEIPT)
    check("판독 계층·엔진", (ocr.tier, ocr.engine), ("localocr", "fake"))
    check("종류", ocr.detected_doc_type, DocType.PAYMENT_RECEIPT)
    check("결제금액", ocr.fields.get("결제금액"), "45000")
    check("결제일 (26/03/15)", ocr.fields.get("결제일"), "2026-03-15")
    check("판독검증", ocr.fields.get("판독검증"), "9/9 통과")
    check("판정", check_document(slots()["suit_1_receipt"], ocr, None, "pdf", IDENTITY).status, "PASS")


def test_lookalikes_are_wrong_documents(tmp: Path) -> None:
    from engine_v2.tests.test_receipt import wd

    print("\n[3] 접수확인서·수험표 → 다른 서류")
    install_fake_ocr([scaled([wd(30, 3, "원서접수확인서", 20), wd(10, 8, "종목명"), wd(30, 8, "정보처리기능사", 16),
                              wd(10, 10, "응시수수료"), wd(30, 10, "19,400원")], (1000, 1400))])
    ocr = read_document(str(make_image_pdf(tmp / "registration.pdf")), DocType.PAYMENT_RECEIPT)
    check("접수확인서 분류", ocr.detected_doc_type, DocType.REGISTRATION_CONFIRMATION)
    result = check_document(slots()["suit_1_receipt"], ocr, None, "pdf", IDENTITY)
    check("영수증 칸에 접수확인서", (result.status, codes(result)), ("FAIL", ["WRONG_DOCUMENT_TYPE"]))

    install_fake_ocr([scaled([wd(40, 4, "수 험 표", 20), wd(10, 12, "성명"), wd(25, 12, "김가상"),
                              wd(10, 15, "시험일시"), wd(25, 15, "2026. 4. 12. 09:00", 18)], (1000, 1400))])
    ocr = read_document(str(make_image_pdf(tmp / "ticket.pdf")), DocType.EXAM_CONFIRMATION)
    check("수험표 분류", ocr.detected_doc_type, DocType.ADMISSION_TICKET)
    result = check_document(slots()["certificate_1_exam"], ocr, None, "pdf", IDENTITY)
    check("응시서류 칸에 수험표", (result.status, codes(result)), ("FAIL", ["WRONG_DOCUMENT_TYPE"]))


def test_unread_exam_date_goes_to_review(tmp: Path) -> None:
    from engine_v2.tests.test_exam_docs import admission_words

    print("\n[4] 이미지 응시확인서에서 응시일을 못 읽음 → 담당자 확인 (부적합 아님)")
    install_fake_ocr([scaled(admission_words(), (1000, 1400))])
    ocr = read_document(str(make_image_pdf(tmp / "exam.pdf")), DocType.EXAM_CONFIRMATION)
    check("응시일을 읽으면", ocr.fields.get("응시일"), "2026-04-12")
    check("응시일을 읽으면 판정", check_document(slots()["certificate_1_exam"], ocr, None, "pdf", IDENTITY).status, "PASS")

    install_fake_ocr([scaled(admission_words(exam_date=""), (1000, 1400))])
    ocr = read_document(str(make_image_pdf(tmp / "exam_unread.pdf")), DocType.EXAM_CONFIRMATION)
    check("응시일 미판독 시 문서 신뢰도", ocr.confidence, 0.5)
    result = check_document(slots()["certificate_1_exam"], ocr, None, "pdf", IDENTITY)
    check("응시일 미판독 판정", result.status, "NEEDS_REVIEW")
    check_true("사유는 미판독(확인필요)", "REQUIRED_FIELD_UNREADABLE" in codes(result))
    check_true("부적합 사유 없음", all(finding.severity != "FAIL" for finding in result.findings))


def make_boundary_pdf(path: Path, characters: int) -> Path:
    """응시일 없는 합성 본문을 get_text().strip() 기준 지정 글자수로 만든다."""
    lines = ["응 시 확 인 서", "성명 김가상", "종목명 정보처리기능사", "발급일자 2026. 4. 30."]
    padding = characters - len("\n".join(lines)) - 1
    assert padding > 0, "경계 본문은 합성 기본 본문보다 길어야 한다"
    return make_text_pdf(path, [*lines, "가" * padding])


def test_source_boundaries(tmp: Path) -> None:
    import fitz

    from engine_v2.pipeline import ocr as v2ocr
    from engine_v2.pipeline.preprocess import PageSource, TEXT_LAYER_MIN_CHARS, preprocess
    from engine_v2.tests.test_exam_docs import admission_words
    from ..ocr.localocr import LocalOcr

    print("\n[5] 글자층 경계 -1/정확히/+1: 필수 항목 없음과 OCR 미판독 구분")
    for characters in (TEXT_LAYER_MIN_CHARS - 1, TEXT_LAYER_MIN_CHARS, TEXT_LAYER_MIN_CHARS + 1):
        path = make_boundary_pdf(tmp / f"synthetic-boundary-{characters}.pdf", characters)
        with fitz.open(path) as doc:
            check(f"경계 {characters} 실제 추출 글자수", len(doc[0].get_text().strip()), characters)
        text_only = characters >= TEXT_LAYER_MIN_CHARS
        check(f"경계 {characters} 실제 페이지 출처", preprocess(path)[0].source,
              PageSource.TEXT_LAYER if text_only else PageSource.RENDER)
        run = Mock(return_value=scaled(admission_words(exam_date=""), (1000, 1400)))
        with patch.dict(os.environ, {ENGINE_ENV: "own"}), patch.dict(v2ocr.ENGINES, {"own": run}):
            ocr = LocalOcr().read(str(path), DocType.EXAM_CONFIRMATION)
        check(f"경계 {characters} OCR 호출 수", run.call_count, 0 if text_only else 1)
        check(f"경계 {characters} 실제 엔진", ocr.engine, "pdftext" if text_only else "own")
        check(f"경계 {characters} 신뢰도", ocr.confidence, 0.9 if text_only else 0.5)
        check_true(f"경계 {characters} 응시일을 채우지 않음", "응시일" not in ocr.fields)
        result = check_document(slots()["certificate_1_exam"], ocr, None, "pdf", IDENTITY)
        expected = (("FAIL", ["MISSING_REQUIRED_FIELD"]) if text_only else
                    ("NEEDS_REVIEW", ["LOW_OCR_CONFIDENCE", "REQUIRED_FIELD_UNREADABLE"]))
        check(f"경계 {characters} 판정·사유", (result.status, codes(result)), expected)

    # 첫 쪽만 검사하거나 engine='text_layer'를 실제 OCR 엔진으로 기록하는 회귀를 막는다.
    for order in ((TEXT_LAYER_MIN_CHARS + 1, TEXT_LAYER_MIN_CHARS - 1),
                  (TEXT_LAYER_MIN_CHARS - 1, TEXT_LAYER_MIN_CHARS + 1)):
        path = tmp / f"synthetic-mixed-{order[0]}.pdf"
        with fitz.open() as doc:
            for characters in order:
                with fitz.open(tmp / f"synthetic-boundary-{characters}.pdf") as source:
                    doc.insert_pdf(source)
            doc.save(path)
        with patch.dict(os.environ, {ENGINE_ENV: "own"}), \
                patch.dict(v2ocr.ENGINES, {"own": lambda png, size: scaled(admission_words(exam_date=""), (1000, 1400))}):
            ocr = LocalOcr().read(str(path), DocType.EXAM_CONFIRMATION)
        check(f"혼합 {order} 실제 엔진·신뢰도", (ocr.engine, ocr.confidence, ocr.page_count), ("own", 0.5, 2))
        result = check_document(slots()["certificate_1_exam"], ocr, None, "pdf", IDENTITY)
        check(f"혼합 {order} 판정·사유", (result.status, codes(result)),
              ("NEEDS_REVIEW", ["LOW_OCR_CONFIDENCE", "REQUIRED_FIELD_UNREADABLE"]))


def test_png_and_complete_text(tmp: Path) -> None:
    from PIL import Image
    from engine_v2.pipeline import ocr as v2ocr
    from engine_v2.tests.test_exam_docs import admission_words
    from ..ocr.localocr import LocalOcr

    print("\n[6] PNG 미판독은 담당자 확인·재촬영 안내, 응시일 있는 PNG/글자층은 PASS")
    image = tmp / "synthetic-exam.png"
    Image.new("RGB", IMAGE_SIZE, "white").save(image, dpi=(250, 250))
    for present in (False, True):
        words = scaled(admission_words() if present else admission_words(exam_date=""), (1000, 1400))
        with patch.dict(os.environ, {ENGINE_ENV: "own"}), \
                patch.dict(v2ocr.ENGINES, {"own": lambda png, size: words}):
            ocr = LocalOcr().read(str(image), DocType.EXAM_CONFIRMATION)
        check(f"PNG 응시일 {present} 실제 엔진", ocr.engine, "own")
        check(f"PNG 응시일 {present} 추출", ocr.fields.get("응시일"), "2026-04-12" if present else None)
        check(f"PNG 응시일 {present} 신뢰도", ocr.confidence, 0.95 if present else 0.5)
        result = check_document(slots()["certificate_1_exam"], ocr, None, "png", IDENTITY)
        check(f"PNG 응시일 {present} 판정", result.status, "PASS" if present else "NEEDS_REVIEW")
        check_true(f"PNG 응시일 {present} FAIL 없음", all(f.severity != "FAIL" for f in result.findings))
        if not present:
            check("PNG 미판독 사유", codes(result), ["LOW_OCR_CONFIDENCE", "REQUIRED_FIELD_UNREADABLE"])
            check_true("PNG 미판독 재촬영 안내", any("다시 찍어 올리면" in f.how_to_fix for f in result.findings))

    pdf = make_text_pdf(tmp / "synthetic-complete.pdf", [
        "응 시 확 인 서", "성명 김가상", "생년월일 1999. 01. 01.", "종목명 정보처리기능사",
        "시험일자 2026. 4. 12.", "발급일자 2026. 4. 30.",
    ])
    with patch.object(v2ocr, "run_ocr", side_effect=AssertionError("글자층은 OCR을 호출하지 않음")):
        ocr = LocalOcr().read(str(pdf), DocType.EXAM_CONFIRMATION)
    check("응시일 있는 글자층 엔진·필드", (ocr.engine, ocr.fields.get("응시일")), ("pdftext", "2026-04-12"))
    check("응시일 있는 글자층 신뢰도 유지", ocr.confidence, 0.95)
    result = check_document(slots()["certificate_1_exam"], ocr, None, "pdf", IDENTITY)
    check("응시일 있는 글자층 판정·사유", (result.status, codes(result)), ("PASS", []))


def test_job_upload_privacy(tmp: Path) -> None:
    from fastapi.testclient import TestClient
    from engine_v2.pipeline import ocr as v2ocr
    from engine_v2.pipeline.preprocess import TEXT_LAYER_MIN_CHARS
    from engine_v2.tests.test_exam_docs import admission_words
    from .. import models
    from ..main import app
    from . import run_p4_scenarios as p4
    from .run_p9_identity_scenarios import identify

    print("\n[7] 취업서류 업로드·목록·체크리스트에서 엔진 문자열·메타데이터 비노출")
    p4._isolate(tmp)
    with TestClient(app) as client:
        app_id = client.post("/api/applications", json={"program_code": JOB_PACKAGE}).json()["id"]
        check("합성 신청인 인증", identify(client, app_id, IDENTITY.name, "1999-01-01").status_code, 200)
        response = client.post(f"/api/applications/{app_id}/subsidy-items", json={"items": [
            {"item_type": "certificate", "count": 1, "receipts": [19400]},
        ]})
        check("합성 응시료 슬롯 생성", response.status_code, 200)
        cases = [(tmp / f"synthetic-boundary-{size}.pdf", "application/pdf", status)
                 for size, status in ((TEXT_LAYER_MIN_CHARS - 1, "NEEDS_REVIEW"),
                                      (TEXT_LAYER_MIN_CHARS, "FAIL"), (TEXT_LAYER_MIN_CHARS + 1, "FAIL"))]
        cases += [(tmp / "synthetic-exam.png", "image/png", "NEEDS_REVIEW"),
                  (tmp / "synthetic-complete.pdf", "application/pdf", "PASS")]
        for path, content_type, expected in cases:
            with patch.dict(os.environ, {ENGINE_ENV: "own"}), \
                    patch.dict(v2ocr.ENGINES, {"own": lambda png, size: scaled(admission_words(exam_date=""), (1000, 1400))}), \
                    path.open("rb") as stream:
                response = client.post(f"/api/applications/{app_id}/documents",
                    files={"file": (path.name, stream, content_type)},
                    data={"slot_key": "certificate_1_exam", "declared_issue_date": "2026-04-30"})
            check(f"합성 업로드 {path.name} HTTP", response.status_code, 200)
            check(f"합성 업로드 {path.name} 판정", response.json().get("status"), expected)
            for label, output in (("업로드", response),
                                  ("목록", client.get(f"/api/applications/{app_id}/documents")),
                                  ("체크리스트", client.get(f"/api/applications/{app_id}/required-documents"))):
                check_true(f"{path.name} {label} 엔진 비노출",
                           all(token not in output.text for token in ("engine", "pdftext", "own", "fallback_reason", "quality_note")))
    models.engine.dispose()


def main() -> int:
    apply_runtime_overrides()
    saved = os.environ.get(ENGINE_ENV)
    tmp = Path(tempfile.mkdtemp(prefix="p16-jobdocs-"))
    try:
        test_text_pdfs(tmp)
        test_image_receipt_without_title_word(tmp)
        test_lookalikes_are_wrong_documents(tmp)
        test_unread_exam_date_goes_to_review(tmp)
        test_source_boundaries(tmp)
        test_png_and_complete_text(tmp)
        test_job_upload_privacy(tmp)
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

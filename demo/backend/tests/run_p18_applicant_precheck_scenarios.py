"""P18 신청자 사전 검사. 합성 OCR·합성 이미지와 임시 DB/저장소만 사용한다.

쪽·본인 항목은 p16 방식의 가짜 OCR로 추출기부터 API까지 검사한다.
신뢰도 분기는 합성 규칙 입력으로, 흐림·회전은 합성 PNG의 실제 own CPU OCR로 검사한다.
"""

import json
import os
import tempfile
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from ..engine_adapter import apply_runtime_overrides, engine_config
from ..ocr.base import OcrResult
from ..ocr.localocr import ENGINE_ENV, LocalOcr
from ..rules.doc_check import check_document
from ..rules.doc_types import DocType
from ..rules.identity import Identity
from ..rules.required_docs import DocRequirement
from . import run_p4_scenarios as p4
from .run_p8_localocr_scenarios import abstract_slot, make_image_pdf
from .run_p9_identity_scenarios import identify, new_app

IDENTITY = Identity("김전북", date(1999, 1, 1))
OTHER_NAME, OTHER_BIRTH = "이합성", "1998-02-03"
_passed = 0
_failed: list[str] = []


def check(name, actual, expected):
    global _passed
    if actual == expected:
        _passed += 1
        print(f"  [OK]   {name}")
    else:
        _failed.append(name)
        print(f"  [FAIL] {name}: 기대={expected!r} 실제={actual!r}")


def review(name, result, code):
    check(name + " 상태", result.status, "NEEDS_REVIEW")
    check(name + " 사유", code in result.codes, True)
    check(name + " FAIL 없음", all(f.severity != "FAIL" for f in result.findings), True)
    check(name + " 재촬영 안내", all(bool(f.how_to_fix) for f in result.findings), True)


def quality_rejection(name, result):
    check(name + " 상태", result.status, "FAIL")
    check(name + " 사유", "LOW_IMAGE_QUALITY" in result.codes, True)
    check(name + " 확정 화질 FAIL", any(f.code == "LOW_IMAGE_QUALITY" and f.severity == "FAIL" for f in result.findings), True)
    check(name + " PDF 재발급 안내", any("PDF로 받아" in f.how_to_fix for f in result.findings if f.code == "LOW_IMAGE_QUALITY"), True)


def resident_words(marker="1/1", *, name=IDENTITY.name, birth="1999-01-01", index=0):
    from engine_v2.tests.test_resident_abstract import header, row, table_head

    words = header(1, 1, name=name, applicant=f"신청인: {name} ({birth})")
    for word in words:
        if word.text == "1/1":
            word.text = marker
        elif word.text == "990101-1234567" and birth == OTHER_BIRTH:
            word.text = "980203-1******"
    first_date = date(2020, 1, 1) if index == 0 else date(2023, 1, 1) + timedelta(days=2 * index - 1)
    second_date = date(2023, 1, 1) if index == 0 else date(2023, 1, 1) + timedelta(days=2 * index)
    return words + table_head(31.8) + [
        *row(34.4, 1 + index * 2, "전북특별자치도 전주시 가상동", first_date.isoformat()),
        *row(39.4, 2 + index * 2, "전북특별자치도 전주시 합성동", second_date.isoformat()),
    ]


def read_fake(tmp, name, words):
    from engine_v2.pipeline import ocr as v2ocr

    path = make_image_pdf(tmp / f"synthetic-{name}.pdf", pages=len(words))
    pending = iter(words)
    with patch.dict(os.environ, {ENGINE_ENV: "p18-synthetic"}), \
            patch.dict(v2ocr.ENGINES, {"p18-synthetic": lambda png, size: next(pending)}):
        result = LocalOcr().read(str(path), None)
    assert result is not None, "합성 판독 결과 없음"
    return result


def test_pages(tmp):
    req = abstract_slot()
    cases = {
        "one": ([resident_words()], "PASS", None),
        "two": ([resident_words("1/2"), resident_words("2/2", index=1)], "PASS", None),
        "missing": ([resident_words("1/2")], "FAIL", "PAGES_INCOMPLETE"),
        "unread": ([resident_words("읽기불가")], "NEEDS_REVIEW", "PAGES_UNREADABLE"),
        "duplicate-missing": ([resident_words("1/2"), resident_words("1/2")], "FAIL", "PAGES_INCOMPLETE"),
        "duplicate-missing-distinct-body": ([resident_words("1/2"), resident_words("1/2", index=1)], "FAIL", "PAGES_INCOMPLETE"),
        "duplicate": ([resident_words(), resident_words()], "FAIL", "PAGES_DUPLICATED"),
        "duplicate-distinct-body": ([resident_words(), resident_words(index=1)], "FAIL", "PAGES_DUPLICATED"),
        "totals": ([resident_words("1/2"), resident_words("2/3", index=1)], "NEEDS_REVIEW", "PAGES_UNREADABLE"),
        "partly-unread": ([resident_words("1/2"), resident_words("읽기불가", index=1)], "NEEDS_REVIEW", "PAGES_UNREADABLE"),
        "out-of-range": ([resident_words("2/1")], "NEEDS_REVIEW", "PAGES_UNREADABLE"),
    }
    results = {}
    for name, (words, status, code) in cases.items():
        ocr = read_fake(tmp, name, words)
        result = check_document(req, ocr, identity=IDENTITY)
        results[name] = ocr
        check(name + " 초본 판정", result.status, status)
        if code:
            check(name + " 쪽 사유", code in result.codes, True)
        if status == "NEEDS_REVIEW":
            review(name, result, code)
        if name == "missing":
            check("누락 문구 N/M", "2쪽 중 1쪽" in result.findings[0].message, True)
    for name in ("duplicate-missing", "duplicate"):
        original = results[name]
        low_type = replace(original, classification_confidence=engine_config.OCR_CONFIDENCE_THRESHOLD - .01)
        review(name + " 낮은 종류 신뢰도", check_document(req, low_type, identity=IDENTITY), "PAGES_UNREADABLE")
        data = json.loads(original.fields["쪽표기자료"])
        data["confidence"] = engine_config.OCR_CONFIDENCE_THRESHOLD - .01
        low_page = replace(original, fields=dict(original.fields, 쪽표기자료=json.dumps(data)))
        review(name + " 낮은 쪽 신뢰도", check_document(req, low_page, identity=IDENTITY), "PAGES_UNREADABLE")
    low_marker = resident_words("1/2")
    next(w for w in low_marker if w.text == "1/2").confidence = engine_config.OCR_CONFIDENCE_THRESHOLD - 0.01
    review("낮은 쪽표기 신뢰도", check_document(req, read_fake(tmp, "low-marker", [low_marker]), identity=IDENTITY), "PAGES_UNREADABLE")
    low = replace(results["missing"], confidence=engine_config.OCR_CONFIDENCE_THRESHOLD - 0.01)
    review("낮은 문서 신뢰도 누락", check_document(req, low, identity=IDENTITY), "PAGES_UNREADABLE")
    return results["one"]


def test_uncertainty(complete):
    req = abstract_slot()
    threshold = engine_config.OCR_CONFIDENCE_THRESHOLD
    for confidence, status in ((threshold, "FAIL"), (threshold - 0.01, "NEEDS_REVIEW")):
        fields = dict(complete.fields, 초본신청인성명=OTHER_NAME, 초본신청인생년월일=OTHER_BIRTH)
        result = check_document(req, replace(complete, fields=fields, confidence=confidence), identity=IDENTITY)
        check(f"본인 불일치 {confidence} 판정", result.status, status)
        if status == "NEEDS_REVIEW":
            review("낮은 본인 불일치", result, "IDENTITY_UNCERTAIN")
        for future in (False, True):
            compared = replace(req, min_issue_date=date(2026, 3, 3), max_issue_date=date(2026, 11, 12))
            value = "2026-11-13" if future else "2025-11-10"
            ocr = replace(complete, confidence=confidence, fields=dict(complete.fields, 발급일=value), issue_date=date.fromisoformat(value))
            result = check_document(compared, ocr, identity=IDENTITY)
            code = "DOCUMENT_ISSUED_AFTER_APPLICATION" if future else "DOCUMENT_ISSUED_TOO_EARLY"
            check(f"날짜 {value} 신뢰도 {confidence}", result.status, status)
            check("날짜 비교 코드", code in result.codes, True)
            if status == "NEEDS_REVIEW":
                review("낮은 날짜 판독", result, code)
        wrong = replace(complete, detected_doc_type=DocType.RESIDENT_CERTIFICATE, confidence=confidence, classification_confidence=confidence)
        result = check_document(req, wrong, identity=IDENTITY)
        check(f"종류 불일치 {confidence}", result.status, status)
        if status == "NEEDS_REVIEW":
            review("낮은 종류 판독", result, "WRONG_DOCUMENT_TYPE")
        payment = DocRequirement("nhis_payment", DocType.NHIS_PAYMENT, "납부확인서", premium_months=["2025-10", "2025-11"])
        ocr = OcrResult(DocType.NHIS_PAYMENT, confidence, fields={"월별고지금액": '{"2025-10":"100000"}'})
        result = check_document(payment, ocr)
        check(f"월 누락 {confidence}", result.status, "NEEDS_REVIEW")
        review("조회범위 없는 고지월 판독", result, "MISSING_BILLING_MONTHS")
    wrong = replace(complete, detected_doc_type=DocType.RESIDENT_CERTIFICATE, classification_confidence=threshold - 0.01)
    review("종류만 저신뢰", check_document(req, wrong), "WRONG_DOCUMENT_TYPE")
    history = DocRequirement("nhis_acquisition_loss", DocType.NHIS_ACQUISITION_LOSS, "자격득실확인서", recent_years=5)
    review("조회기간 미판독", check_document(history, OcrResult(DocType.NHIS_ACQUISITION_LOSS, 1.0, fields={"자격이력자료": "읽기실패"})), "NHIS_HISTORY_PERIOD_UNREADABLE")
    review("조회기간 자료 없음", check_document(history, OcrResult(DocType.NHIS_ACQUISITION_LOSS, 1.0)), "NHIS_HISTORY_PERIOD_UNREADABLE")
    quality_rejection("저화질", check_document(req, replace(complete, image_quality=engine_config.IMAGE_QUALITY_THRESHOLD - 0.01), identity=IDENTITY))
    for field in ("초본신청인성명", "초본신청인생년월일"):
        fields = dict(complete.fields)
        fields.pop(field)
        review("초본 " + field, check_document(req, replace(complete, fields=fields), identity=IDENTITY), "RESIDENT_APPLICANT_UNREADABLE")
    outside = DocRequirement("work_proof", DocType.FARM_BIZ_CERT, "농업경영체증명")
    check("본인 항목 없는 종류는 범위 밖", check_document(outside, OcrResult(DocType.FARM_BIZ_CERT, 1.0), identity=IDENTITY).status, "PASS")


def test_insurance(tmp):
    from engine_v2.tests.test_insurance_4 import employed_words
    from .run_p16_job_docs_scenarios import scaled

    req = DocRequirement("work_proof", DocType.INSURANCE_4, "4대보험")
    words = employed_words()
    result = read_fake(tmp, "insurance", [scaled(words, (1000, 1400))])
    check("정상 4대보험", check_document(req, result, identity=IDENTITY).status, "PASS")
    for label, predicate in (("생년월일", lambda w: "990101" in w.text), ("성명", lambda w: w.text in {IDENTITY.name, "성명"})):
        masked = [w for w in words if not predicate(w)]
        ocr = read_fake(tmp, "insurance-hidden-" + label, [scaled(masked, (1000, 1400))])
        review("4대보험 " + label + " 가림", check_document(req, ocr, identity=IDENTITY), "REQUIRED_FIELD_UNREADABLE")


def test_api(tmp):
    from fastapi.testclient import TestClient
    from sqlmodel import select
    from engine_v2.pipeline import ocr as v2ocr
    from .. import models
    from ..main import app

    p4._isolate(tmp)
    with TestClient(app) as client:
        app_id = new_app(client)
        check("합성 본인 인증", identify(client, app_id, IDENTITY.name, IDENTITY.birth.isoformat()).status_code, 200)
        for marker, status in (("1/1", "PASS"), ("1/2", "FAIL"), ("미판독", "NEEDS_REVIEW")):
            path = make_image_pdf(tmp / "synthetic-api-pages.pdf", pages=1)
            with patch.dict(os.environ, {ENGINE_ENV: "p18-synthetic"}), \
                    patch.dict(v2ocr.ENGINES, {"p18-synthetic": lambda png, size: resident_words(marker)}), path.open("rb") as stream:
                response = client.post(f"/api/applications/{app_id}/documents", files={"file": (path.name, stream, "application/pdf")}, data={"slot_key": "resident_abstract", "declared_issue_date": "2026-11-10"})
            check("쪽 API HTTP " + marker, response.status_code, 200)
            check("쪽 API 판정 " + marker, response.json().get("status"), status)
            final = client.get(f"/api/applications/{app_id}/final-check").json()
            blockers = [b for b in final["blockers"] if b.get("kind") == "document" and b.get("target") == "resident_abstract"]
            check("서류 제출 차단 " + marker, bool(blockers), status == "FAIL")
        # 타인 이름·생일을 신청인 칸과 본문 모두에 넣어 실제 업로드한다.
        with patch.dict(os.environ, {ENGINE_ENV: "p18-synthetic"}), \
                patch.dict(v2ocr.ENGINES, {"p18-synthetic": lambda png, size: resident_words(name=OTHER_NAME, birth=OTHER_BIRTH)}), path.open("rb") as stream:
            response = client.post(f"/api/applications/{app_id}/documents", files={"file": ("synthetic-other.pdf", stream, "application/pdf")}, data={"slot_key": "resident_abstract", "declared_issue_date": "2026-11-10"})
        check("타인 초본 업로드", (response.status_code, response.json().get("status")), (200, "FAIL"))
        outputs = [("업로드", response)] + [(label, client.get(f"/api/applications/{app_id}/{suffix}")) for label, suffix in (
            ("목록", "documents"), ("체크리스트", "required-documents"), ("최종확인", "final-check"))]
        forbidden = (OTHER_NAME, OTHER_BIRTH, "engine", "fallback_reason", "quality_note", "classification_evidence", "쪽표기자료", "판독검증", "p18-synthetic", "pdftext", "easyocr", "own")
        for label, output in outputs:
            check(label + " HTTP", output.status_code, 200)
            check(label + " 타인값·담당자키 비노출", all(token not in output.text for token in forbidden), True)
        with models.get_session() as session:
            document = session.exec(select(models.Document).where(models.Document.application_id == app_id)).first()
            check("DB 추출 원값 보존", document.ocr_json["fields"].get("성명"), OTHER_NAME)
            application = session.get(models.Application, app_id)
            # FAIL 제출을 우회하는 제품 변경이 아닌 담당자 뷰의 합성 상태 준비.
            application.status = "submitted"
            session.add(application)
            session.commit()
            session.refresh(document)
        officer = client.get(f"/api/officer/applications/{app_id}")
        check("담당자 API HTTP", officer.status_code, 200)
        extracted = officer.json()["documents"][0]["extracted"]
        check("담당자 성명 보존", extracted.get("성명"), OTHER_NAME)
        check("담당자 생년월일 보존", extracted.get("생년월일"), OTHER_BIRTH)
        # 생년월일이 신청자 허용 목록에 포함되는 4대보험도 같은 경계로 숨긴다.
        from ..api.common import document_dict
        document.doc_type = str(DocType.INSURANCE_4)
        check("4대보험 불일치 성명·생일 비노출", {"성명", "생년월일"}.isdisjoint(document_dict(document)["extracted"]), True)
    models.engine.dispose()


def test_blur_rotation(tmp):
    from PIL import ImageFilter
    from engine_v2.tools.make_synth_eval import documents, render
    from ..ocr import read_document

    _, cells, _ = next(documents())
    cells += [(14, 23, "신청인: 김전북 (1999-01-01)")]
    base = render(cells)
    # 합성 이미지 자체를 변형하고 실제 판독 체인을 사용한다. 회전·흐림 측정기는 추가하지 않는다.
    for name, image in (("blur", base.filter(ImageFilter.GaussianBlur(5))), ("rotate90", base.rotate(90, expand=True))):
        path = tmp / f"synthetic-{name}.png"
        image.save(path, dpi=(300, 300))
        with patch.dict(os.environ, {ENGINE_ENV: "own"}):
            ocr = read_document(str(path), DocType.RESIDENT_ABSTRACT)
        result = check_document(abstract_slot(), ocr, identity=IDENTITY)
        check(name + " 실제 합성 이미지", result.status, "NEEDS_REVIEW")
        check(name + " 안내", bool(result.findings) and all(f.how_to_fix for f in result.findings), True)


def test_issue_date_labels():
    from ..ocr.pdftext import extract_issue_date, read_page_text

    for text in ("생년월일 1999-01-01", "거래일 2026-11-10", "1999-01-01 2026-11-10", "날짜 없음"):
        check("B6 라벨 없는 날짜", extract_issue_date(text), None)
    check("B6 발급일 라벨", extract_issue_date("생년월일 1999-01-01 발급일 2026-11-10"), date(2026, 11, 10))
    check("B6 유효하지 않은 라벨 날짜", extract_issue_date("발급일 2026-02-30 거래일 2026-11-10"), None)
    for padding in ("", "합성 설명 " * 100):
        ocr = read_page_text("사업자등록증명\n개업일 2020-01-01\n거래일 2026-11-10\n" + padding, None, 0)
        req = DocRequirement("work_proof", DocType.BIZ_REG_PROOF, "사업자등록증명", min_issue_date=date(2026, 3, 3))
        check("B6 발급일 속성 비움", ocr.issue_date, None)
        check("B6 발급일 필드 비움", "발급일" in ocr.fields, False)
        review("B6 발급일 미판독", check_document(req, ocr, declared_issue_date=date(2026, 11, 10)), "REQUIRED_FIELD_UNREADABLE")
    outside = DocRequirement("work_proof", DocType.FARM_BIZ_CERT, "농업경영체증명",
                             min_issue_date=date(2026, 3, 3), date_basis="none")
    check("B6 날짜 검사 제외 서류", check_document(outside, OcrResult(DocType.FARM_BIZ_CERT, 1.0)).status, "PASS")


def main():
    apply_runtime_overrides()
    # 외부 OCR 설정은 사용하지 않는다. 원래 환경은 patch가 복구한다.
    clean = {key: value for key, value in os.environ.items() if not key.startswith("JBAI_")}
    with patch.dict(os.environ, clean, clear=True), tempfile.TemporaryDirectory(prefix="p18-synthetic-") as directory:
        tmp = Path(directory)
        complete = test_pages(tmp)
        test_uncertainty(complete)
        test_insurance(tmp)
        test_api(tmp)
        test_blur_rotation(tmp)
        test_issue_date_labels()
    print(f"\n통과 {_passed} / 실패 {len(_failed)}")
    return int(bool(_failed))


if __name__ == "__main__":
    raise SystemExit(main())

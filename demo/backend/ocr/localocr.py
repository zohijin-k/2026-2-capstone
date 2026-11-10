"""Tier1.5 — 로컬 OCR 판독 (engine_v2).

Tier2(pdftext)는 텍스트 레이어가 있는 PDF만 읽는다. 그런데 실측(2026-11-10)해 보니
신청자가 정부24에서 받아 올리는 초본은 **브라우저 "PDF로 저장" 본이라 글자가 전부
이미지**다. Tier2는 이걸 못 읽고 신뢰도 0 → 전부 담당자 큐로 갔다.

이 계층은 그 공백을 메운다.
  - 서류 이미지를 **외부로 보내지 않고** 이 서버 안에서 OCR한다 (개인정보).
  - 초본/등본은 engine_v2 추출기로 구조를 읽는다: 성명·생년월일·발급일·주소이력,
    그리고 쪽 간 일치·순번 연속 같은 **서류 내부 검증**으로 신뢰도를 매긴다.
  - 건강보험료 납부·자격득실확인서는 텍스트 PDF와 이미지 PDF 모두 engine_v2 추출기를 쓴다.
  - 그 밖의 서류는 OCR 텍스트에 Tier2의 정규식 추출을 그대로 적용한다.

처리하지 않는 파일(→ None, 다음 계층으로):
  - 건강보험 서류 외 텍스트 레이어 PDF: Tier2가 더 빠르고 정확하다
  - 암호 PDF·없는 파일: Tier2가 공고문 문구로 '미비'를 낸다
  - OCR 엔진이 설치돼 있지 않은 서버: 조용히 건너뛴다 (데모가 멈추지 않는 원칙)

OCR 엔진 선택: 환경변수 ENGINE_V2_OCR = applevision | easyocr | paddle | off
  기본값은 macOS면 applevision(내장), 그 외 easyocr.
"""

from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

from ..rules.doc_types import DocType
from .base import BBox, OcrResult

NAME = "localocr"
ENGINE_ENV = "ENGINE_V2_OCR"

#: Tier2 신뢰도 공식은 '정확한 텍스트'를 전제로 한다. OCR 텍스트에는 그 근거가 없으므로,
#: 서류 내부 검증이 없는 서류는 엔진 임계값(0.85) 아래로 묶어 담당자 확인으로 보낸다.
GENERIC_CONFIDENCE_CAP = 0.8

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _engine_name() -> str:
    return os.environ.get(ENGINE_ENV) or ("applevision" if sys.platform == "darwin" else "easyocr")


def _import_v2():
    """engine_v2는 지연 import 한다 — OCR을 안 쓰는 경로에서 의존성을 요구하지 않도록."""
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    from engine_v2.extractors import resident_abstract
    from engine_v2.extractors import nhis_acquisition_loss, nhis_payment
    from engine_v2.engine import _load_pages
    from engine_v2.pipeline.ocr import run_ocr
    from engine_v2.pipeline.preprocess import PageSource, preprocess
    from engine_v2.schemas.models import DocType as V2DocType, DocumentInput

    return resident_abstract, nhis_payment, nhis_acquisition_loss, run_ocr, PageSource, preprocess, V2DocType, DocumentInput, _load_pages


def _quality(pages) -> float:
    """해상도로 화질을 근사한다 (엔진 IMAGE_QUALITY_THRESHOLD 0.6과 비교)."""
    dpis = [p.dpi for p in pages if p.dpi]
    if not dpis:
        return 0.75  # 사진 업로드: 물리 크기를 몰라 중간값
    low = min(dpis)
    return 0.9 if low >= 200 else 0.7 if low >= 150 else 0.5


def _demo_bbox(v2_bbox) -> BBox | None:
    if v2_bbox is None:
        return None
    return BBox(v2_bbox.page, v2_bbox.x0, v2_bbox.y0, v2_bbox.x1, v2_bbox.y1)


def _entry_bbox(entry, pages) -> BBox | None:
    """주소이력 한 건의 위치 (전입일 하이라이트용)."""
    if not entry.words:
        return None
    page = next(p for p, _ in pages if p.page == entry.page)
    ws = [w for w in entry.words if w.page == entry.page]
    x0, y0 = page.px_to_pt(min(w.px[0] for w in ws), min(w.px[1] for w in ws))
    x1, y1 = page.px_to_pt(max(w.px[2] for w in ws), max(w.px[3] for w in ws))
    return BBox(entry.page, round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1))


def _from_resident(ex, pages, ra, v2types) -> OcrResult:
    """engine_v2 초본 추출 결과 → 데모 OcrResult (필드 이름은 데모 규칙이 쓰는 그대로)."""
    detected = (DocType.RESIDENT_ABSTRACT if ex.detected_type == v2types.RESIDENT_ABSTRACT
                else DocType.RESIDENT_CERTIFICATE)
    f = ex.fields
    fields: dict[str, str] = {}
    bboxes: dict[str, BBox] = {}

    for v2key, label in (
        ("issue_date", "발급일"), ("name", "성명"), ("birth_date", "생년월일"),
        ("applicant_name", "초본신청인성명"),
        ("applicant_birth_date", "초본신청인생년월일"),
        ("address_history_count", "주소이력건수"),
    ):
        if v2key in f:
            v = f[v2key].value
            fields[label] = v.isoformat() if isinstance(v, date) else str(v)
            if (b := _demo_bbox(f[v2key].bbox)) is not None:
                bboxes[label] = b

    # 데모 배점의 '도 거주기간'은 "전북 최종 전입일 → 공고일 역산"이다.
    # engine_v2는 주소이력 전체에서 전북 연속 거주가 시작된 건을 찾는다
    # (전라북도 → 전북특별자치도 명칭 변경, 세대주 변경 등으로 끊기지 않음).
    start = ra.trailing_residence_start(ex.history, "전북")
    if start:
        fields["전입일"] = start.isoformat()
        entry = next((e for e in ex.history if e.effective == start), None)
        if entry and (b := _entry_bbox(entry, pages)):
            bboxes["전입일"] = b

    if ex.history:
        fields["현주소시도"] = ra.resolved_sido(ex.history, len(ex.history) - 1) or "판별불가"
        fields["주소이력건수"] = str(len(ex.history))
        if len(ex.history) == 1:
            fields["과거주소미포함의심"] = "true"
        # 이력이 2건 이상이면 '주소변동내역 포함'으로 본다. 1건 이하는 단정하지 않는다
        # (미포함으로 단정하면 doc_check가 부적합을 낸다 — 오독일 때 신청자가 억울해진다).
        if len(ex.history) >= 2:
            fields["주소변동내역"] = "포함"

    passed = sum(v.passed for v in ex.validations)
    fields["판독검증"] = f"{passed}/{len(ex.validations)} 통과"
    failed = [v.name for v in ex.validations if not v.passed]
    if failed:
        fields["판독검증실패"] = ", ".join(failed)

    # 신뢰도 = 핵심 필드 신뢰도의 최솟값. 필드 신뢰도는 OCR 점수가 아니라 검증 통과율이다.
    key = [f[k].confidence for k in ("issue_date", "name", "birth_date") if k in f]
    confidence = min([ex.type_confidence, *key]) if "issue_date" in f else 0.5

    return OcrResult(
        detected_doc_type=detected,
        confidence=round(confidence, 2),
        image_quality=_quality([p for p, _ in pages]),
        issue_date=f["issue_date"].value if "issue_date" in f else None,
        fields=fields,
        bboxes=bboxes,
        page_count=len(pages),
        tier=NAME,
    )


def _from_nhis(ex, pages, v2types, classification_evidence: str = "",
               detected_override: DocType | None = None) -> OcrResult:
    """engine_v2 건강보험 판독 결과를 신청자·담당자 화면 계약으로 옮긴다."""
    fields: dict[str, str] = {}
    bboxes: dict[str, BBox] = {}
    for key, value in ex.fields.items():
        rendered = value.value.isoformat() if isinstance(value.value, date) else str(value.value)
        fields[key] = rendered
        if (box := _demo_bbox(value.bbox)) is not None:
            bboxes[key] = box
    validations = ex.validations
    fields["판독검증"] = f"{sum(v.passed for v in validations)}/{len(validations)} 통과"
    failed = [v.name for v in validations if not v.passed]
    if failed:
        fields["판독검증실패"] = ", ".join(failed)
    if ex.warnings:
        fields["판독경고"] = " ".join(ex.warnings)
    confidence = min((field.confidence for field in ex.fields.values()), default=0.5)
    detected_map = {
        v2types.NHIS_PAYMENT: DocType.NHIS_PAYMENT,
        v2types.NHIS_ACQUISITION_LOSS: DocType.NHIS_ACQUISITION_LOSS,
    }
    detected = detected_override or detected_map.get(ex.detected_type)
    issue = ex.fields.get("발급일")
    issue_date = None
    if issue:
        try:
            issue_date = date.fromisoformat(str(issue.value)[:10])
        except ValueError:
            pass
    return OcrResult(
        detected_doc_type=detected,
        confidence=round(min(confidence, ex.type_confidence), 2),
        image_quality=_quality([page for page, _ in pages]),
        issue_date=issue_date,
        fields=fields,
        bboxes=bboxes,
        page_count=len(pages),
        tier=NAME,
        classification_evidence=classification_evidence,
        classification_confidence=0.95 if detected else 0.0,
    )


def _generic(pages, path: Path) -> OcrResult | None:
    """초본·등본이 아닌 서류: OCR 텍스트에 Tier2 정규식을 적용한다.

    서류 종류를 알아보지 못했으면 None — 이 계층이 확신 없는 결과로 Tier2의 화면 캡처·화질
    판정을 덮어쓰지 않게 한다.
    """
    from . import pdftext

    text = "\n".join(r.text for _, r in pages)
    if pdftext.classify(text) is None:
        return None
    result = pdftext.read_page_text(text, None, 0)
    result.confidence = min(result.confidence, GENERIC_CONFIDENCE_CAP)
    result.image_quality = _quality([p for p, _ in pages])
    result.page_count = len(pages)
    result.tier = NAME
    if path.suffix.lower() != ".pdf":
        _merge_image_heuristics(result, path)
    return result


def _merge_image_heuristics(result: OcrResult, path: Path) -> None:
    """사진 업로드는 Tier2의 화면 캡처·화질 휴리스틱을 그대로 가져온다."""
    from . import pdftext

    img = pdftext._read_image(path)
    if img is not None and not img.is_encrypted:
        result.is_screen_capture = img.is_screen_capture
        result.image_quality = min(result.image_quality, img.image_quality)


def _tier2_can_read(path: Path) -> bool:
    """Tier2와 **같은 기준**으로 경계를 긋는다: 암호이거나 첫 쪽에 글자가 하나라도 있으면 Tier2 몫."""
    import fitz

    try:
        with fitz.open(path) as doc:
            if doc.needs_pass or doc.page_count == 0:
                return True
            return bool("".join(doc[0].get_text().split()))
    except Exception:  # noqa: BLE001 - 못 여는 파일은 Tier2가 '열 수 없음'으로 처리
        return True


class LocalOcr:
    name = NAME

    def read(self, file_path: str, expected: DocType | None) -> OcrResult | None:
        del expected  # 종류는 슬롯 기대값이 아니라 본문 OCR 결과로 먼저 고른다.
        engine = _engine_name()
        path = Path(file_path)
        if not path.exists() or path.suffix.lower() not in {".pdf", ".jpg", ".jpeg", ".png"}:
            return None

        text_pdf = path.suffix.lower() == ".pdf" and _tier2_can_read(path)

        from . import pdftext

        if text_pdf:
            # 텍스트 레이어는 바로 읽어 분류한 다음, 지원되는 NHIS 유형이면 그 추출기를 고른다.
            classified = pdftext._read_pdf(path)
            if classified is None:
                return None
            detected = classified.detected_doc_type
            if detected not in (DocType.NHIS_PAYMENT, DocType.NHIS_ACQUISITION_LOSS):
                return None  # 그 밖의 텍스트 PDF는 Tier2가 이미 분류·판독한다.
        elif engine == "off":
            return None

        try:
            ra, payment_extractor, acquisition_extractor, run_ocr, PageSource, preprocess, v2types, V2DocumentInput, load_pages = _import_v2()
        except ImportError:
            return None

        if text_pdf:
            v2type = v2types.NHIS_PAYMENT if detected == DocType.NHIS_PAYMENT else v2types.NHIS_ACQUISITION_LOSS
            input_doc = V2DocumentInput(doc_id="demo", declared_type=v2type, file_path=str(path))
            pages = load_pages(input_doc, engine)
            if isinstance(pages, str):
                return None  # OCR 엔진이 없어도 다음 계층이 판독을 이어받는다.
            extractor = payment_extractor if detected == DocType.NHIS_PAYMENT else acquisition_extractor
            return _from_nhis(
                extractor.extract(pages), pages, v2types,
                classified.classification_evidence, detected,
            )

        try:
            page_images = preprocess(path)
        except ValueError:
            return None
        if any(p.source == PageSource.TEXT_LAYER for p in page_images):
            return None

        pages = []
        for p in page_images:
            r = run_ocr(engine, p.png, p.pixel_size)
            if r.error:
                return None  # 엔진 미설치 등 → 다음 계층
            pages.append((p, r))

        text = "\n".join(result.text for _, result in pages)
        detected, evidence = pdftext.classify_with_evidence(text)
        if detected is None:
            return None

        if detected in (DocType.NHIS_PAYMENT, DocType.NHIS_ACQUISITION_LOSS):
            extractor = payment_extractor if detected == DocType.NHIS_PAYMENT else acquisition_extractor
            result = _from_nhis(extractor.extract(pages), pages, v2types, evidence, detected)
            if path.suffix.lower() != ".pdf":
                _merge_image_heuristics(result, path)
            return result

        if detected in (DocType.RESIDENT_ABSTRACT, DocType.RESIDENT_CERTIFICATE):
            ex = ra.extract(pages)
            result = _from_resident(ex, pages, ra, v2types)
            result.detected_doc_type = detected
            result.classification_evidence = evidence
            result.classification_confidence = 0.95
            if path.suffix.lower() != ".pdf":
                _merge_image_heuristics(result, path)
            return result

        result = _generic(pages, path)
        if result is not None:
            result.detected_doc_type = detected
            result.classification_evidence = evidence
            result.classification_confidence = 0.95
        return result

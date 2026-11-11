"""Tier1.2 — 전북AI OCR 판독 (도청 제공 PaddleOCR-VL).

기관 확인(2026-11-11)에 따라 신청 서류 판독의 기본 엔진으로 쓴다. 전북AI가 실패하면
LocalOcr(Tier1.5)가 같은 파일을 이어받고, 대체 사유는 담당자 화면에만 남는다.

맡는 파일 — LocalOcr와 같은 경계:
  - 텍스트 레이어가 없는 파일: 정부24 브라우저 인쇄 PDF·스캔 PDF·사진.
    텍스트 PDF는 지금처럼 LocalOcr(건강보험 서류)·PdfText가 읽는다.
  - 판독기(engine_v2/extractors/jbai_text.py)가 있는 서류 칸: 주민등록초본·등본,
    건강보험료 납부확인서, 자격득실확인서. 그 밖의 칸은 전북AI를 부르지 않는다.

켜는 조건: JBAI_API_KEY가 있고 JBAI_ALLOW_REAL_DOCS가 참일 때만. 하나라도 없으면 None을
돌려 지금처럼 LocalOcr부터 동작한다.

대체(→ OcrFallback): 인증 실패(401), 재시도 후에도 429, 시간 초과, 연결 실패, 응답 형식 오류,
판독기 실패. 시연 중 네트워크가 끊겨도 업로드가 멈추지 않도록 요청마다 시간 제한
(JBAI_TIMEOUT_SEC, 기본 60초)을 두고, 429 재시도 대기도 짧게 자른다.

개인정보:
  - 응답 원문의 주민등록번호는 engine_v2 클라이언트가 받은 즉시 뒷자리를 지운다(`mask_rrn`).
  - 이 계층은 가린 텍스트 줄·표만 쓴다. 원문 필드(raw_content·table_content)는 비우고 다룬다.
  - 같은 파일(내용 SHA-256)은 메모리 캐시의 가린 판독 결과를 다시 쓴다. 디스크에는 남기지 않는다.
  - 로그에는 엔진 이름·상태 코드·쪽 수·소요 시간만 남긴다. 키·요청/응답 본문·이미지는 남기지 않는다.
"""

from __future__ import annotations

import hashlib
import logging
import os
import sys
import threading
import time
from collections import OrderedDict
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from ..rules.doc_types import DocType
from .base import OcrFallback, OcrResult
from .localocr import _from_nhis, _from_resident, _merge_image_heuristics, _quality, _tier2_can_read

NAME = "jbai"
KEY_ENV = "JBAI_API_KEY"
ALLOW_ENV = "JBAI_ALLOW_REAL_DOCS"
TIMEOUT_ENV = "JBAI_TIMEOUT_SEC"
DEFAULT_TIMEOUT_SEC = 60.0
#: Retry-After가 길어도 업로드 응답이 오래 멈추지 않게 재시도 대기를 자른다.
MAX_RETRY_WAIT_SEC = 10.0
CACHE_SIZE = 64

# JBAI results are accepted only when their document-specific core checks pass.
# Keep thresholds and required validations in this one table for review.
QUALITY_RULES = {
    DocType.RESIDENT_ABSTRACT: {
        "required_fields": ("issue_date", "name", "birth_date"),
        "required_validations": ("pages_complete", "name_consistent"),
        "minimum_history": 1,
    },
    DocType.RESIDENT_CERTIFICATE: {
        "required_fields": ("issue_date", "name", "birth_date"),
        "required_validations": ("pages_complete", "name_consistent"),
        "minimum_history": 1,
    },
    DocType.NHIS_PAYMENT: {
        "required_fields": ("성명", "생년월일", "발급일", "고지월", "건강보험료"),
        "required_validations": ("document_type", "성명_consistent", "생년월일_consistent",
                                 "발급일_consistent", "page_names_match", "insurance_type_found",
                                 "monthly_rows_found", "monthly_amounts_numeric", "months_continuous",
                                 "monthly_total_matches"),
    },
    DocType.NHIS_ACQUISITION_LOSS: {
        "required_fields": ("성명", "생년월일", "발급일", "자격이력자료", "가입구분"),
        "required_validations": ("document_type", "성명_consistent", "생년월일_consistent",
                                 "발급일_consistent", "page_names_match", "history_dates_read",
                                 "acquisition_before_loss"),
    },
}


def _quality_failure(detected: DocType, extracted) -> str | None:
    """Reject missing required fields or failed document checks, not OCR noise alone."""
    rules = QUALITY_RULES[detected]
    fields = extracted.fields
    validations = {item.name: item.passed for item in extracted.validations}
    if detected in (DocType.RESIDENT_ABSTRACT, DocType.RESIDENT_CERTIFICATE):
        if len(extracted.history) < rules["minimum_history"]:
            return "주소 이력 없음"
        if "issue_date" not in fields:
            return "발급일 없음"
        if "name" not in fields:
            return "성명 없음"
        if not validations.get("pages_complete", False):
            return "쪽 번호 검증 실패"
        if not validations.get("name_consistent", False):
            return "쪽마다 성명 일치 검증 실패"
    for key in rules["required_fields"]:
        if key not in fields or fields[key].value in (None, ""):
            return f"핵심 항목 없음: {key}"
    for key in rules["required_validations"]:
        if not validations.get(key, False):
            labels = {
                "pages_complete": "쪽 번호 검증 실패",
                "name_consistent": "쪽마다 성명 일치 검증 실패",
                "page_names_match": "쪽마다 성명 일치 검증 실패",
                "monthly_rows_found": "월별 표 없음",
                "monthly_amounts_numeric": "월별 금액 판독 실패",
                "monthly_total_matches": "월별 합계 검증 실패",
                "document_type": "서류 종류 검증 실패",
                "성명_consistent": "성명 검증 실패",
                "생년월일_consistent": "생년월일 검증 실패",
                "발급일_consistent": "발급일 검증 실패",
                "insurance_type_found": "가입구분 판독 실패",
                "months_continuous": "월별 기간 연속성 검증 실패",
                "history_dates_read": "자격 이력 날짜 판독 실패",
                "acquisition_before_loss": "자격 날짜 순서 검증 실패",
            }
            return labels.get(key, f"검증 실패: {key}")
    return None


def _noisy_pages(document) -> list[int]:
    from engine_v2.pipeline.jbai_quality import HALLUCINATION_THRESHOLDS

    return [page.page + 1 for page in document.pages
            if page.hallucination_score >= HALLUCINATION_THRESHOLDS["fail_score"]]


def _noise_suffix(noisy_pages: list[int]) -> str:
    return f" · 환각 의심 {'·'.join(map(str, noisy_pages))}쪽" if noisy_pages else ""

#: 전북AI 판독기가 있는 서류. 이 칸에 올라온 파일만 전북AI로 보낸다.
SUPPORTED: tuple[DocType, ...] = (
    DocType.RESIDENT_ABSTRACT,
    DocType.RESIDENT_CERTIFICATE,
    DocType.NHIS_PAYMENT,
    DocType.NHIS_ACQUISITION_LOSS,
)
_SUFFIXES = {".pdf", ".jpg", ".jpeg", ".png"}
_REPO_ROOT = Path(__file__).resolve().parents[3]

log = logging.getLogger("demo.ocr.jbai")

_cache: OrderedDict[str, object] = OrderedDict()
_cache_lock = threading.Lock()


def enabled() -> bool:
    """JBAI_API_KEY가 있고 JBAI_ALLOW_REAL_DOCS가 참일 때만 켠다."""
    has_key = bool(os.environ.get(KEY_ENV, "").strip())
    allowed = os.environ.get(ALLOW_ENV, "").strip().lower() in {"1", "true", "yes", "on"}
    return has_key and allowed


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


def _timeout() -> float:
    try:
        value = float(os.environ.get(TIMEOUT_ENV) or DEFAULT_TIMEOUT_SEC)
    except ValueError:
        return DEFAULT_TIMEOUT_SEC
    return value if value > 0 else DEFAULT_TIMEOUT_SEC


def _sleep(seconds: float) -> None:
    time.sleep(min(max(seconds, 0.0), MAX_RETRY_WAIT_SEC))


def _import_v2() -> SimpleNamespace:
    """engine_v2는 지연 import 한다 — 전북AI를 끈 서버에서 의존성을 요구하지 않도록."""
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    from engine_v2.extractors import jbai_text, resident_abstract
    from engine_v2.pipeline import jbai_ocr
    from engine_v2.pipeline.preprocess import PageSource, preprocess
    from engine_v2.schemas.models import DocType as V2DocType

    return SimpleNamespace(jbai_text=jbai_text, resident_abstract=resident_abstract,
                           jbai_ocr=jbai_ocr, PageSource=PageSource, preprocess=preprocess,
                           V2DocType=V2DocType)


def _failure(error: Exception, jbai_ocr) -> tuple[str, str]:
    """(로그용 상태, 담당자 화면용 대체 사유). 오류 메시지 원문은 쓰지 않는다."""
    status = getattr(error, "status", None)
    if isinstance(error, jbai_ocr.JBAIAuthenticationError):
        return "401", "전북AI 인증 실패(401)"
    if isinstance(error, jbai_ocr.JBAIRateLimitError):
        return "429", "전북AI 요청 제한(429, 재시도 후에도)"
    if isinstance(error, jbai_ocr.JBAITimeoutError):
        return "timeout", "전북AI 응답 시간 초과"
    if isinstance(error, jbai_ocr.JBAIResponseError):
        return str(status or "response"), "전북AI 응답 형식 오류"
    if isinstance(error, jbai_ocr.JBAIImageTooLarge):
        return "too_large", "전북AI 전송 이미지가 32MB를 넘음"
    if isinstance(error, (jbai_ocr.JBAIConfigurationError, jbai_ocr.JBAIRealDocumentBlocked)):
        return "config", "전북AI 설정 오류"
    if status:
        return str(status), f"전북AI 요청 실패(HTTP {status})"
    return "network", "전북AI 연결 실패"


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _document_text(document) -> str:
    lines = [line for page in document.pages for line in page.text_lines]
    lines += [cell.text for page in document.pages for table in page.tables
              for row in table.rows for cell in row if cell.text]
    return "\n".join(lines)


class JbaiOcr:
    name = NAME

    def read(self, file_path: str, expected: DocType | None) -> OcrResult | None:
        if not enabled() or expected not in SUPPORTED:
            return None
        path = Path(file_path)
        suffix = path.suffix.lower()
        if not path.exists() or suffix not in _SUFFIXES:
            return None
        if suffix == ".pdf" and _tier2_can_read(path):
            return None  # 텍스트 PDF(·암호 PDF)는 지금처럼 다음 계층이 읽는다.

        try:
            v2 = _import_v2()
        except ImportError:
            return None
        try:
            page_images = v2.preprocess(path)
        except ValueError:
            return None
        if any(page.source == v2.PageSource.TEXT_LAYER for page in page_images):
            return None  # LocalOcr와 같은 경계: 한 쪽이라도 텍스트 레이어면 맡지 않는다.

        document = self._recognize(path, v2)
        started = time.perf_counter()
        try:
            return self._convert(document, path, page_images, v2)
        except OcrFallback:
            raise
        except Exception:  # noqa: BLE001 - 판독기 오류도 로컬 OCR로 넘긴다
            log.warning("engine=%s status=reader pages=%d elapsed_ms=%d",
                        NAME, len(document.pages), _elapsed_ms(started))
            raise OcrFallback("전북AI 판독기 오류") from None

    def _recognize(self, path: Path, v2):
        """전북AI 판독 결과(주민번호 뒷자리를 지운 것)를 캐시에서 꺼내거나 새로 받는다."""
        key = hashlib.sha256(path.read_bytes()).hexdigest()
        with _cache_lock:
            cached = _cache.get(key)
            if cached is not None:
                _cache.move_to_end(key)
        if cached is not None:
            log.info("engine=%s status=cache pages=%d elapsed_ms=0", NAME, len(cached.pages))
            return cached

        started = time.perf_counter()
        try:
            document = v2.jbai_ocr.run_jbai_file_pair(
                path, is_demo_upload=True, sleep=_sleep, timeout=_timeout(),
            )
        except v2.jbai_ocr.JBAIOCRError as error:
            status, reason = _failure(error, v2.jbai_ocr)
            log.warning("engine=%s status=%s pages=0 elapsed_ms=%d", NAME, status, _elapsed_ms(started))
            raise OcrFallback(reason) from None
        except Exception:  # noqa: BLE001 - 렌더링·이미지 변환 실패
            log.warning("engine=%s status=error pages=0 elapsed_ms=%d", NAME, _elapsed_ms(started))
            raise OcrFallback("전북AI 전송 이미지 준비 실패") from None

        # 원문 필드는 이 계층에서 쓰지 않는다. 가린 텍스트 줄·표만 남겨 캐시·판독에 쓴다.
        document = replace(document, pages=[
            replace(page, raw_content="", table_content="") for page in document.pages
        ])
        log.info("engine=%s status=200 pages=%d elapsed_ms=%d",
                 NAME, len(document.pages), _elapsed_ms(started))
        with _cache_lock:
            _cache[key] = document
            while len(_cache) > CACHE_SIZE:
                _cache.popitem(last=False)
        return document

    def _convert(self, document, path: Path, page_images, v2) -> OcrResult:
        """전북AI 판독 결과 → 데모 OcrResult. LocalOcr와 같은 변환(_from_resident·_from_nhis)을 쓴다."""
        from . import pdftext

        noisy_pages = _noisy_pages(document)
        detected, evidence = pdftext.classify_with_evidence(_document_text(document))
        if detected is None:
            raise OcrFallback("전북AI 판독 결과로 서류 종류를 알아보지 못함" + _noise_suffix(noisy_pages))
        if detected not in SUPPORTED:
            raise OcrFallback("전북AI 판독기가 없는 서류로 판별됨" + _noise_suffix(noisy_pages))

        v2types = v2.V2DocType
        v2type = {
            DocType.RESIDENT_ABSTRACT: v2types.RESIDENT_ABSTRACT,
            DocType.RESIDENT_CERTIFICATE: v2types.RESIDENT_REGISTER,
            DocType.NHIS_PAYMENT: v2types.NHIS_PAYMENT,
            DocType.NHIS_ACQUISITION_LOSS: v2types.NHIS_ACQUISITION_LOSS,
        }[detected]
        extracted = v2.jbai_text.extract(document, v2type)
        quality_reason = _quality_failure(detected, extracted)
        # 판독기가 열 순서 처리에만 쓰는 임시 격자. 화면 좌표로는 쓰지 않는다.
        pages = v2.jbai_text.virtual_pages(document, v2type)

        if detected in (DocType.NHIS_PAYMENT, DocType.NHIS_ACQUISITION_LOSS):
            result = _from_nhis(extracted, pages, v2types, evidence, detected)
        else:
            result = _from_resident(extracted, pages, v2.resident_abstract, v2types)
            result.detected_doc_type = detected
            result.classification_evidence = evidence
            result.classification_confidence = 0.95

        # 전북AI는 좌표(bbox)를 주지 않는다 — 임시 격자 좌표로 하이라이트를 만들지 않는다.
        result.bboxes = {}
        # 화질·쪽 수는 LocalOcr와 같은 기준(원본 파일의 해상도)으로 매긴다.
        result.image_quality = _quality(page_images)
        result.page_count = len(document.pages)
        if path.suffix.lower() != ".pdf":
            _merge_image_heuristics(result, path)
        result.tier = NAME
        result.engine = NAME
        if noisy_pages:
            result.quality_note = "잡음 있음"
        if quality_reason:
            raise OcrFallback(f"전북AI 판독 검증 실패: {quality_reason}" + _noise_suffix(noisy_pages),
                              fallback_result=result)
        return result

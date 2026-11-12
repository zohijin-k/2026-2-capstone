"""OCR 폴백 체인.

Tier1(fixture) → Tier1.2(전북AI OCR) → Tier1.5(로컬 OCR, engine_v2) → Tier2(PDF 텍스트)
→ Tier3(상용 API) 순으로 시도하고, 전부 미스면
신뢰도 0짜리 결과를 돌려준다. 신뢰도 0은 엔진에서 NEEDS_REVIEW가 되어 담당자 큐로
가므로, 어떤 파일이 올라와도 화면이 멈추지 않는다.

설계 근거: .trellis/tasks/09-16-demo-site/design.md 4절
"""

import time

from ..rules.doc_types import DocType
from .base import BBox, OcrAdapter, OcrFallback, OcrResult
from .fixture import FixtureOcr, fixture_keys
from .jbai import JbaiOcr
from .localocr import LocalOcr, ensure_nhis_required_fields
from .pdftext import PdfTextOcr, split_pdf_pages
from .upstage import UpstageOcr

#: 시도 순서. 앞 계층이 None을 돌려주면 다음으로 넘어간다.
#: 전북AI(JbaiOcr)는 JBAI_API_KEY·JBAI_ALLOW_REAL_DOCS가 모두 있을 때만, 판독기가 있는 서류
#: (초본·등본·납부확인서·자격득실)의 텍스트 레이어 없는 파일을 맡는다. 실패하면 OcrFallback으로
#: 사유를 남기고 LocalOcr가 이어받는다.
#: LocalOcr는 텍스트 레이어가 **없는** 파일(브라우저 인쇄 PDF·사진)만 맡고, 텍스트 PDF는
#: None을 돌려 Tier2에 넘긴다. OCR 엔진이 없는 서버에서도 None → 기존 동작 그대로.
CHAIN: list[OcrAdapter] = [FixtureOcr(), JbaiOcr(), LocalOcr(), PdfTextOcr(), UpstageOcr()]


def read_document(file_path: str, expected: DocType | None = None) -> OcrResult:
    """서류 한 건을 판독한다. 예외를 밖으로 내보내지 않는다."""
    started = time.perf_counter()
    result: OcrResult | None = None
    fallback_reasons: list[str] = []
    fallback_result: OcrResult | None = None

    for adapter in CHAIN:
        try:
            result = adapter.read(file_path, expected)
        except OcrFallback as fallback:
            fallback_reasons.append(fallback.reason)  # 담당자 화면에 대체 사유로 남긴다
            if fallback.fallback_result is not None:
                fallback_result = fallback.fallback_result
            result = None
        except NotImplementedError:
            result = None  # 미구성 계층은 조용히 건너뛴다
        except Exception:  # noqa: BLE001 - 한 계층이 터져도 다음으로 넘어가야 한다
            result = None
        if result is not None:
            break

    if result is None:
        result = fallback_result or OcrResult(
            detected_doc_type=None,
            confidence=0.0,
            image_quality=0.5,
            fields={"판독실패": "자동 판독이 되지 않아 담당자가 직접 확인합니다."},
            tier="none",
        )
        if fallback_result is not None:
            result.confidence = min(result.confidence, 0.4)

    # 어느 엔진으로 읽었는지와 대체 사유는 담당자 화면 전용이다 (신청자 응답에는 싣지 않는다).
    if not result.engine:
        result.engine = result.tier
    if fallback_reasons and not result.fallback_reason:
        result.fallback_reason = " / ".join(fallback_reasons)

    # 모든 OCR 계층이 공통으로 지난 뒤 추출값이 머리표만으로 구성됐는지 확인한다.
    from pathlib import Path
    import sys

    repo_root = str(Path(__file__).resolve().parents[3])
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    from engine_v2.pipeline.field_safety import remove_header_only_fields

    for key in remove_header_only_fields(result.fields):
        result.bboxes.pop(key, None)

    ensure_nhis_required_fields(result)

    result.elapsed_ms = int((time.perf_counter() - started) * 1000)
    return result


__all__ = [
    "BBox",
    "CHAIN",
    "OcrAdapter",
    "OcrResult",
    "fixture_keys",
    "read_document",
    "split_pdf_pages",
]

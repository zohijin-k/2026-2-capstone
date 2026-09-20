"""OCR 3계층 폴백 체인.

Tier1(fixture) → Tier2(PDF 텍스트) → Tier3(상용 API) 순으로 시도하고, 전부 미스면
신뢰도 0짜리 결과를 돌려준다. 신뢰도 0은 엔진에서 NEEDS_REVIEW가 되어 담당자 큐로
가므로, 어떤 파일이 올라와도 화면이 멈추지 않는다.

설계 근거: .trellis/tasks/09-16-demo-site/design.md 4절
"""

import time

from ..rules.doc_types import DocType
from .base import BBox, OcrAdapter, OcrResult
from .fixture import FixtureOcr, fixture_keys
from .pdftext import PdfTextOcr, split_pdf_pages
from .upstage import UpstageOcr

#: 시도 순서. 앞 계층이 None을 돌려주면 다음으로 넘어간다.
CHAIN: list[OcrAdapter] = [FixtureOcr(), PdfTextOcr(), UpstageOcr()]


def read_document(file_path: str, expected: DocType | None = None) -> OcrResult:
    """서류 한 건을 판독한다. 예외를 밖으로 내보내지 않는다."""
    started = time.perf_counter()
    result: OcrResult | None = None

    for adapter in CHAIN:
        try:
            result = adapter.read(file_path, expected)
        except NotImplementedError:
            result = None  # 미구성 계층은 조용히 건너뛴다
        except Exception:  # noqa: BLE001 - 한 계층이 터져도 다음으로 넘어가야 한다
            result = None
        if result is not None:
            break

    if result is None:
        result = OcrResult(
            detected_doc_type=None,
            confidence=0.0,
            image_quality=0.5,
            fields={"판독실패": "자동 판독이 되지 않아 담당자가 직접 확인합니다."},
            tier="none",
        )

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

"""Tier3 — 상용 Document AI 스텁.

스캔 이미지(jpg/png)는 텍스트 레이어가 없어 Tier2가 읽지 못한다. 실서비스라면
Upstage Document AI나 네이버 클로바 OCR을 여기에 붙인다. 데모에서는 **인터페이스만**
정의한다 (부모 prd.md C3: 상용 OCR API는 비목표).

키가 없으면 `read`가 조용히 None을 돌려주고, 폴백 체인이 신뢰도 0으로 마감한다.
그 결과 엔진이 NEEDS_REVIEW를 내고 담당자 큐로 간다 — 데모가 멈추지 않는다.
"""

import os

from ..rules.doc_types import DocType
from .base import OcrResult

NAME = "upstage"

#: 환경변수로 주입한다. 저장소에는 키를 두지 않는다.
API_KEY_ENV = "UPSTAGE_API_KEY"
ENDPOINT = "https://api.upstage.ai/v1/document-ai/document-parse"


class UpstageOcr:
    """미구성 상태에서는 항상 None. TF 이후 `_call_api`만 채우면 된다."""

    name = NAME

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.getenv(API_KEY_ENV, "")

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def read(self, file_path: str, expected: DocType | None) -> OcrResult | None:
        if not self.configured:
            return None
        return self._call_api(file_path, expected)

    def _call_api(self, file_path: str, expected: DocType | None) -> OcrResult | None:
        """실제 호출 지점.

        구현 시 할 일:
          1. multipart로 `file_path` 업로드
          2. 응답의 문자 단위 confidence 평균 → `OcrResult.confidence`
          3. 응답 레이아웃의 bbox → `OcrResult.bboxes` (좌표계를 PDF 포인트로 정규화)
          4. 추출 텍스트를 `pdftext.read_page_text`에 그대로 흘려 필드 파싱 재사용
        """
        del file_path, expected
        raise NotImplementedError(
            "상용 OCR 연동은 데모 범위 밖입니다. TF 확정 후 구현합니다."
        )

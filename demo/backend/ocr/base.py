"""OCR 어댑터 인터페이스.

OCR은 이 프로젝트에서 아무도 구현하지 않은 공백이다. 시연 안정성과 설득력을 같이
잡기 위해 3계층으로 나누고 런타임에 폴백한다.

  Tier1 `fixture.py`  — 시연용 고정 응답. 반드시 동작한다.
  Tier2 `pdftext.py`  — PyMuPDF로 실제 PDF 텍스트+좌표를 읽는다. "진짜 읽는다"의 증거.
  Tier3 `upstage.py`  — 상용 API. 스캔 이미지용. 데모에서는 스텁.

폴백 규칙: Tier1 히트 → 반환. 미스면 Tier2. Tier2도 못 읽으면(스캔 이미지 등)
Tier3, 그것도 미구성이면 `confidence = 0.0` → 엔진이 NEEDS_REVIEW로 떨어뜨려
담당자 큐로 간다. **데모가 멈추지 않는 것**이 이 구조의 목적이다.

설계 근거: .trellis/tasks/09-16-demo-site/design.md 4절
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Protocol, runtime_checkable

from ..rules.doc_types import DocType


@dataclass(frozen=True)
class BBox:
    """원본 파일에서 값을 읽어낸 위치. 담당자 화면 하이라이트용(R2.4/R4.3).

    좌표계는 PDF 포인트(좌상단 원점). 이미지는 픽셀.
    """

    page: int
    x0: float
    y0: float
    x1: float
    y1: float

    def as_dict(self) -> dict[str, float | int]:
        return {"page": self.page, "x0": self.x0, "y0": self.y0, "x1": self.x1, "y1": self.y1}


@dataclass
class OcrResult:
    """서류 한 건(또는 한 페이지)의 판독 결과."""

    #: 판독된 문서 종류. 분류 실패 시 None.
    detected_doc_type: DocType | None = None
    #: 0.0 ~ 1.0. 엔진의 OCR_CONFIDENCE_THRESHOLD(0.85)와 비교된다.
    confidence: float = 0.0
    #: 0.0 ~ 1.0. 엔진의 IMAGE_QUALITY_THRESHOLD(0.6)와 비교된다.
    image_quality: float = 1.0
    #: 서류 본문에서 읽은 발급일.
    issue_date: date | None = None
    #: 서명란 감지 결과. 서명이 필요 없는 서류는 None.
    has_signature: bool | None = None
    #: {"성명": "홍길동", "가구원수": "4", ...}
    fields: dict[str, str] = field(default_factory=dict)
    #: 필드명 → 원본 좌표
    bboxes: dict[str, BBox] = field(default_factory=dict)
    #: 암호가 걸렸거나 열 수 없는 파일.
    is_encrypted: bool = False
    #: 모니터 화면을 캡처한 것으로 의심됨 (공고문: 화면 캡처 불인정).
    is_screen_capture: bool = False
    page_count: int = 1
    #: 어느 계층이 읽었는지. 담당자 화면과 로그에 그대로 노출한다.
    tier: str = "none"
    #: 판독 소요 시간(ms). R2.1의 5초 기준을 화면에서 보여주기 위해 남긴다.
    elapsed_ms: int = 0

    def bboxes_as_dict(self) -> dict[str, dict[str, float | int]]:
        return {k: v.as_dict() for k, v in self.bboxes.items()}


@runtime_checkable
class OcrAdapter(Protocol):
    """판독기 한 계층.

    `read`는 처리하지 못한 파일에 대해 `None`을 돌려준다. 예외를 던지지 않는다 —
    한 계층이 실패해도 다음 계층으로 넘어가야 하기 때문이다.
    """

    name: str

    def read(self, file_path: str, expected: DocType | None) -> OcrResult | None: ...


def unreadable(reason: str, *, tier: str) -> OcrResult:
    """파일을 열지 못했을 때의 결과. 엔진이 UNREADABLE_FILE로 잡는다."""
    return OcrResult(
        detected_doc_type=None,
        confidence=0.0,
        image_quality=0.0,
        is_encrypted=True,
        fields={"판독실패": reason},
        tier=tier,
    )

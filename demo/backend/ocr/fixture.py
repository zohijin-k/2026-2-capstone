"""Tier1 — 시연용 고정 판독 결과.

파일명(확장자 제외)이 아래 표의 키와 같으면 정해진 결과를 돌려준다. 시연 중
OCR이 흔들려서 화면이 무너지는 사고를 막는 안전장치이자, 시나리오 S1~S10을
클릭만으로 재현하는 수단이다.

샘플 파일은 저장소에 커밋하지 않는다. `demo/fixtures/make_samples.py`를 돌리면
여기 정의된 키와 같은 이름의 더미 PDF가 `demo/fixtures/samples/`에 생성된다.
실제 개인정보나 실물 서류는 일절 쓰지 않는다.
"""

from datetime import date
from pathlib import Path

from ..rules.doc_types import DocType
from .base import BBox, OcrResult

NAME = "fixture"

#: 초본 본문에서 성명이 찍히는 대략적인 위치. 담당자 화면 하이라이트 시연용.
_ABSTRACT_BOXES = {
    "성명": BBox(0, 120.0, 168.0, 232.0, 184.0),
    "발급일": BBox(0, 330.0, 700.0, 470.0, 716.0),
    "전입일": BBox(0, 120.0, 402.0, 300.0, 418.0),
}

_NHIS_BOXES = {
    "가구원수": BBox(0, 300.0, 250.0, 380.0, 266.0),
    "건강보험료": BBox(0, 300.0, 300.0, 430.0, 316.0),
    "발급일": BBox(0, 330.0, 700.0, 470.0, 716.0),
}


def _abstract(
    *,
    doc_type: DocType = DocType.RESIDENT_ABSTRACT,
    issue_date: date = date(2026, 3, 5),
    confidence: float = 0.94,
    image_quality: float = 0.92,
    transfer_in: str = "2021-02-20",
    address_history: str = "포함(최근 5년)",
) -> OcrResult:
    return OcrResult(
        detected_doc_type=doc_type,
        confidence=confidence,
        image_quality=image_quality,
        issue_date=issue_date,
        fields={
            "성명": "홍길동",
            "발급일": issue_date.isoformat(),
            "전입일": transfer_in,
            "주소변동내역": address_history,
            "병역사항": "복무 완료",
        },
        bboxes=dict(_ABSTRACT_BOXES),
        tier=NAME,
    )


#: 시연 시나리오 → 고정 판독 결과.
#: 키는 파일명(확장자 제외). 값 옆 주석의 S번호는 `implement.md` 시연 시나리오다.
FIXTURES: dict[str, OcrResult] = {
    # S2 완전 적합 — 거주 5년 / 근로 3년 / 4인 건보료 200,000원 / 27세
    "S2_주민등록초본_적합": _abstract(transfer_in="2020-11-20"),
    "S2_건강보험료납부확인서_적합": OcrResult(
        detected_doc_type=DocType.NHIS_PAYMENT,
        confidence=0.95,
        image_quality=0.93,
        issue_date=date(2026, 3, 5),
        fields={
            "성명": "홍길동",
            "발급일": "2026-03-05",
            "건강보험료": "200000",
            "고지월": "2025-10,2025-11,2025-12",
            "가입구분": "직장",
        },
        bboxes=dict(_NHIS_BOXES),
        tier=NAME,
    ),
    "S2_건강보험자격확인서_적합": OcrResult(
        detected_doc_type=DocType.NHIS_QUALIFICATION,
        confidence=0.95,
        image_quality=0.93,
        issue_date=date(2026, 3, 5),
        fields={"성명": "홍길동", "발급일": "2026-03-05", "가구원수": "4", "가입구분": "직장"},
        bboxes=dict(_NHIS_BOXES),
        tier=NAME,
    ),
    "S2_건강보험자격득실확인서_적합": OcrResult(
        detected_doc_type=DocType.NHIS_ACQUISITION_LOSS,
        confidence=0.95,
        image_quality=0.93,
        issue_date=date(2026, 3, 5),
        fields={"성명": "홍길동", "발급일": "2026-03-05", "변동내역": "최근 5년 포함"},
        tier=NAME,
    ),
    "S2_4대보험가입내역확인서_적합": OcrResult(
        detected_doc_type=DocType.INSURANCE_4,
        confidence=0.93,
        image_quality=0.9,
        issue_date=date(2026, 3, 5),
        fields={"성명": "홍길동", "발급일": "2026-03-05", "취업일": "2023-01-02"},
        tier=NAME,
    ),
    # S3 초본 자리에 등본 — 공고문이 직접 지목한 미비 사유
    "S3_주민등록등본_오제출": _abstract(doc_type=DocType.RESIDENT_CERTIFICATE),
    # S4 공고일 이전 발급
    "S4_주민등록초본_발급일이전": _abstract(issue_date=date(2026, 2, 28)),
    # S5 입력한 발급일과 서류상 발급일 불일치 (업로드 화면에서 3/5로 입력하는 시나리오)
    "S5_주민등록초본_발급일불일치": _abstract(issue_date=date(2026, 3, 10)),
    # S6 암호 걸린 PDF
    "S6_주민등록초본_암호": OcrResult(
        detected_doc_type=None,
        confidence=0.0,
        image_quality=0.0,
        is_encrypted=True,
        fields={"판독실패": "PDF에 암호가 걸려 있어 열 수 없습니다."},
        tier=NAME,
    ),
    # S7 중위소득 140% 초과 (4인 직장가입자 340,000원)
    "S7_건강보험료납부확인서_소득초과": OcrResult(
        detected_doc_type=DocType.NHIS_PAYMENT,
        confidence=0.95,
        image_quality=0.93,
        issue_date=date(2026, 3, 5),
        fields={
            "성명": "홍길동",
            "발급일": "2026-03-05",
            "건강보험료": "340000",
            "고지월": "2025-10,2025-11,2025-12",
            "가입구분": "직장",
        },
        bboxes=dict(_NHIS_BOXES),
        tier=NAME,
    ),
    # S8 저해상도 사진 — 신뢰도 0.6 → NEEDS_REVIEW → 담당자 큐
    "S8_주민등록초본_저해상도": _abstract(confidence=0.6, image_quality=0.72),
    # 공고문 미비 예시 ② 초본에 과거 주소이력 미포함
    "S11_주민등록초본_주소이력없음": _abstract(address_history="미포함"),
    # 공고문 미비 예시 ⑤ 모니터 화면 캡처
    "S12_주민등록초본_화면캡처": OcrResult(
        detected_doc_type=DocType.RESIDENT_ABSTRACT,
        confidence=0.71,
        image_quality=0.66,
        issue_date=date(2026, 3, 5),
        is_screen_capture=True,
        fields={"성명": "홍길동", "발급일": "2026-03-05"},
        tier=NAME,
    ),
}


class FixtureOcr:
    """파일명으로 사전 정의된 결과를 찾는다. 못 찾으면 None → 다음 계층으로."""

    name = NAME

    def read(self, file_path: str, expected: DocType | None) -> OcrResult | None:
        del expected  # fixture는 기대 문서종류와 무관하게 파일명으로만 찾는다
        stem = Path(file_path).stem
        hit = FIXTURES.get(stem)
        if hit is None:
            return None
        # 호출자가 결과를 바꿔도 표가 오염되지 않게 복사해 돌려준다.
        return OcrResult(
            detected_doc_type=hit.detected_doc_type,
            confidence=hit.confidence,
            image_quality=hit.image_quality,
            issue_date=hit.issue_date,
            has_signature=hit.has_signature,
            fields=dict(hit.fields),
            bboxes=dict(hit.bboxes),
            is_encrypted=hit.is_encrypted,
            is_screen_capture=hit.is_screen_capture,
            page_count=hit.page_count,
            tier=NAME,
        )


def fixture_keys() -> list[str]:
    """시연 화면의 '샘플로 재현' 목록에 쓴다."""
    return sorted(FIXTURES)

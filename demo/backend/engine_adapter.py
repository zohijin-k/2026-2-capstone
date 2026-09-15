"""엔진(`engine/`)과의 유일한 접점.

엔진은 진 담당이고 이 태스크에서 수정하지 않는다. 대신 현재 엔진의 가정값과
공고문 실제값 사이의 간극을 여기서 런타임으로 흡수한다. 그래야 엔진 수정을
기다리느라 데모가 막히지 않는다.

간극 목록과 수정 요청(E1~E13)은 `.trellis/tasks/09-16-demo-site/design.md` 9절 참고.
진과 합의되는 항목부터 엔진 본체로 옮기고 여기서는 지운다.

엔진은 복사하지 않고 저장소 루트를 sys.path에 올려 import 한다. 진의 수정이
그대로 반영되어야 하기 때문이다.
"""

import sys
from pathlib import Path

#: 저장소 루트 (demo/backend/engine_adapter.py 기준 2단계 위)
REPO_ROOT = Path(__file__).resolve().parents[2]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from engine import config as engine_config  # noqa: E402
from engine.models import RequiredDocumentSpec  # noqa: E402
from engine.pipeline import run_pipeline  # noqa: E402

from .rules.doc_types import CONFUSION_GROUPS, DocType  # noqa: E402
from .rules.programs import DOUBLE_SAVINGS, JOB_PACKAGE, PROGRAMS  # noqa: E402

#: 엔진이 쓰는 사업 키 ↔ 데모가 쓰는 사업 코드
ENGINE_PROGRAM_KEY = {
    DOUBLE_SAVINGS: "전북청년적금",
    JOB_PACKAGE: "취업지원패키지",
}


def apply_runtime_overrides() -> None:
    """엔진 config를 공고문 실제값으로 덮어쓴다.

    앱 기동 시 1회 호출한다. 엔진 파일 자체는 건드리지 않는다.
    """
    _override_document_cutoff()
    _override_required_documents()
    _override_confusion_groups()


def _override_document_cutoff() -> None:
    """E5: 엔진 기본값 2026-08-01 → 사업별 실제 인정 기준일."""
    for code, program in PROGRAMS.items():
        engine_config.DOCUMENT_ISSUE_CUTOFF[ENGINE_PROGRAM_KEY[code]] = (
            program.document_cutoff
        )


def _override_required_documents() -> None:
    """E1·E2·E8: 필수서류 목록을 공고문 기준으로 교체.

    엔진 기본값은 '주민등록등본'·'소득금액증명원'을 필수로 잡고 있는데, 공고문은
    '주민등록초본(※등본 아님)'과 건강보험 3종을 요구한다. 라벨이 정반대라 그대로
    두면 적합한 신청이 전부 부적합으로 떨어진다.

    근로확인서류(5종 택1)는 엔진에 "택1 그룹" 개념이 없어 여기서 다루지 않는다.
    신청자별 맞춤 체크리스트는 P2에서 `rules/required_docs.py`가 조립한다.
    """
    cutoff = PROGRAMS[DOUBLE_SAVINGS].document_cutoff
    engine_config.REQUIRED_DOCUMENTS[ENGINE_PROGRAM_KEY[DOUBLE_SAVINGS]] = [
        RequiredDocumentSpec(
            doc_type=DocType.RESIDENT_ABSTRACT,
            required=True,
            requires_signature=False,
            check_declared_date=True,
            min_issue_date=cutoff,
        ),
        RequiredDocumentSpec(
            doc_type=DocType.NHIS_PAYMENT,
            required=True,
            requires_signature=False,
            check_declared_date=True,
            min_issue_date=cutoff,
        ),
        RequiredDocumentSpec(
            doc_type=DocType.NHIS_QUALIFICATION,
            required=True,
            requires_signature=False,
            check_declared_date=True,
            min_issue_date=cutoff,
        ),
        RequiredDocumentSpec(
            doc_type=DocType.NHIS_ACQUISITION_LOSS,
            required=True,
            requires_signature=False,
            check_declared_date=True,
            min_issue_date=cutoff,
        ),
        RequiredDocumentSpec(
            doc_type=DocType.ADMIN_INFO_CONSENT,
            required=True,
            requires_signature=True,
        ),
    ]

    job_cutoff = PROGRAMS[JOB_PACKAGE].document_cutoff
    engine_config.REQUIRED_DOCUMENTS[ENGINE_PROGRAM_KEY[JOB_PACKAGE]] = [
        RequiredDocumentSpec(
            doc_type=DocType.RESIDENT_ABSTRACT,
            required=True,
            requires_signature=False,
            check_declared_date=True,
            min_issue_date=job_cutoff,
        ),
    ]


def _override_confusion_groups() -> None:
    """E10: 오분류 탐지군을 데모의 단일 소스로 맞춘다."""
    engine_config.DOCUMENT_TYPE_CONFUSION_GROUPS = [
        {str(d) for d in group} for group in CONFUSION_GROUPS
    ]


__all__ = ["apply_runtime_overrides", "run_pipeline", "ENGINE_PROGRAM_KEY"]

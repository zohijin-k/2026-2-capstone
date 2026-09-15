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
from datetime import date
from pathlib import Path
from typing import Any

#: 저장소 루트 (demo/backend/engine_adapter.py 기준 2단계 위)
REPO_ROOT = Path(__file__).resolve().parents[2]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from engine import config as engine_config  # noqa: E402
from engine import models as engine_models  # noqa: E402
from engine.models import RequiredDocumentSpec  # noqa: E402
from engine.pipeline import run_pipeline  # noqa: E402
from engine.stage1_document_check import (  # noqa: E402
    check_single_document as engine_check_single_document,
)

from .rules.doc_types import CONFUSION_GROUPS, DocType  # noqa: E402
from .rules.programs import DOUBLE_SAVINGS, JOB_PACKAGE, PROGRAMS, ProgramConfig  # noqa: E402

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


# ---------------------------------------------------------------- 제출 변환 (P3)


def income_percent_to_decile(percent: float | None) -> int | None:
    """E6·E7 흡수 — 중위소득 % → 엔진이 요구하는 소득분위(1~10).

    엔진 `Applicant`는 아직 `income_decile`(1~10)만 받고, 2단계는 `INCOME_DECILE_LIMIT`
    (현재 9) 초과를 부적합으로 본다. 공고문의 실제 기준은 **중위소득 140% 이하**다.

    그래서 140%를 9분위 상단에 맞춘 근사 매핑을 쓴다. 140% 초과 → 10분위 →
    엔진이 INCOME_OVER_THRESHOLD로 떨어뜨린다. 판정 경계(140%)는 정확히 보존되고
    분위 값 자체는 표시용 근사치다.

    엔진이 `income_ratio`를 직접 받도록 바뀌면 이 함수는 통째로 사라진다.
    """
    if percent is None:
        return None
    if percent > 140.0:
        return 10
    ratio = max(percent, 0.0) / 140.0
    return min(9, max(1, int(ratio * 9) + 1))


def to_engine_applicant(
    *,
    application_no: str,
    name: str,
    birth_date: date | None,
    residence_region: str,
    program: ProgramConfig,
    income_percent: float | None,
    prior_support_count: int = 0,
    is_duplicate_submission: bool = False,
    conflicting_benefits: list[str] | None = None,
):
    """데모 신청 건 → 엔진 `Applicant`.

    `applicant_id`에 데모의 `application_no`를 그대로 넣는다. 담당자가 원본 서류와
    매칭하는 유일 키이므로 두 시스템이 같은 값을 써야 한다.
    """
    return engine_models.Applicant(
        applicant_id=application_no,
        name=name or "(미입력)",
        # 엔진 스키마가 birth_date를 필수로 본다. 미입력은 자격 판정에 쓰이지 않으므로
        # 기준일 밖의 값으로 채우지 않고 그대로 전달한다.
        birth_date=birth_date or date(1900, 1, 1),
        residence_region=residence_region,
        program=ENGINE_PROGRAM_KEY[program.code],
        income_decile=income_percent_to_decile(income_percent),
        prior_support_count=prior_support_count,
        is_duplicate_submission=is_duplicate_submission,
        conflicting_benefits=conflicting_benefits or [],
    )


def to_engine_documents(rows: list[dict[str, Any]]) -> list:
    """업로드 서류 목록 → 엔진 `Document` 목록.

    `doc_type`에는 **판독된** 종류를 넣는다. 그래야 엔진 1단계가 "요구 서류가 없고
    혼동군의 다른 서류가 올라왔다"를 보고 WRONG_DOCUMENT_TYPE을 잡는다. 판독이
    안 된 파일(암호 등)은 요구 서류 자리에 그대로 두어 UNREADABLE_FILE이 뜨게 한다.
    """
    documents = []
    for row in rows:
        doc_type = row.get("doc_type") or row.get("expected_doc_type") or ""
        documents.append(
            engine_models.Document(
                doc_type=str(doc_type),
                file_format=row.get("file_format") or "pdf",
                ocr_confidence=float(row.get("confidence") or 0.0),
                image_quality_score=float(row.get("image_quality") or 0.0),
                has_signature=row.get("has_signature"),
                issue_date=row.get("issue_date"),
                declared_issue_date=row.get("declared_issue_date"),
                extracted_fields=dict(row.get("fields") or {}),
                is_encrypted_or_corrupted=bool(row.get("is_encrypted")),
            )
        )
    return documents


def electronic_consent_row(agreed_at: date, signature_path: str | None) -> dict[str, Any]:
    """E4 흡수 — 전자서명으로 갈음한 서식5를 엔진에는 '서명된 서류 1건'으로 넘긴다.

    엔진 필수서류 목록에는 `행정정보공동이용동의서`가 서명 필요 서류로 들어 있다.
    데모는 이 서식을 파일로 받지 않고 캔버스 전자서명 + 동의 로그로 대체하므로
    (R1.2), 동의 기록이 있으면 여기서 서류 1건을 합성한다. 동의 기록이 없으면
    합성하지 않는다 — 그러면 엔진이 MISSING_REQUIRED_DOC을 정상적으로 잡는다.
    """
    return {
        "document_id": None,
        "slot_key": "admin_info_consent",
        "doc_type": str(DocType.ADMIN_INFO_CONSENT),
        "file_name": Path(signature_path).name if signature_path else "전자서명",
        "file_format": "png",
        "confidence": 1.0,
        "image_quality": 1.0,
        "has_signature": True,
        "issue_date": agreed_at,
        "declared_issue_date": None,
        "fields": {"서명방식": "캔버스 전자서명", "동의일": agreed_at.isoformat()},
        "is_encrypted": False,
    }


def inject_file_refs(
    review_payload: dict[str, Any] | None, documents: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """`review_payload.documents[].file_ref`를 채운다.

    엔진은 이 필드를 None으로 비워 둔다(파일 저장 위치를 모르기 때문). 담당자가
    "AI 점검 결과와 원본 서류를 함께" 보려면 이 값이 있어야 한다. 데모의 원본
    스트리밍 경로는 `/api/files/{document_id}`다.

    엔진이 만든 목록과 우리가 넘긴 목록은 순서가 같다. 순서 대신 document_id를
    같이 넣어 담당자 화면이 인덱스에 의존하지 않게 한다.
    """
    if not review_payload:
        return review_payload
    for entry, row in zip(review_payload.get("documents", []), documents):
        document_id = row.get("document_id")
        entry["document_id"] = document_id
        entry["slot_key"] = row.get("slot_key")
        entry["file_name"] = row.get("file_name")
        entry["file_ref"] = f"/api/files/{document_id}" if document_id else None
    return review_payload


__all__ = [
    "ENGINE_PROGRAM_KEY",
    "apply_runtime_overrides",
    "electronic_consent_row",
    "engine_check_single_document",
    "engine_config",
    "engine_models",
    "income_percent_to_decile",
    "inject_file_refs",
    "run_pipeline",
    "to_engine_applicant",
    "to_engine_documents",
]

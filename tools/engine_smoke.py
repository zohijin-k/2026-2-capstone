"""엔진 단독 회귀 확인 — 판정 분기 8종을 돌려 최종 판정을 고정한다.

저장소 루트에서:
    python -X utf8 -m tools.engine_smoke

데모사이트는 이 `run_pipeline()` 하나만 호출하면 된다:
    from engine.pipeline import run_pipeline
    result = run_pipeline(applicant, documents)

**최종 판정 하나만 검사한다.** 1·2단계 세부나 사유 코드까지 고정하면 엔진 담당자가
사유 문구를 다듬을 때마다 이 스크립트가 깨져서, 곧 아무도 보지 않게 된다. 분기가
살아 있는지만 지키는 것이 유지비 대비 효과가 가장 좋다.

시나리오를 늘리지도 않는다. 아래 8개가 이미 엔진의 판정 분기(발급일 컷오프 ·
신고일 불일치 · 서류 오분류 · 서명 누락 · 소득분위 · 지원 횟수 · 판독 신뢰도)를
고르게 덮는다.

`python tools/engine_smoke.py` 로는 돌지 않는다 — 그러면 sys.path[0] 이 tools/ 가
되어 `engine` 을 찾지 못한다. 반드시 `-m` 으로 부른다.
"""

import json
from datetime import date

from engine.models import Applicant, Document
from engine.pipeline import run_pipeline

_failed: list[str] = []

# 데모 기준일: config.DOCUMENT_ISSUE_CUTOFF = 2026-08-01 (전북청년적금)
VALID_ISSUE_DATE = date(2026, 8, 10)     # 컷오프 이후 -> 정상
TOO_EARLY_ISSUE_DATE = date(2026, 7, 20)  # 컷오프 이전 -> 즉시 부적합


def make_applicant(**overrides) -> Applicant:
    base = dict(
        applicant_id="APP-2027-000123",
        name="홍길동",
        birth_date=date(1998, 5, 1),
        residence_region="전주시",
        program="전북청년적금",
        income_decile=5,          # 9분위 이하 컷오프 -> 5분위는 안전하게 통과
        prior_support_count=0,
        is_duplicate_submission=False,
        conflicting_benefits=[],
    )
    base.update(overrides)
    return Applicant(**base)


def make_doc(doc_type, **overrides) -> Document:
    base = dict(
        doc_type=doc_type,
        file_format="pdf",
        ocr_confidence=0.95,
        image_quality_score=0.9,
        has_signature=True,
        issue_date=VALID_ISSUE_DATE,
        declared_issue_date=VALID_ISSUE_DATE,   # 업로드 화면에서 사용자가 입력한 값 = OCR값과 일치(기본)
        extracted_fields={},
        is_encrypted_or_corrupted=False,
    )
    base.update(overrides)
    return Document(**base)


def full_docs():
    return [
        make_doc("주민등록등본"),
        make_doc("소득금액증명원"),
        make_doc("건강보험료납부확인서"),
        make_doc("행정정보공동이용동의서"),
    ]


def print_result(title, applicant, documents, expected=None):
    print("=" * 70)
    print(f"[시나리오] {title}")
    result = run_pipeline(applicant, documents)
    actual = result.status.value
    if expected is None:
        print(f"최종 판정: {actual}")
    elif actual == expected:
        print(f"  [OK]   최종 판정: {actual}")
    else:
        _failed.append(f"{title}: 기대={expected} 실제={actual}")
        print(f"  [FAIL] 최종 판정: 기대={expected} 실제={actual}")
    print(f"- 1단계(서류): {result.stage1.status.value}")
    for f in result.stage1.findings:
        print(f"    · {f.code.value}: {f.message}")
    print(f"- 2단계(자격): {result.stage2.status.value}")
    for f in result.stage2.findings:
        print(f"    · {f.code.value}: {f.message}")
    if result.review_payload:
        print("- 담당자 검토 요청 패키지:")
        print(json.dumps(result.review_payload, ensure_ascii=False, indent=2))
    print()


def main() -> int:
    # 1) 완전 적합
    print_result("완전 적합 케이스", make_applicant(), full_docs(), "PASS")

    # 2) 등본 발행일이 기준일(8월) 이전 -> 그 즉시 부적합
    docs_too_early = full_docs()
    docs_too_early[0] = make_doc(
        "주민등록등본",
        issue_date=TOO_EARLY_ISSUE_DATE,
        declared_issue_date=TOO_EARLY_ISSUE_DATE,
    )
    print_result("등본 발행일이 기준일(8월) 이전", make_applicant(), docs_too_early, "FAIL")

    # 3) 사용자가 업로드 시 입력한 발급일과 서류상 실제 발급일 불일치 (오업로드/오기입)
    docs_mismatch = full_docs()
    docs_mismatch[0] = make_doc(
        "주민등록등본",
        issue_date=VALID_ISSUE_DATE,
        declared_issue_date=date(2026, 8, 5),  # 사용자가 다른 날짜를 입력함
    )
    print_result("입력한 발급일과 서류상 발급일 불일치", make_applicant(), docs_mismatch, "FAIL")

    # 4) 등본 대신 초본 제출 (오분류)
    docs_wrong_type = full_docs()
    docs_wrong_type[0] = make_doc("주민등록초본")
    print_result("등본 대신 초본 제출", make_applicant(), docs_wrong_type, "FAIL")

    # 5) 서명 누락 (동의서에 서명 없음)
    docs_no_sign = full_docs()
    docs_no_sign[3] = make_doc("행정정보공동이용동의서", has_signature=False)
    print_result("서명 누락", make_applicant(), docs_no_sign, "FAIL")

    # 6) 소득분위 10분위 신청 (9분위 이하만 가능 -> 부적합)
    print_result("소득분위 10분위 신청(기준 초과)", make_applicant(income_decile=10), full_docs(), "FAIL")

    # 7) 지원 횟수 초과
    print_result("지원 횟수 초과", make_applicant(prior_support_count=1), full_docs(), "FAIL")

    # 8) OCR 신뢰도 낮음 (화질은 괜찮은데 판독 자신 없음 -> 자동 FAIL 아님, 검토 큐)
    docs_low_conf = full_docs()
    docs_low_conf[0] = make_doc("주민등록등본", ocr_confidence=0.6)
    print_result("OCR 신뢰도 낮음(담당자 확인 큐)", make_applicant(), docs_low_conf, "NEEDS_REVIEW")

    print("=" * 70)
    print(f"통과 {8 - len(_failed)} / 실패 {len(_failed)}")
    for line in _failed:
        print(f"  - {line}")
    return 1 if _failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

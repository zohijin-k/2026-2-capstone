"""P3 게이트 검증 스크립트.

저장소 루트에서:
    PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python -m demo.backend.tests.run_p3_scenarios

확인하는 것:
  1. 중위소득 환산표와 구간 경계가 시행지침 서식6·공고문 140% 표와 일치한다
  2. S2(완전 적합) 채점이 **수기 검산 99점**과 일치한다 (40+25+25+9)
  3. S7(4인 건보료 340,000원)이 중위소득 153% → **자격 부적합**으로 떨어진다
  4. 항목마다 basis·source_doc·bbox가 실제로 채워져 DB에 저장된다 (담당자 화면 전제)
  5. `review_payload.documents[].file_ref`가 주입된다
  6. 제출 전 최종 확인이 부적합·누락을 잡아 제출을 막는다
  7. **마이페이지 응답 어디에도 점수가 없다** (R5.3)
  8. 동점자 정렬 키가 시행지침 우선순위 ①~④대로 정렬한다

pytest 없이 돌아간다. DB는 임시 파일에 만들고 끝나면 지운다. 업로드 파일은
`demo/fixtures/samples/`의 더미 PDF만 쓴다 — 실제 개인정보·실물 서류는 쓰지 않는다.
"""

import json
import shutil
import tempfile
from datetime import date
from pathlib import Path

from sqlmodel import create_engine, select

from .. import models
from ..rules.facts import build_facts, extract_region, parse_ymd
from ..rules.programs import DOUBLE_SAVINGS, PROGRAMS
from ..rules.scoring import (
    ESTIMATE_LABEL,
    FactSource,
    ScoringFacts,
    income_percent,
    korean_age_at,
    score_application,
)

PROGRAM = PROGRAMS[DOUBLE_SAVINGS]
SAMPLES = Path(__file__).resolve().parents[2] / "fixtures" / "samples"

_passed = 0
_failed: list[str] = []


def check(name: str, actual: object, expected: object) -> None:
    global _passed
    if actual == expected:
        _passed += 1
        print(f"  [OK]   {name}: {actual}")
    else:
        _failed.append(name)
        print(f"  [FAIL] {name}: 기대={expected!r} 실제={actual!r}")


def check_true(name: str, value: object) -> None:
    check(name, bool(value), True)


# ---------------------------------------------------------------- 1. 환산표


def test_income_table() -> None:
    print("\n[1] 중위소득 환산과 구간 경계 (공고문 140% 표 → 심사표 40점 항목)")

    percent, base_100, _ = income_percent(4, 200_000, "직장")
    check("4인 직장 100% 기준선", base_100, 222_165)
    check("4인 직장 200,000원 → 중위소득 %", round(percent, 1), 90.0)

    # 표에 없는 가구원수·가입구분은 대체값을 쓰고 그 사실을 남긴다.
    _, _, note8 = income_percent(9, 200_000, "직장")
    check_true("8인 이상 가구 대체 근거 문구", ESTIMATE_LABEL in note8)
    _, _, note_mix = income_percent(1, 100_000, "혼합")
    check_true("1인 혼합 대체 근거 문구", ESTIMATE_LABEL in note_mix)

    over, _, _ = income_percent(4, 340_000, "직장")
    check("4인 직장 340,000원 → 중위소득 %", round(over, 1), 153.0)
    check("140% 상한(311,031원) 초과 판정", over > 140.0, True)

    # 구간 경계값 — 심사표 1번 항목이 여기서 갈린다.
    def band_score(premium: int) -> int:
        facts = ScoringFacts(household_size=4, monthly_premium=premium, insurance_type="직장")
        sheet = score_application(
            facts,
            announcement_date=PROGRAM.announcement_date,
            age_basis_date=PROGRAM.age_basis_date,
        )
        return sheet.items[0].score

    check("99.9% → 40점", band_score(222_000), 40)
    check("100.0% → 37점", band_score(222_165), 37)
    check("110% → 34점", band_score(244_382), 34)
    check("120% → 31점", band_score(266_598), 31)
    check("130% → 28점", band_score(288_815), 28)


# ---------------------------------------------------------------- 2. S2 검산


S2_FACTS = ScoringFacts(
    household_size=4,
    monthly_premium=200_000,
    insurance_type="직장",
    transfer_in_date=date(2020, 11, 20),   # 거주 5년 3개월
    employment_date=date(2023, 1, 2),      # 근로 3년 2개월
    birth_date=date(1998, 6, 15),          # '25.12.31. 기준 만 27세
    sources={
        "income": FactSource(origin="테스트"),
        "residence": FactSource(origin="테스트"),
        "work": FactSource(origin="테스트"),
        "age": FactSource(origin="테스트"),
    },
)


def test_s2_scoring() -> None:
    print("\n[2] S2 완전 적합 — 심사표 수기 검산 (서식6)")
    sheet = score_application(
        S2_FACTS,
        announcement_date=PROGRAM.announcement_date,
        age_basis_date=PROGRAM.age_basis_date,
    )
    by_key = {i.key: i for i in sheet.items}

    check("만나이('25.12.31. 기준)", korean_age_at(date(1998, 6, 15), date(2025, 12, 31)), 27)
    check("1. 중위소득 (90.0% → 100% 미만)", by_key["income"].score, 40)
    check("2. 도 거주기간 (5년 이상)", by_key["residence"].score, 25)
    check("3. 근로기간 (3년 이상)", by_key["work"].score, 25)
    check("4. 연령 (25~29세)", by_key["age"].score, 9)
    check("합계", sheet.total, 99)
    check("만점", sheet.max_total, 100)
    check("자격 상한 초과 아님", sheet.income_over_limit, False)
    check("미채점 항목 없음", sheet.incomplete, False)
    for item in sheet.items:
        check_true(f"{item.label} 근거 문장", item.basis)
    print(f"         근거 예시: {by_key['income'].basis}")
    print(f"         근거 예시: {by_key['residence'].basis}")


def test_s7_scoring() -> None:
    print("\n[3] S7 중위소득 초과 — 자격 부적합")
    facts = ScoringFacts(
        household_size=4,
        monthly_premium=340_000,
        insurance_type="직장",
        transfer_in_date=date(2020, 11, 20),
        employment_date=date(2023, 1, 2),
        birth_date=date(1998, 6, 15),
    )
    sheet = score_application(
        facts,
        announcement_date=PROGRAM.announcement_date,
        age_basis_date=PROGRAM.age_basis_date,
    )
    check("중위소득 %", sheet.income_percent, 153.0)
    check("140% 상한 초과", sheet.income_over_limit, True)
    check("1. 중위소득 (130% 이상)", sheet.items[0].score, 28)
    check("합계는 계산되지만 자격 부적합", sheet.total, 87)


def test_missing_facts() -> None:
    print("\n[4] 값이 없으면 0점 + 담당자 확인 대상")
    sheet = score_application(
        ScoringFacts(),
        announcement_date=PROGRAM.announcement_date,
        age_basis_date=PROGRAM.age_basis_date,
    )
    check("합계", sheet.total, 0)
    check("미채점 항목 있음", sheet.incomplete, True)
    check("모든 항목이 판정 불가", all(i.band == "판정 불가" for i in sheet.items), True)


def test_tiebreak() -> None:
    print("\n[5] 동점자 우선순위 (① 소득 적은 자 ② 거주 긴 자 ③ 근로 긴 자 ④ 연령 낮은 자)")

    def sheet_for(premium: int, transfer: date, employed: date, birth: date):
        return score_application(
            ScoringFacts(
                household_size=4,
                monthly_premium=premium,
                insurance_type="직장",
                transfer_in_date=transfer,
                employment_date=employed,
                birth_date=birth,
            ),
            announcement_date=PROGRAM.announcement_date,
            age_basis_date=PROGRAM.age_basis_date,
        )

    # 넷 다 99점. 소득만 다르다 → 소득이 적은 쪽이 앞.
    low = sheet_for(180_000, date(2020, 11, 20), date(2023, 1, 2), date(1998, 6, 15))
    high = sheet_for(210_000, date(2020, 11, 20), date(2023, 1, 2), date(1998, 6, 15))
    check("둘 다 99점", (low.total, high.total), (99, 99))
    check("① 소득이 적은 쪽이 앞", low.tiebreak < high.tiebreak, True)

    # 소득 동일 → 거주기간이 긴 쪽이 앞.
    longer = sheet_for(200_000, date(2018, 1, 5), date(2023, 1, 2), date(1998, 6, 15))
    shorter = sheet_for(200_000, date(2020, 11, 20), date(2023, 1, 2), date(1998, 6, 15))
    check("② 거주가 긴 쪽이 앞", longer.tiebreak < shorter.tiebreak, True)

    # 소득·거주 동일 → 근로기간이 긴 쪽이 앞.
    work_long = sheet_for(200_000, date(2020, 11, 20), date(2021, 1, 2), date(1998, 6, 15))
    work_short = sheet_for(200_000, date(2020, 11, 20), date(2023, 1, 2), date(1998, 6, 15))
    check("③ 근로가 긴 쪽이 앞", work_long.tiebreak < work_short.tiebreak, True)

    # 앞의 셋 동일 → 연령이 낮은(생년월일이 늦은) 쪽이 앞.
    young = sheet_for(200_000, date(2020, 11, 20), date(2023, 1, 2), date(1999, 6, 15))
    old = sheet_for(200_000, date(2020, 11, 20), date(2023, 1, 2), date(1998, 6, 15))
    check("④ 연령이 낮은 쪽이 앞", young.tiebreak < old.tiebreak, True)

    order = sorted([high, low], key=lambda s: s.tiebreak)
    check("정렬 키로 실제 정렬", order[0] is low, True)


def test_region_and_ymd() -> None:
    print("\n[6] 입력값 환원 (주소 → 시군, 년월일 3분할 → date)")
    regions = list(PROGRAM.quota_by_region or {})
    check(
        "전북특별자치도 전주시 완산구 → 전주시",
        extract_region("전북특별자치도 전주시 완산구 효자동", regions),
        "전주시",
    )
    check("완주군 표기", extract_region("전북 완주군 봉동읍", regions), "완주군")
    check("도외 주소", extract_region("서울특별시 관악구", regions), "")
    check("년월일 3분할", parse_ymd({"y": "1998", "m": "6", "d": "15"}), date(1998, 6, 15))
    check("미입력", parse_ymd({"y": "1998", "m": "", "d": ""}), None)


# ---------------------------------------------------------------- E2E


def _api():
    """임시 DB로 갈아끼운 TestClient. demo.db를 건드리지 않는다."""
    from fastapi.testclient import TestClient

    from ..main import app

    return TestClient(app)


S2_FORM1 = {
    "savingPurpose": "주거자금",
    "priorJoined": "아니오",
    "name": "홍길동",
    "birth": {"y": "1998", "m": "6", "d": "15"},
    "gender": "남",
    "address": "전북특별자치도 전주시 완산구 효자동 123",
    "mobile": "010-0000-0000",
    "transferIn": {"y": "2020", "m": "11", "d": "20"},
    "householdType": "그 외 일반 가구",
    "householdSize": "4인",
    "workType": "상용직(노동계약기간 1년 이상)",
    "employedAt": {"y": "2023", "m": "1", "d": "2"},
    "workplaceRegion": "전북특별자치도 내 지역",
    "workplaceName": "(주)데모",
    "bankName": "농협은행",
    "accountNo": "302-0000-0000-00",
    "accountHolder": "홍길동",
    "referralPaths": ["홈페이지(도, 시군, 청년센터 등)"],
}

CONSENTS = [
    {"consent_type": "privacy", "agreed": True},
    {"consent_type": "unique_id", "agreed": True},
    {"consent_type": "third_party", "agreed": True},
    {
        "consent_type": "admin_info",
        "agreed": True,
        "signature_kind": "electronic",
        "signature_data_url": (
            "data:image/png;base64,"
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        ),
    },
]

#: 슬롯 → fixture 파일명. 파일명이 Tier1 판독 결과를 결정한다.
S2_UPLOADS = {
    "resident_abstract": "S2_주민등록초본_적합.pdf",
    "nhis_payment": "S2_건강보험료납부확인서_적합.pdf",
    "nhis_qualification": "S2_건강보험자격확인서_적합.pdf",
    "nhis_acquisition_loss": "S2_건강보험자격득실확인서_적합.pdf",
    "work_proof": "S2_4대보험가입내역확인서_적합.pdf",
}


def _create_and_fill(client, uploads: dict[str, str]) -> int:
    app_id = client.post("/api/applications", json={"program_code": DOUBLE_SAVINGS}).json()["id"]
    client.patch(f"/api/applications/{app_id}", json={"form1": S2_FORM1})
    client.post(f"/api/applications/{app_id}/consents", json={"consents": CONSENTS})
    client.put(
        f"/api/applications/{app_id}/doc-context",
        json={"work_category": "직장가입자", "workplace_count": 1},
    )
    for slot, filename in uploads.items():
        path = SAMPLES / filename
        with path.open("rb") as fh:
            client.post(
                f"/api/applications/{app_id}/documents",
                files={"file": (filename, fh, "application/pdf")},
                data={"slot_key": slot, "declared_issue_date": "2026-03-05"},
            )
    return app_id


def test_e2e(client) -> None:
    print("\n[7] 제출 전 최종 확인 → 제출 → 마이페이지 (S2)")

    # 아무것도 채우지 않은 신청 건은 제출할 수 없어야 한다.
    empty_id = client.post("/api/applications", json={"program_code": DOUBLE_SAVINGS}).json()["id"]
    empty = client.get(f"/api/applications/{empty_id}/final-check").json()
    check("빈 신청 건은 제출 불가", empty["can_submit"], False)
    check("막는 항목 수", len(empty["blockers"]), 18)
    check(
        "이동 위치가 붙어 있음",
        sorted({b["goto"] for b in empty["blockers"]}),
        ["consent", "form1", "upload"],
    )
    check("보완 없음 경고", any("보완" in w for w in empty["warnings"]), True)
    blocked = client.post(f"/api/applications/{empty_id}/submit")
    check("미완료 상태에서 제출 시도 → 400", blocked.status_code, 400)

    # S3(초본 자리에 등본)이 남아 있으면 제출을 막고, 그 슬롯으로 되돌린다.
    wrong = dict(S2_UPLOADS)
    wrong["resident_abstract"] = "S3_주민등록등본_오제출.pdf"
    wrong_id = _create_and_fill(client, wrong)
    wrong_final = client.get(f"/api/applications/{wrong_id}/final-check").json()
    check("부적합 서류가 남으면 제출 불가", wrong_final["can_submit"], False)
    doc_blockers = [b for b in wrong_final["blockers"] if b["kind"] == "document"]
    check("막는 항목은 그 서류 1건", len(doc_blockers), 1)
    check("되돌아갈 슬롯", doc_blockers[0]["target"], "resident_abstract")
    check_true("사유가 그대로 노출", "등본" in doc_blockers[0]["message"])

    app_id = _create_and_fill(client, S2_UPLOADS)
    final = client.get(f"/api/applications/{app_id}/final-check").json()
    check("S2 최종 확인 통과", final["can_submit"], True)
    check("남은 부적합 없음", final["blockers"], [])
    check("서류 5건", len(final["documents"]), 5)
    check("입력 요약에 계좌 포함", any(f["label"].startswith("입금") for f in final["form_summary"]), True)

    submitted = client.post(f"/api/applications/{app_id}/submit")
    check("제출 성공", submitted.status_code, 200)
    body = submitted.json()
    check_true("신청번호 반환", body["application_no"])
    check("제출 응답에 점수 없음", _score_leak(body), [])
    check("재제출 차단", client.post(f"/api/applications/{app_id}/submit").status_code, 400)

    # --- 저장된 심사 결과 (담당자 화면이 읽는 것) ---
    with models.get_session() as s:
        review = s.exec(
            select(models.Review).where(models.Review.application_id == app_id)
        ).first()
    check_true("review 행 생성", review)
    assert review is not None
    check("엔진 최종 판정", review.final_status, "PASS")
    check("1단계", review.stage1_status, "PASS")
    check("2단계", review.stage2_status, "PASS")
    check("저장된 총점", review.total_score, 99)

    items = {i["key"]: i for i in review.score_json["items"]}
    check("저장된 항목 수", len(items), 4)
    check("중위소득 근거 서류", items["income"]["source_doc"], "건강보험료납부확인서")
    check_true("중위소득 bbox", items["income"]["bbox"])
    check("거주기간 근거 서류", items["residence"]["source_doc"], "주민등록초본")
    check_true("거주기간 bbox", items["residence"]["bbox"])
    check("근로기간 근거 서류", items["work"]["source_doc"], "4대보험가입내역확인서")
    for key, item in items.items():
        check_true(f"{key} basis 저장", item["basis"])
        check_true(f"{key} source_document_id 저장", item["source_document_id"])
    check_true("(데모 추정치) 라벨 저장", any(ESTIMATE_LABEL in n for n in review.score_json["notes"]))
    check("동점자 키 5개 저장", len(review.tiebreak_json), 5)

    payload = review.review_payload_json
    check("review_payload 신청번호 = application_no", payload["applicant_id"], body["application_no"])
    refs = [d.get("file_ref") for d in payload["documents"] if d.get("document_id")]
    check("file_ref 주입 건수", len(refs), 5)
    check("file_ref 형식", all(str(r).startswith("/api/files/") for r in refs), True)
    check(
        "전자서명으로 갈음한 서식5가 서류 1건으로 들어감",
        any(d["doc_type"] == "행정정보공동이용동의서" for d in payload["documents"]),
        True,
    )

    # --- 마이페이지: 점수가 절대 없어야 한다 (R5.3) ---
    print("\n[8] 마이페이지 — 점수 미노출 (R5.3)")
    status = client.get(f"/api/applications/{app_id}/status").json()
    check("진행 단계 5개", [p["label"] for p in status["progress"]], ["접수", "서류검토", "자격심사", "선정심사", "결과발표"])
    check("현재 단계", [p["label"] for p in status["progress"] if p["state"] == "current"], ["서류검토"])
    check("제출 서류 판독 결과 재확인", len(status["documents"]), 5)
    check("동의 기록 4건", len(status["consents"]), 4)
    check("점수 관련 필드 없음", _score_leak(status), [])
    raw = json.dumps(status, ensure_ascii=False)
    check("총점 숫자(99)가 응답에 없음", ": 99" in raw or ":99" in raw, False)
    check("'점수'는 미공개 안내 문장에만 등장", _score_word_fields(status), ["result_notice"])
    print(f"         안내 문구: {status['result_notice']}")


def test_e2e_s7(client) -> None:
    print("\n[9] S7 — 4인 직장가입자 건보료 340,000원 → 자격 부적합")
    uploads = dict(S2_UPLOADS)
    uploads["nhis_payment"] = "S7_건강보험료납부확인서_소득초과.pdf"
    app_id = _create_and_fill(client, uploads)

    final = client.get(f"/api/applications/{app_id}/final-check").json()
    check("서류 자체는 모두 적합이라 제출은 가능", final["can_submit"], True)
    check("제출 성공", client.post(f"/api/applications/{app_id}/submit").status_code, 200)

    with models.get_session() as s:
        review = s.exec(
            select(models.Review).where(models.Review.application_id == app_id)
        ).first()
    assert review is not None
    check("엔진 최종 판정", review.final_status, "FAIL")
    check("1단계(서류)는 통과", review.stage1_status, "PASS")
    check("2단계(자격) 부적합", review.stage2_status, "FAIL")
    codes = [r["code"] for r in review.review_payload_json["reasons"]]
    check("사유", "INCOME_OVER_THRESHOLD" in codes, True)
    check("중위소득 %", review.score_json["income_percent"], 153.0)
    check("140% 상한 초과 플래그", review.score_json["income_over_limit"], True)
    check("점수는 계산되어 담당자에게 전달", review.total_score, 87)

    status = client.get(f"/api/applications/{app_id}/status").json()
    check("마이페이지에는 여전히 점수 없음", _score_leak(status), [])


def test_facts_from_documents(client) -> None:
    print("\n[10] 판독값 우선 — 서류에서 읽은 값이 신청서 입력값을 덮는다")
    app_id = _create_and_fill(client, S2_UPLOADS)
    documents = client.get(f"/api/applications/{app_id}/documents").json()
    check("업로드 서류 수", len(documents), 5)

    from ..api.common import document_fact, list_documents

    rows = [document_fact(d) for d in list_documents(app_id)]
    facts = build_facts(S2_FORM1, rows)
    check("가구원수 = 자격확인서 판독값", facts.household_size, 4)
    check("건보료 = 납부확인서 고지금액", facts.monthly_premium, 200_000)
    check("가입구분", facts.insurance_type, "직장")
    check("전입일 = 초본 판독값", facts.transfer_in_date, date(2020, 11, 20))
    check("취업일 = 신청서 입력값", facts.employment_date, date(2023, 1, 2))
    check("생년월일", facts.birth_date, date(1998, 6, 15))
    check_true("소득 근거 출처 표기", facts.source("income").origin)


# ---------------------------------------------------------------- 점수 누출 검사


#: 신청자 응답에 있으면 안 되는 키. 하나라도 있으면 R5.3 위반이다.
FORBIDDEN_KEYS = {
    "score",
    "total_score",
    "score_json",
    "total",
    "max_total",
    "items",
    "band",
    "basis",
    "tiebreak",
    "income_percent",
    "review_payload",
    "review_payload_json",
}


def _score_leak(value: object, path: str = "") -> list[str]:
    """응답 트리 전체를 훑어 점수 관련 키가 있는지 본다."""
    hits: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            here = f"{path}.{key}" if path else key
            if key in FORBIDDEN_KEYS:
                hits.append(here)
            hits.extend(_score_leak(child, here))
    elif isinstance(value, list):
        for i, child in enumerate(value):
            hits.extend(_score_leak(child, f"{path}[{i}]"))
    return hits


def _score_word_fields(value: object, path: str = "") -> list[str]:
    """'점수'라는 낱말이 등장하는 필드 경로. 미공개 안내 문장 외에는 없어야 한다."""
    hits: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            hits.extend(_score_word_fields(child, f"{path}.{key}" if path else key))
    elif isinstance(value, list):
        for i, child in enumerate(value):
            hits.extend(_score_word_fields(child, f"{path}[{i}]"))
    elif isinstance(value, str) and "점수" in value:
        hits.append(path)
    return hits


# ---------------------------------------------------------------- 진입점


def _isolate(tmp: Path) -> None:
    """DB와 업로드 저장소를 임시 경로로 갈아끼운다.

    데모 저장소(`demo/storage`, `demo/demo.db`)를 그대로 쓰면 시연용 데이터에
    테스트 파일이 섞인다. 신청번호가 임시 DB에서 1번부터 다시 매겨지는 탓에
    같은 이름의 폴더에 겹쳐 쓰기까지 한다. 둘 다 여기서 끊는다.
    """
    from ..api import applications as applications_api
    from ..api import documents as documents_api

    models.engine = create_engine(
        f"sqlite:///{tmp / 'p3.db'}", connect_args={"check_same_thread": False}
    )
    storage = tmp / "storage"
    documents_api.STORAGE = storage
    documents_api.DOCUMENTS = storage / "documents"
    applications_api.STORAGE = storage
    applications_api.SIGNATURES = storage / "signatures"


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="p3-scenarios-"))
    _isolate(tmp)

    try:
        test_income_table()
        test_s2_scoring()
        test_s7_scoring()
        test_missing_facts()
        test_tiebreak()
        test_region_and_ymd()
        with _api() as client:
            test_e2e(client)
            test_e2e_s7(client)
            test_facts_from_documents(client)
    finally:
        models.engine.dispose()
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n통과 {_passed} / 실패 {len(_failed)}")
    if _failed:
        for name in _failed:
            print(f"  - {name}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

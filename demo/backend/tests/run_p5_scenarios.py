"""P5 게이트 검증 스크립트 — 취업지원패키지 분기.

저장소 루트에서:
    PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python -m demo.backend.tests.run_p5_scenarios

확인하는 것:
  1. 사업을 바꾸면 연령 기준·서류 인정일·소득요건 유무·보완 정책이 자동으로 달라진다
  2. 자가진단이 8문항 → **2문항**(나이·거주지)으로 줄어든다
  3. 지원 항목을 복수로 고르면 항목별 추가서류 체크리스트가 실제로 조립된다
  4. 실비 계산 — 정장 70,000원 → **50,000원**, 35,000원 → 35,000원 (R6.2)
  5. 면접비는 영수증 없이 면접확인서만으로 정액 50,000원
  6. 응시확인서에 **응시일 표기가 없으면** 부적합
  7. 선착순 순번과 7일 보완 기한 카운트다운이 계산된다
  8. S10 — 면접비 2회 + 정장 1회 + 자격증 1회 복수 신청 e2e
  9. 취업패키지에도 점수는 나가지 않는다 (애초에 점수제가 아니다)

pytest 없이 돌아간다. DB와 업로드 저장소는 임시 경로에 만들고 끝나면 지운다 —
`demo/storage`·`demo/demo.db`(시연용 데이터)를 절대 건드리지 않는다.
"""

import json
import shutil
import tempfile
from pathlib import Path

from sqlmodel import create_engine, select

from .. import models
from ..rules.programs import DOUBLE_SAVINGS, JOB_PACKAGE, get_program
from ..rules.required_docs import ApplicantDocInput, build_checklist
from ..rules.roles import ROLE_PROVINCE
from ..rules.subsidy import (
    LIMITS,
    Selection,
    SubsidyType,
    estimate,
    granted_amount,
    parse_selections,
)

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


# ---------------------------------------------------------------- 시연 데이터


JOB_FORM1 = {
    "name": "김청년",
    "birth": {"y": "1999", "m": "4", "d": "10"},
    "gender": "여",
    "address": "전북특별자치도 전주시 완산구 효자동 123",
    "mobile": "010-1111-2222",
    "bankName": "전북은행",
    "accountNo": "1010-00-000000",
    "accountHolder": "김청년",
}

JOB_CONSENTS = [
    {"consent_type": "privacy", "agreed": True},
    {"consent_type": "third_party", "agreed": True},
]

#: 취업패키지 자가진단 2문항 — 나이·거주지.
JOB_SELF_CHECK = {"1": "예", "2": "예"}

#: S10 업로드 — 면접비 2회 + 정장 1회(70,000원) + 자격증 1회.
S10_UPLOADS = {
    "resident_abstract": "S10_주민등록초본_취업패키지.pdf",
    "interview_1_confirmation": "S10_면접확인서_1회차.pdf",
    "interview_2_confirmation": "S10_면접확인서_2회차.pdf",
    "suit_1_confirmation": "S10_면접확인서_정장.pdf",
    "suit_1_receipt": "S10_결제영수증_정장70000.pdf",
    "certificate_1_exam": "S10_응시확인서_적합.pdf",
    "certificate_1_receipt": "S10_결제영수증_응시료43000.pdf",
}

#: 업로드 화면에서 신청자가 직접 입력하는 발급일. 초본만 대조 대상이다.
DECLARED_DATES = {
    "S10_주민등록초본_취업패키지.pdf": "2026-04-07",
    "S8_주민등록초본_저해상도.pdf": "2026-03-05",
}

S10_SELECTION = [
    {"item_type": "interview", "count": 2, "receipts": []},
    {"item_type": "suit", "count": 1, "receipts": [70000]},
    {"item_type": "certificate", "count": 1, "receipts": [43000]},
]


def _upload(client, app_id: int, slot: str, filename: str, declared: str = "") -> dict:
    with (SAMPLES / filename).open("rb") as fh:
        res = client.post(
            f"/api/applications/{app_id}/documents",
            files={"file": (filename, fh, "application/pdf")},
            data={"slot_key": slot, "declared_issue_date": declared},
        )
    return res.json()


def create_job_application(
    client,
    *,
    selections: list[dict] | None = None,
    uploads: dict[str, str] | None = None,
    form1: dict | None = None,
) -> int:
    app_id = client.post(
        "/api/applications", json={"program_code": JOB_PACKAGE}
    ).json()["id"]
    client.patch(f"/api/applications/{app_id}", json={"form1": form1 or JOB_FORM1})
    client.post(f"/api/applications/{app_id}/self-check", json={"answers": JOB_SELF_CHECK})
    client.post(f"/api/applications/{app_id}/consents", json={"consents": JOB_CONSENTS})
    if selections is not None:
        client.post(
            f"/api/applications/{app_id}/subsidy-items", json={"items": selections}
        )
    for slot, filename in (uploads or {}).items():
        _upload(client, app_id, slot, filename, DECLARED_DATES.get(filename, ""))
    return app_id


# ---------------------------------------------------------------- 1. 사업 분기


def test_program_branching(client) -> None:
    print("\n[1] 사업을 바꾸면 기준이 통째로 달라진다 (R6)")

    programs = {p["code"]: p for p in client.get("/api/programs").json()}
    check("사업 2종", sorted(programs), [DOUBLE_SAVINGS, JOB_PACKAGE])

    ds, jp = programs[DOUBLE_SAVINGS], programs[JOB_PACKAGE]

    check("두배적금 선발", ds["selection"], "scored")
    check("취업패키지 선발", jp["selection"], "first_come")
    check("두배적금 보완", ds["supplement_days"], None)
    check("취업패키지 보완", jp["supplement_days"], 7)
    check("두배적금 연령 기준일", ds["age_basis_date"], "2025-12-31")
    check("취업패키지 연령 기준일", jp["age_basis_date"], "2026-01-01")
    check("두배적금 출생 범위", ds["birth_range"], ["1986-01-01", "2007-12-31"])
    check("취업패키지 출생 범위", jp["birth_range"], ["1987-01-01", "2008-12-31"])
    check("두배적금 서류 인정일", ds["document_cutoff"], "2026-03-03")
    check("취업패키지 서류 인정일", jp["document_cutoff"], "2026-01-01")
    check("두배적금 소득요건", ds["has_income_requirement"], True)
    check("취업패키지 소득요건", jp["has_income_requirement"], False)
    check("두배적금 근로요건", ds["has_work_requirement"], True)
    check("취업패키지 근로요건", jp["has_work_requirement"], False)
    check("두배적금 정원(시군 합계)", ds["quota_total"], 1300)
    check("취업패키지 총 지원규모", jp["quota_total"], 900)
    check("자가진단 문항 수 — 두배적금", len(ds["self_check_items"]), 8)
    check("자가진단 문항 수 — 취업패키지", len(jp["self_check_items"]), 2)
    check("지원 항목표는 취업패키지에만", ds["subsidy_catalog"], None)
    check("지원 항목 4종", [c["item_type"] for c in jp["subsidy_catalog"]],
          ["interview", "suit", "photo", "certificate"])

    print("\n  -- 사업계획서 지원내용 표와 숫자가 일치하는가")
    by_type = {c["item_type"]: c for c in jp["subsidy_catalog"]}
    check("면접비", (by_type["interview"]["unit_cap"], by_type["interview"]["max_count"],
                   by_type["interview"]["actual_cost"]), (50000, 2, False))
    check("정장비", (by_type["suit"]["unit_cap"], by_type["suit"]["max_count"],
                   by_type["suit"]["actual_cost"]), (50000, 2, True))
    check("면접사진", (by_type["photo"]["unit_cap"], by_type["photo"]["max_count"],
                    by_type["photo"]["actual_cost"]), (20000, 1, True))
    check("자격증 응시료", (by_type["certificate"]["unit_cap"],
                       by_type["certificate"]["max_count"],
                       by_type["certificate"]["actual_cost"]), (50000, 2, True))
    print("\n  -- 미확정 가정값에 (데모 추정치) 라벨이 붙어 있는가")
    check_true(
        "취업패키지 가정값 라벨", any("(데모 추정치)" in n for n in jp["notes"])
    )
    print(f"         {[n for n in jp['notes'] if '(데모 추정치)' in n]}")

    check("면접비 추가서류", by_type["interview"]["extra_docs"], ["면접확인서"])
    check("정장비 추가서류", by_type["suit"]["extra_docs"], ["면접확인서", "결제영수증"])
    check("사진비 추가서류", by_type["photo"]["extra_docs"], ["면접용 사진사본", "결제영수증"])
    check("자격증 추가서류", by_type["certificate"]["extra_docs"],
          ["응시확인서 또는 성적표", "결제영수증"])


# ---------------------------------------------------------------- 2. 자가진단


def test_self_check(client) -> None:
    print("\n[2] 자가진단 축소판 — 8문항 → 2문항 (나이·거주지)")

    job_id = client.post("/api/applications", json={"program_code": JOB_PACKAGE}).json()["id"]
    result = client.post(
        f"/api/applications/{job_id}/self-check", json={"answers": {"1": "예", "2": "예"}}
    ).json()
    check("2문항만 답해도 완료", result["completed"], True)
    check("자격 있음", result["eligible"], True)
    check("물은 문항 수", result["total_items"], 2)

    denied = client.post(
        f"/api/applications/{job_id}/self-check", json={"answers": {"1": "예", "2": "아니오"}}
    ).json()
    check("연령 미달 → 부적격", denied["eligible"], False)
    check("막힌 문항", denied["failed_item"], 2)
    check_true("취업패키지 연령 기준으로 안내", "1987. 1. 1." in denied["reason"])
    check_true("2008년생까지 안내", "2008. 12. 31." in denied["reason"])

    print("\n  -- 같은 답변을 두배적금에 넣으면 아직 미완료다 (8문항이므로)")
    ds_id = client.post(
        "/api/applications", json={"program_code": DOUBLE_SAVINGS}
    ).json()["id"]
    ds_result = client.post(
        f"/api/applications/{ds_id}/self-check", json={"answers": {"1": "예", "2": "예"}}
    ).json()
    check("두배적금은 2문항으로 끝나지 않는다", ds_result["completed"], False)
    check("두배적금 문항 수", ds_result["total_items"], 8)


# ---------------------------------------------------------------- 3. 실비 계산


def test_subsidy_math() -> None:
    print("\n[3] 실비 계산 — 영수증 금액과 한도 비교 (R6.2)")

    print("\n  -- 게이트: 정장 대여 영수증 70,000원")
    check("정장 70,000원 → 지급액", granted_amount(SubsidyType.SUIT, 70000), 50000)
    check("정장 35,000원 → 지급액", granted_amount(SubsidyType.SUIT, 35000), 35000)
    check("정장 한도 정확히 50,000원", granted_amount(SubsidyType.SUIT, 50000), 50000)
    check("정장 1원", granted_amount(SubsidyType.SUIT, 1), 1)

    print("\n  -- 나머지 실비 항목 경계값")
    check("사진 18,000원", granted_amount(SubsidyType.PHOTO, 18000), 18000)
    check("사진 25,000원 → 한도 20,000원", granted_amount(SubsidyType.PHOTO, 25000), 20000)
    check("응시료 43,000원", granted_amount(SubsidyType.CERTIFICATE, 43000), 43000)
    check("응시료 60,000원 → 한도 50,000원", granted_amount(SubsidyType.CERTIFICATE, 60000), 50000)

    print("\n  -- 면접비만 정액 (영수증 불요)")
    check("면접비는 영수증 없이도 50,000원", granted_amount(SubsidyType.INTERVIEW, None), 50000)
    check("면접비는 영수증이 적어도 50,000원", granted_amount(SubsidyType.INTERVIEW, 10000), 50000)
    check("면접비는 영수증을 받지 않는다", LIMITS[SubsidyType.INTERVIEW].needs_receipt, False)

    print("\n  -- 실비 항목은 영수증 금액이 없으면 확정되지 않는다")
    pending = estimate([Selection(SubsidyType.SUIT, 1, [None])])
    check("미확정 표시", pending.pending, True)
    check("미확정 지급액", pending.total_granted, 0)
    check_true("입력 안내", "영수증" in pending.lines[0]["calculation"]
               if isinstance(pending.lines[0], dict) else "영수증" in pending.lines[0].calculation)

    print("\n  -- 횟수 상한 초과는 상한으로 깎고 사실을 알린다")
    over = estimate(parse_selections([{"item_type": "interview", "count": 3}]))
    check("면접비 3회 → 2줄", len(over.lines), 2)
    check("합계", over.total_granted, 100000)
    check_true("조정 경고", any("최대 2회" in w for w in over.warnings))
    photo_over = estimate(parse_selections([{"item_type": "photo", "count": 2, "receipts": [18000, 18000]}]))
    check("사진비 2회 → 1줄", len(photo_over.lines), 1)
    check("사진비 합계", photo_over.total_granted, 18000)

    print("\n  -- S10 조합 합계")
    s10 = estimate(parse_selections(S10_SELECTION))
    check(
        "회차별 지급액",
        [(line.label, line.granted_amount) for line in s10.lines],
        [
            ("면접비 1회차", 50000),
            ("면접비 2회차", 50000),
            ("면접정장비 1회차", 50000),
            ("자격증 응시료 1회차", 43000),
        ],
    )
    check("S10 예상 지원금 합계", s10.total_granted, 193000)
    suit_line = next(line for line in s10.lines if line.label.startswith("면접정장비"))
    print(f"         정장 계산 근거: {suit_line.calculation}")
    check_true("한도 초과 근거 문장", "70,000원 > 한도 50,000원" in suit_line.calculation)


# ---------------------------------------------------------------- 4. 체크리스트


def test_checklist_assembly(client) -> None:
    print("\n[4] 지원 항목을 바꾸면 추가서류 체크리스트가 실제로 바뀐다 (R6.3)")

    program = get_program(JOB_PACKAGE)
    base = build_checklist(program, ApplicantDocInput())
    check(
        "항목을 안 고르면 공통서류만",
        [r.slot_key for r in base],
        ["application_form", "resident_abstract", "bank_account"],
    )
    check("업로드가 필요한 공통서류는 초본 1종", [r.slot_key for r in base if r.upload],
          ["resident_abstract"])
    check(
        "신청서는 온라인 작성으로 갈음",
        next(r.fulfilled_by for r in base if r.slot_key == "application_form"),
        "온라인 신청서 작성 + 동의 기록",
    )
    check(
        "통장 사본은 계좌 입력으로 갈음 (R1.4)",
        next(r.fulfilled_by for r in base if r.slot_key == "bank_account"),
        "신청서의 계좌번호 입력",
    )

    print("\n  -- API로 항목을 고르면 서버가 다시 조립한다")
    app_id = create_job_application(client, selections=[{"item_type": "interview", "count": 1}])
    one = client.get(f"/api/applications/{app_id}/required-documents").json()
    check(
        "면접비 1회 → 면접확인서 1장",
        [i["slot_key"] for i in one["items"] if i["upload"]],
        ["resident_abstract", "interview_1_confirmation"],
    )

    client.post(
        f"/api/applications/{app_id}/subsidy-items", json={"items": S10_SELECTION}
    )
    many = client.get(f"/api/applications/{app_id}/required-documents").json()
    check(
        "면접비 2회 + 정장 1회 + 자격증 1회",
        [i["slot_key"] for i in many["items"] if i["upload"]],
        [
            "resident_abstract",
            "interview_1_confirmation",
            "interview_2_confirmation",
            "suit_1_confirmation",
            "suit_1_receipt",
            "certificate_1_exam",
            "certificate_1_receipt",
        ],
    )
    check("업로드 슬롯 수", many["upload_total"], 7)
    check("근로유형을 묻지 않는다", many["program"]["asks_work_category"], False)
    check("지원 항목이 있는 사업", many["program"]["has_subsidy_items"], True)

    exam = next(i for i in many["items"] if i["slot_key"] == "certificate_1_exam")
    check("응시확인서 또는 성적표 택1", exam["doc_type_choices"], ["응시확인서", "성적표"])
    check("응시일 표기 필수", exam["required_fields"], ["응시일"])
    check_true("응시일 경고 문구", any("응시일" in w for w in exam["warnings"]))
    check(
        "취업패키지 인정 기준일이 슬롯에 붙는다",
        exam["min_issue_date"],
        "2026-01-01",
    )

    print("\n  -- 항목을 빼면 그 서류도 사라진다")
    client.post(
        f"/api/applications/{app_id}/subsidy-items",
        json={"items": [{"item_type": "photo", "count": 1, "receipts": [18000]}]},
    )
    photo = client.get(f"/api/applications/{app_id}/required-documents").json()
    check(
        "사진비만 남김",
        [i["slot_key"] for i in photo["items"] if i["upload"]],
        ["resident_abstract", "photo_1_photo", "photo_1_receipt"],
    )

    print("\n  -- 두배적금에서는 지원 항목 API 자체가 거부된다")
    ds_id = client.post("/api/applications", json={"program_code": DOUBLE_SAVINGS}).json()["id"]
    rejected = client.post(
        f"/api/applications/{ds_id}/subsidy-items", json={"items": S10_SELECTION}
    )
    check("두배적금은 항목 선택 사업이 아니다", rejected.status_code, 400)


# ---------------------------------------------------------------- 5. 응시일 검증


def test_exam_date_required(client) -> None:
    print("\n[5] 응시확인서·성적표 — 응시일 표기가 없으면 부적합")

    app_id = create_job_application(
        client, selections=[{"item_type": "certificate", "count": 1, "receipts": [43000]}]
    )

    missing = _upload(client, app_id, "certificate_1_exam", "S10_응시확인서_응시일없음.pdf")
    check("응시일 없는 응시확인서 판정", missing["status"], "FAIL")
    codes = [f["code"] for f in missing["findings"]]
    check("사유 코드", codes, ["MISSING_REQUIRED_FIELD"])
    print(f"         사유: {missing['findings'][0]['message']}")
    print(f"         해결: {missing['findings'][0]['how_to_fix']}")
    check_true("해결 방법에 응시일 표기 안내", "응시일" in missing["findings"][0]["how_to_fix"])

    ok = _upload(client, app_id, "certificate_1_exam", "S10_응시확인서_적합.pdf")
    check("응시일 있는 응시확인서", ok["status"], "PASS")
    check("응시일 판독", ok["extracted"].get("응시일"), "2026-03-22")

    transcript = _upload(client, app_id, "certificate_1_exam", "S10_성적표_적합.pdf")
    check("성적표도 같은 자리에 인정된다 (택1)", transcript["status"], "PASS")
    check("판독된 서류", transcript["detected_doc_type"], "성적표")

    wrong = _upload(client, app_id, "certificate_1_exam", "S10_면접확인서_1회차.pdf")
    check("엉뚱한 서류는 여전히 부적합", wrong["status"], "FAIL")
    check("사유", [f["code"] for f in wrong["findings"]], ["WRONG_DOCUMENT_TYPE"])

    print("\n  -- 결제영수증은 금액을 읽어 실비 계산의 근거로 남긴다")
    receipt = _upload(client, app_id, "certificate_1_receipt", "S10_결제영수증_응시료43000.pdf")
    check("영수증 판정", receipt["status"], "PASS")
    check("판독된 결제금액", receipt["extracted"].get("결제금액"), "43000")


# ---------------------------------------------------------------- 6. S10 e2e


def test_s10_end_to_end(client) -> int:
    print("\n[6] S10 — 면접비 2회 + 정장 1회 + 자격증 1회 복수 신청 (게이트)")

    app_id = create_job_application(
        client, selections=S10_SELECTION, uploads=S10_UPLOADS
    )

    saved = client.get(f"/api/applications/{app_id}/subsidy-items").json()
    check("저장된 선택 항목 수", len(saved["selections"]), 3)
    check("예상 지원금 합계", saved["estimate"]["total_granted"], 193000)
    suit = next(
        line for line in saved["estimate"]["lines"] if line["item_type"] == "suit"
    )
    check("정장 영수증 70,000원", suit["receipt_amount"], 70000)
    check("정장 지급액 50,000원", suit["granted_amount"], 50000)
    print(f"         계산 근거: {suit['calculation']}")

    final = client.get(f"/api/applications/{app_id}/final-check").json()
    check("제출 가능", final["can_submit"], True)
    check("남은 부적합 없음", final["blockers"], [])
    check("보완이 있는 사업", final["allows_supplement"], True)
    check_true("보완 안내 문구", any("7일" in w for w in final["warnings"]))
    check("선착순 안내", final["first_come"]["quota"], 900)
    check("최종 확인 화면에도 예상 지원금", final["subsidy"]["total_granted"], 193000)
    check(
        "요약에 거주기간·근로사항이 없다",
        [f["label"] for f in final["form_summary"]],
        ["신청자 이름", "생년월일", "성별", "주소", "연락처", "입금 받을 계좌"],
    )

    body = client.post(f"/api/applications/{app_id}/submit").json()
    check("접수 순번", body["first_come"]["position"], 1)
    check("남은 지원규모", body["first_come"]["remaining"], 899)
    check("제출 응답의 지원금", body["subsidy"]["total_granted"], 193000)
    check_true("선착순 안내 문구", "선착순" in body["notice"])
    check_true("보완 안내가 다음 절차에 있다", any("7일" in s for s in body["next_steps"]))

    with models.get_session() as s:
        review = s.exec(
            select(models.Review).where(models.Review.application_id == app_id)
        ).first()
        rows = list(
            s.exec(
                select(models.SubsidyItem).where(
                    models.SubsidyItem.application_id == app_id
                )
            ).all()
        )
    assert review is not None
    check("엔진 최종 판정", review.final_status, "PASS")
    check("점수제가 아니므로 총점 없음", review.total_score, None)
    check("심사표 없음", review.score_json, {})
    check("소득요건이 없어 2단계도 통과", review.stage2_status, "PASS")
    check("저장된 지원 항목 행 수", len(rows), 4)
    check("저장된 실지급액 합계", sum(r.granted_amount for r in rows), 193000)

    status = client.get(f"/api/applications/{app_id}/status").json()
    check(
        "진행 단계가 취업패키지 추진체계를 따른다",
        [p["label"] for p in status["progress"]],
        ["접수", "서류검토", "지원대상자·보완 안내", "보완서류 검토", "지원금 지급"],
    )
    check("마이페이지 선착순 순번", status["first_come"]["position"], 1)
    check("마이페이지 예상 지원금", status["subsidy"]["total_granted"], 193000)
    check("서류가 전부 적합이면 보완 기한이 없다", status["supplement"], None)
    check("마이페이지에 점수 관련 필드 없음", _score_leak(status), [])
    return app_id


# ---------------------------------------------------------------- 7. 7일 보완


def test_supplement_countdown(client) -> int:
    print("\n[7] 7일 보완 기한 카운트다운 (E12)")

    uploads = dict(S10_UPLOADS)
    # 저해상도 초본 → 판독 신뢰도 0.6 → 확인필요. 제출은 되지만 보완 대상이다.
    uploads["resident_abstract"] = "S8_주민등록초본_저해상도.pdf"
    app_id = create_job_application(client, selections=S10_SELECTION, uploads=uploads)

    final = client.get(f"/api/applications/{app_id}/final-check").json()
    check("확인필요 서류가 있어도 제출은 가능", final["can_submit"], True)

    body = client.post(f"/api/applications/{app_id}/submit").json()
    check("두 번째 접수 순번", body["first_come"]["position"], 2)

    supplement = body["supplement"]
    check_true("보완 기한이 잡혔다", supplement)
    check("보완 일수", supplement["days"], 7)
    check("남은 일수", supplement["days_left"], 7)
    check("기한 만료 아님", supplement["expired"], False)
    check_true("보완 대상 서류가 지목된다", supplement["targets"])
    check("보완 대상", supplement["targets"][0]["label"], "주민등록초본")
    print(f"         기한: {supplement['deadline']} · {supplement['notice']}")

    status = client.get(f"/api/applications/{app_id}/status").json()
    check("마이페이지에도 카운트다운", status["supplement"]["days_left"], 7)

    print("\n  -- 두배적금은 보완도 선착순도 없다")
    ds_id = client.post(
        "/api/applications", json={"program_code": DOUBLE_SAVINGS}
    ).json()["id"]
    ds_status = client.get(f"/api/applications/{ds_id}/status").json()
    check("두배적금 보완 블록 없음", ds_status["supplement"], None)
    check("두배적금 선착순 블록 없음", ds_status["first_come"], None)
    check("두배적금 지원 항목 블록 없음", ds_status["subsidy"], None)
    return app_id


# ---------------------------------------------------------------- 8. 담당자 화면


def test_officer_view(client, job_ids: list[int]) -> None:
    print("\n[8] 담당자 화면 — 선착순 목록과 항목별 지급 내역")

    listing = client.get(
        "/api/officer/applications",
        params={"role": ROLE_PROVINCE, "program": JOB_PACKAGE},
    ).json()
    check("취업패키지 건수", listing["total"], len(job_ids))
    check("기본 정렬이 접수순", listing["filters"]["applied"]["sort"], "submitted")
    check(
        "접수 순서대로 줄선다",
        [r["application_id"] for r in listing["rows"]],
        job_ids,
    )
    check("점수 칸은 비어 있다", [r["total_score"] for r in listing["rows"]],
          [None] * len(job_ids))
    check("선착순 진행률 배지", listing["first_come"]["quota"], 900)
    check("접수 건수", listing["first_come"]["applied"], len(job_ids))
    check("시군 정원 배지는 두배적금 것", all(q["region"] for q in listing["quota"]), True)

    ds_listing = client.get(
        "/api/officer/applications",
        params={"role": ROLE_PROVINCE, "program": DOUBLE_SAVINGS},
    ).json()
    check("두배적금은 점수순", ds_listing["filters"]["applied"]["sort"], "score")
    check("두배적금에는 선착순 배지가 없다", ds_listing["first_come"], None)

    detail = client.get(
        f"/api/officer/applications/{job_ids[0]}", params={"role": ROLE_PROVINCE}
    ).json()
    check("선발 방식", detail["selection"], "first_come")
    check("심사표 없음", detail["score_sheet"], {})
    check(
        "자격요건은 거주지·연령 2항목",
        [e["key"] for e in detail["eligibility"]],
        ["residence", "age"],
    )
    check("자격요건 충족", all(e["ok"] for e in detail["eligibility"]), True)
    check("지원 항목 지급 내역", detail["subsidy"]["total_granted"], 193000)
    check("보완 대상이 아니면 기한 없음", detail["supplement"], None)

    review_detail = client.get(
        f"/api/officer/applications/{job_ids[1]}", params={"role": ROLE_PROVINCE}
    ).json()
    check("확인필요 건에는 보완 기한", review_detail["supplement"]["days_left"], 7)
    check("AI 판정", review_detail["ai"]["final_status"], "NEEDS_REVIEW")

    print("\n  -- 원본은 여전히 인라인으로만 나간다 (P4 DoD 유지)")
    for doc in detail["documents"][:3]:
        res = client.get(doc["file_url"])
        check(
            f"{doc['label'][:14]} inline",
            res.headers.get("content-disposition", "").split(";")[0],
            "inline",
        )


# ---------------------------------------------------------------- 점수 누출 감시


FORBIDDEN_KEYS = {
    "score",
    "total_score",
    "score_json",
    "max_total",
    "band",
    "basis",
    "tiebreak",
    "income_percent",
    "review_payload",
    "review_payload_json",
    "rank",
}


def _score_leak(value: object, path: str = "") -> list[str]:
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


# ---------------------------------------------------------------- 진입점


def _isolate(tmp: Path) -> None:
    """DB와 업로드 저장소를 임시 경로로 갈아끼운다.

    데모 저장소(`demo/storage`, `demo/demo.db`)를 그대로 쓰면 시연용 데이터에
    테스트 파일이 섞인다. 신청번호가 임시 DB에서 1번부터 다시 매겨지는 탓에
    같은 이름의 폴더에 겹쳐 쓰기까지 한다. 셋 다 여기서 끊는다.
    """
    from ..api import applications as applications_api
    from ..api import documents as documents_api
    from ..api import files as files_api

    models.engine = create_engine(
        f"sqlite:///{tmp / 'p5.db'}", connect_args={"check_same_thread": False}
    )
    storage = tmp / "storage"
    documents_api.STORAGE = storage
    documents_api.DOCUMENTS = storage / "documents"
    applications_api.STORAGE = storage
    applications_api.SIGNATURES = storage / "signatures"
    files_api.STORAGE = storage


def main() -> int:
    from fastapi.testclient import TestClient

    from ..main import app

    tmp = Path(tempfile.mkdtemp(prefix="p5-scenarios-"))
    _isolate(tmp)

    try:
        with TestClient(app) as client:
            test_program_branching(client)
            test_self_check(client)
            test_subsidy_math()
            test_checklist_assembly(client)
            test_exam_date_required(client)
            s10_id = test_s10_end_to_end(client)
            supplement_id = test_supplement_countdown(client)
            test_officer_view(client, [s10_id, supplement_id])
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

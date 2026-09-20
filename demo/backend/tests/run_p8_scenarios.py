"""P8 게이트 검증 스크립트 — 현황 대시보드 집계 API.

저장소 루트에서:
    python -X utf8 -m demo.backend.tests.run_p8_scenarios

확인하는 것:
  1. **소득 배점 구간이 뒤집히지 않는다** — 이 스크립트의 존재 이유다. 백엔드
     배점표는 높은 소득이 0번(130% 이상 = 28점)이고 화면 배점표는 낮은 소득이
     0번(100% 미만 = 40점)이다. 인덱스를 그대로 주고받으면 점수가 정확히 뒤집히는데,
     화면은 아무 에러 없이 그럴듯한 분포를 그린다.
  2. 배점·커트라인이 **권한 없이는 응답에 아예 없다** — 값이 null 인 것으로는
     부족하다. 배열째 없어야 한다.
  3. 화면 집계를 터뜨리는 값(시군 밖 주소 · 연령 범위 밖 · 미채점)을 서버가 걸러
     내고 그 사실을 notes 에 남긴다.
  4. 공개 행에 이름·주소가 섞이지 않는다.
  5. 일정이 실제 제출 시각에서 나온다.

pytest 없이 돌아간다. DB와 업로드 저장소는 임시 경로에 만들고 끝나면 지운다 —
demo/storage·demo/demo.db(시연용 데이터)를 절대 건드리지 않는다.
"""

import shutil
import tempfile
from pathlib import Path

from sqlmodel import create_engine

from .. import models
from ..api import dashboard as dashboard_api
from ..rules.programs import DOUBLE_SAVINGS
from ..rules.roles import ROLE_CITY, ROLE_PROVINCE, ROLE_TOWN
from .run_p4_scenarios import BASE_FORM1, CONSENTS, SAMPLES, SELF_CHECK_ANSWERS, S2_UPLOADS

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


def _create(client, *, name: str, address: str, birth: dict, uploads: dict) -> int:
    app_id = client.post("/api/applications", json={"program_code": DOUBLE_SAVINGS}).json()["id"]
    form1 = {**BASE_FORM1, "name": name, "address": address, "birth": birth}
    client.patch(f"/api/applications/{app_id}", json={"form1": form1})
    client.post(f"/api/applications/{app_id}/self-check", json={"answers": SELF_CHECK_ANSWERS})
    client.post(f"/api/applications/{app_id}/consents", json={"consents": CONSENTS})
    client.put(
        f"/api/applications/{app_id}/doc-context",
        json={"work_category": "직장가입자", "workplace_count": 1},
    )
    for slot, filename in uploads.items():
        with (SAMPLES / filename).open("rb") as fh:
            client.post(
                f"/api/applications/{app_id}/documents",
                files={"file": (filename, fh, "application/pdf")},
                data={"slot_key": slot, "declared_issue_date": "2026-03-05"},
            )
    client.post(f"/api/applications/{app_id}/submit")
    return app_id


def seed(client) -> None:
    """4건. 소득 구간 양 끝 · 시군 밖 주소 · 연령 범위 밖이 섞이게 배치한다."""
    over_income = {**S2_UPLOADS, "nhis_payment": "S7_건강보험료납부확인서_소득초과.pdf"}
    birth_ok = {"y": "1998", "m": "6", "d": "15"}  # '25.12.31. 기준 만 27세

    # A — 전주 · 중위소득 67.1% → 소득 40점 → 화면 구간 0번
    _create(client, name="홍길동", address="전북특별자치도 전주시 완산구 효자동 123",
            birth=birth_ok, uploads=S2_UPLOADS)
    # B — 군산 · 중위소득 153% → 소득 28점 → 화면 구간 4번 (A와 정반대 끝)
    _create(client, name="김영희", address="전북특별자치도 군산시 나운동 45",
            birth=birth_ok, uploads=over_income)
    # C — 시군을 읽을 수 없는 주소. 걸러져야 한다.
    _create(client, name="박철수", address="서울특별시 종로구 세종대로 1",
            birth=birth_ok, uploads=S2_UPLOADS)
    # D — 연령 범위 밖(만 56세). 신청 자체는 막히지 않고 엔진이 부적합으로 처리한다.
    _create(client, name="이민수", address="전북특별자치도 익산시 영등동 7",
            birth={"y": "1969", "m": "3", "d": "3"}, uploads=S2_UPLOADS)


# ---------------------------------------------------------------- 검사


def test_income_band_not_flipped(client) -> None:
    print("\n[1] 소득 배점 구간이 뒤집히지 않는다")
    body = client.get("/api/dashboard/dataset", params={"role": ROLE_CITY}).json()
    scores = {row["id"]: row for row in body["scores"]}
    apps = {row["id"]: row for row in body["applications"]}

    by_region = {apps[i]["region"]: scores.get(i) for i in apps}
    jeonju = by_region.get("전주시")
    gunsan = by_region.get("군산시")

    check_true("전주 건 배점 있음", jeonju)
    check_true("군산 건 배점 있음", gunsan)
    if not (jeonju and gunsan):
        return

    # 화면 배점표: 0번 = 100% 미만 = 40점 / 4번 = 130% 이상 = 28점.
    # 뒤집혀 있으면 아래 두 줄이 정확히 서로 바뀐다.
    check("중위소득 67% 건의 소득 구간", jeonju["incomeBand"], 0)
    check("중위소득 153% 건의 소득 구간", gunsan["incomeBand"], 4)
    check_true("소득 구간이 서로 다르다", jeonju["incomeBand"] != gunsan["incomeBand"])

    # 거주·근로는 양쪽 표의 순서가 같다. 같은 입력이므로 같은 구간이어야 한다.
    check("거주 구간 일치", jeonju["residenceBand"], gunsan["residenceBand"])
    check("근로 구간 일치", jeonju["workBand"], gunsan["workBand"])
    check_true("총점이 화면 최저점 이상", jeonju["score"] >= dashboard_api.MIN_TOTAL_SCORE)


def test_scores_withheld(client) -> None:
    print("\n[2] 배점은 권한 없이 응답에 존재하지 않는다")
    plain = client.get("/api/dashboard/dataset").json()
    check("권한 없음 → scores", plain["scores"], None)
    check_true("이유를 밝힌다", plain["scoresWithheldReason"])

    # null 이 아니라 '없다'를 확인한다. 공개 행 어디에도 점수 필드가 없어야 한다.
    leaked = [k for row in plain["applications"] for k in row
              if k in {"score", "incomeBand", "residenceBand", "workBand"}]
    check("공개 행의 점수 필드", leaked, [])

    check("읍면동 → scores", client.get(
        "/api/dashboard/dataset", params={"role": ROLE_TOWN}).json()["scores"], None)
    for role in (ROLE_CITY, ROLE_PROVINCE):
        body = client.get("/api/dashboard/dataset", params={"role": role}).json()
        check_true(f"{role} → scores 배열", isinstance(body["scores"], list))
        check(f"{role} → 이유 없음", body["scoresWithheldReason"], None)


def test_guards(client) -> None:
    print("\n[3] 화면을 터뜨리는 값을 서버가 걸러 낸다")
    body = client.get("/api/dashboard/dataset").json()
    regions = {row["region"] for row in body["applications"]}

    check("집계된 건수", body["total"], 2)
    check("시군 밖 주소 제외", "서울특별시" in regions, False)
    check("14개 시군만 남음", regions, {"전주시", "군산시"})
    check_true("제외 사실을 notes 에 남긴다", any("시군" in n for n in body["notes"]))
    check_true("연령 제외도 남긴다", any("세 밖" in n for n in body["notes"]))

    for row in body["applications"]:
        check_true(f"{row['id']} 연령이 18~39", 18 <= row["age"] <= 39)
        check_true(f"{row['id']} 가구원수 1 이상", row["householdSize"] >= 1)


def test_public_fields(client) -> None:
    print("\n[4] 공개 행에 개인 식별 정보가 없다")
    body = client.get("/api/dashboard/dataset", params={"role": ROLE_PROVINCE}).json()
    row = body["applications"][0]
    for field in ("name", "address", "mobile", "accountNo", "birth"):
        check(f"{field} 없음", field in row, False)

    check("성별 표기", row["gender"] in {"남성", "여성"}, True)
    check("근로유형 표기", row["workType"], "상용직")
    check("가입유형 표기", row["insuranceType"], "직장가입자")
    check("가구원수", row["householdSize"], 4)

    # 부적합 단계 매핑. 중위소득 초과는 2단계(자격) 부적합이다.
    gunsan = next(r for r in body["applications"] if r["region"] == "군산시")
    check("소득 초과 건의 부적합 단계", gunsan["rejectStage"], "eligibility")
    check_true("부적합 사유 문장", gunsan["rejectReason"])

    # 2차 중복 조회는 데모에 연동이 없어 절대 발화하지 않는다.
    check("duplicate 단계", any(r["rejectStage"] == "duplicate" for r in body["applications"]), False)

    # 엔진이 제출과 동시에 1·2단계를 끝내므로 심사 완료 시각이 채워져 있어야 한다.
    # 담당자가 판단을 누른 시각을 여기 쓰면, 엔진이 이미 부적합으로 판정한 건이
    # 담당자가 열기 전까지 "심사 중"에 머물고 부적합 사유 차트가 빈 채로 남는다.
    for row in body["applications"]:
        check_true(f"{row['id']} 서류 확인 시각", row["docReviewedAt"])
        check_true(f"{row['id']} 자격 심사 시각", row["eligibilityReviewedAt"])
    check_true("부적합 건이 심사 중에 머물지 않는다", gunsan["eligibilityReviewedAt"])


def test_schedule_and_meta(client) -> None:
    print("\n[5] 일정이 실제 제출 시각에서 나온다")
    body = client.get("/api/dashboard/dataset").json()
    s = body["schedule"]
    check_true("접수 시작 < 마감", s["openAt"] < s["closeAt"])
    check_true("마감 < 1차 선정", s["closeAt"] < s["firstSelectionAt"]["전주시"])
    check_true("1차 < 2차 < 발표",
               s["firstSelectionAt"]["전주시"] < s["secondVerificationAt"] < s["announcementAt"])
    check("14개 시군 전부 1차 일정", len(s["firstSelectionAt"]), 14)
    check("정원표 14개 시군", len(body["regions"]), 14)
    check("정원 합계", sum(r["quota"] for r in body["regions"]), 1300)

    submitted = [r["submittedAt"] for r in body["applications"] if r["submittedAt"]]
    check_true("제출 시각이 접수 구간 안", all(s["openAt"] <= t <= s["closeAt"] for t in submitted))

    meta = client.get("/api/dashboard/meta").json()
    check("meta.total 은 제출 건 전부", meta["total"], 4)
    check("dataset.total 은 집계 가능 건", body["total"], 2)


# ---------------------------------------------------------------- 실행


def _isolate(tmp: Path) -> None:
    from ..api import applications as applications_api
    from ..api import documents as documents_api
    from ..api import files as files_api

    models.engine = create_engine(
        f"sqlite:///{tmp / 'p8.db'}", connect_args={"check_same_thread": False}
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

    tmp = Path(tempfile.mkdtemp(prefix="p8-scenarios-"))
    _isolate(tmp)

    try:
        with TestClient(app) as client:
            seed(client)
            test_income_band_not_flipped(client)
            test_scores_withheld(client)
            test_guards(client)
            test_public_fields(client)
            test_schedule_and_meta(client)
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

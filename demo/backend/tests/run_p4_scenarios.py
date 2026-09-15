"""P4 게이트 검증 스크립트 — 담당자 화면.

저장소 루트에서:
    PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python -m demo.backend.tests.run_p4_scenarios

확인하는 것:
  1. **다운로드 0회** — 심사 1건을 여는 전 구간에서 `Content-Disposition`이 전부
     `inline`이고 `attachment`가 0건이다. 소스 코드에도 다운로드 경로가 없다.
  2. 심사표 항목의 `source_document_id` + `bbox`로 좌측 하이라이트 대상이 실제로
     해석된다 (존재하는 서류 · 좌표 4점 · 인라인으로 열림)
  3. 필터(사업·시군·읍면동·처리상태·AI판정·신청일)가 각각 결과 건수를 바꾼다
  4. 역할 3종(읍면동/시군/도)에서 보이는 목록과 가능한 액션이 다르다
  5. 승인/반려/보류 + 메모가 DB에 기록된다
  6. 시군별 정원 대비 진행률·커트라인 배지가 계산된다

pytest 없이 돌아간다. DB와 업로드 저장소는 임시 경로에 만들고 끝나면 지운다 —
`demo/storage`·`demo/demo.db`(시연용 데이터)를 절대 건드리지 않는다.
"""

import json
import shutil
import tempfile
from pathlib import Path

from sqlmodel import create_engine, select

from .. import models
from ..rules.programs import DOUBLE_SAVINGS
from ..rules.roles import ROLE_CITY, ROLE_PROVINCE, ROLE_TOWN

SAMPLES = Path(__file__).resolve().parents[2] / "fixtures" / "samples"
DEMO_ROOT = Path(__file__).resolve().parents[2]

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


BASE_FORM1 = {
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

#: 서식2 자가진단 8문항 — 제외대상 조회 결과 칸이 이 답변을 읽는다.
SELF_CHECK_ANSWERS = {str(i): "예" for i in range(1, 9)}

S2_UPLOADS = {
    "resident_abstract": "S2_주민등록초본_적합.pdf",
    "nhis_payment": "S2_건강보험료납부확인서_적합.pdf",
    "nhis_qualification": "S2_건강보험자격확인서_적합.pdf",
    "nhis_acquisition_loss": "S2_건강보험자격득실확인서_적합.pdf",
    "work_proof": "S2_4대보험가입내역확인서_적합.pdf",
}


def _create(client, *, name: str, address: str, transfer_in: dict, uploads: dict) -> int:
    app_id = client.post(
        "/api/applications", json={"program_code": DOUBLE_SAVINGS}
    ).json()["id"]
    form1 = {**BASE_FORM1, "name": name, "address": address, "transferIn": transfer_in}
    client.patch(f"/api/applications/{app_id}", json={"form1": form1})
    client.post(
        f"/api/applications/{app_id}/self-check", json={"answers": SELF_CHECK_ANSWERS}
    )
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


def seed(client) -> dict[str, int]:
    """4건을 만든다. 시군·읍면동·AI판정·점수가 모두 갈리게 배치한다."""
    fail_uploads = {**S2_UPLOADS, "nhis_payment": "S7_건강보험료납부확인서_소득초과.pdf"}
    review_uploads = {**S2_UPLOADS, "resident_abstract": "S8_주민등록초본_저해상도.pdf"}
    return {
        # 전주 효자동 · PASS · 99점
        "A": _create(
            client,
            name="홍길동",
            address="전북특별자치도 전주시 완산구 효자동 123",
            transfer_in={"y": "2020", "m": "11", "d": "20"},
            uploads=S2_UPLOADS,
        ),
        # 전주 인후동 · FAIL(중위소득 153%)
        "B": _create(
            client,
            name="김영희",
            address="전북특별자치도 전주시 덕진구 인후동 45",
            transfer_in={"y": "2020", "m": "11", "d": "20"},
            uploads=fail_uploads,
        ),
        # 군산 나운동 · NEEDS_REVIEW(판독 신뢰도 0.6)
        "C": _create(
            client,
            name="박철수",
            address="전북특별자치도 군산시 나운동 7",
            transfer_in={"y": "2020", "m": "11", "d": "20"},
            uploads=review_uploads,
        ),
        # 전주 효자동 · PASS · A와 동점(전입일은 초본 판독값이 우선이라 같은 값이 된다)
        "D": _create(
            client,
            name="이민수",
            address="전북특별자치도 전주시 완산구 효자동 999",
            transfer_in={"y": "2025", "m": "6", "d": "1"},
            uploads=S2_UPLOADS,
        ),
    }


# ---------------------------------------------------------------- 다운로드 감시


class Recorder:
    """심사 세션 동안 오간 응답 헤더를 전부 기록한다.

    "다운로드 0회"는 말로 선언할 게 아니라 헤더로 증명해야 한다. 이 기록이
    S9 시연의 브라우저 네트워크 탭을 대신한다.
    """

    def __init__(self, client) -> None:
        self.client = client
        self.log: list[dict[str, str]] = []

    def get(self, path: str, **kw):
        res = self.client.get(path, **kw)
        self._record("GET", path, res)
        return res

    def post(self, path: str, **kw):
        res = self.client.post(path, **kw)
        self._record("POST", path, res)
        return res

    def _record(self, method: str, path: str, res) -> None:
        self.log.append(
            {
                "method": method,
                "path": path,
                "status": str(res.status_code),
                "content_disposition": res.headers.get("content-disposition", ""),
                "content_type": res.headers.get("content-type", ""),
            }
        )

    @property
    def dispositions(self) -> list[str]:
        return [e["content_disposition"] for e in self.log if e["content_disposition"]]

    @property
    def attachments(self) -> list[dict[str, str]]:
        return [
            e for e in self.log if "attachment" in e["content_disposition"].lower()
        ]


# ---------------------------------------------------------------- 1. 목록·필터


def test_list_and_filters(client, ids) -> None:
    print("\n[1] 접수 목록 — 컬럼·정렬·필터 (R4.4)")

    everything = client.get("/api/officer/applications", params={"role": ROLE_PROVINCE}).json()
    check("도·청년허브는 14개 시군 전체", everything["total"], 4)
    check(
        "컬럼",
        [c["key"] for c in everything["columns"]],
        [
            "application_no",
            "name",
            "region",
            "ai_status",
            "total_score",
            "missing_count",
            "submitted_at",
            "decision",
        ],
    )
    first = everything["rows"][0]
    check("기본 정렬은 점수순 — 1등이 99점", first["total_score"], 99)
    check("1등 성명", first["name"], "홍길동")
    check("시군 내 순위", first["rank"], 1)
    check("AI판정 표기", first["ai_status_label"], "적합")
    check("미비서류 0건", first["missing_count"], 0)
    check("처리상태 초기값", first["decision_label"], "미처리")

    by_no = {r["application_no"]: r for r in everything["rows"]}
    review_row = next(r for r in everything["rows"] if r["ai_status"] == "NEEDS_REVIEW")
    check("S8 저신뢰 건은 확인필요로 담당자 큐에 도착", review_row["name"], "박철수")
    check("확인필요 건의 미비서류 수", review_row["missing_count"], 1)
    check("신청번호가 키로 쓰인다", len(by_no), 4)

    def total(**params) -> int:
        return client.get(
            "/api/officer/applications", params={"role": ROLE_PROVINCE, **params}
        ).json()["total"]

    print("\n  -- 필터마다 건수가 실제로 바뀌는가")
    check("필터 없음", total(), 4)
    check("사업 = 두배적금", total(program=DOUBLE_SAVINGS), 4)
    check("사업 = 취업지원패키지", total(program="job_package"), 0)
    check("AI판정 = 적합", total(ai_status="PASS"), 2)
    check("AI판정 = 부적합", total(ai_status="FAIL"), 1)
    check("AI판정 = 확인필요", total(ai_status="NEEDS_REVIEW"), 1)
    check("처리상태 = 미처리", total(status="pending"), 4)
    check("처리상태 = 승인", total(status="approve"), 0)
    check("신청일 >= 2026-01-01", total(submitted_from="2026-01-01"), 4)
    check("신청일 <= 2000-01-01", total(submitted_to="2000-01-01"), 0)
    check("시군 = 전주시 (시군 역할)", client.get(
        "/api/officer/applications", params={"role": ROLE_CITY, "region": "전주시"}
    ).json()["total"], 3)
    check("시군 = 군산시 (시군 역할)", client.get(
        "/api/officer/applications", params={"role": ROLE_CITY, "region": "군산시"}
    ).json()["total"], 1)
    check("시군 = 진안군 (접수 0건)", client.get(
        "/api/officer/applications", params={"role": ROLE_CITY, "region": "진안군"}
    ).json()["total"], 0)
    check("잘못된 처리상태 → 400", client.get(
        "/api/officer/applications", params={"role": ROLE_PROVINCE, "status": "무엇"}
    ).status_code, 400)

    print("\n  -- 정렬")
    scored = client.get(
        "/api/officer/applications", params={"role": ROLE_PROVINCE, "sort": "score"}
    ).json()["rows"]
    check(
        "점수순(두배적금)",
        [r["total_score"] for r in scored],
        sorted([r["total_score"] for r in scored], reverse=True),
    )
    received = client.get(
        "/api/officer/applications", params={"role": ROLE_PROVINCE, "sort": "submitted"}
    ).json()["rows"]
    check("접수순(취업패키지)", [r["name"] for r in received], ["홍길동", "김영희", "박철수", "이민수"])
    check("정렬이 실제로 다름", [r["name"] for r in scored] != [r["name"] for r in received], True)

    print("\n  -- 페이징")
    paged = client.get(
        "/api/officer/applications", params={"role": ROLE_PROVINCE, "page_size": 2}
    ).json()
    check("페이지 크기", len(paged["rows"]), 2)
    check("페이지 수", paged["page_count"], 2)
    page2 = client.get(
        "/api/officer/applications",
        params={"role": ROLE_PROVINCE, "page_size": 2, "page": 2},
    ).json()
    check("2페이지", len(page2["rows"]), 2)
    check(
        "겹치지 않음",
        set(r["application_no"] for r in paged["rows"])
        & set(r["application_no"] for r in page2["rows"]),
        set(),
    )

    del ids


# ---------------------------------------------------------------- 2. 정원 배지


def test_quota(client) -> None:
    print("\n[2] 시군별 정원 대비 진행률 배지 (전주 550 … 진안 15)")
    body = client.get("/api/officer/applications", params={"role": ROLE_PROVINCE}).json()
    quota = {q["region"]: q for q in body["quota"]}
    check("14개 시군 전체", len(quota), 14)
    check("전주시 정원", quota["전주시"]["quota"], 550)
    check("진안군 정원", quota["진안군"]["quota"], 15)
    check("전주시 120% 선발 상한", quota["전주시"]["limit_120"], 660)
    check("전주시 접수", quota["전주시"]["applied"], 3)
    check("군산시 접수", quota["군산시"]["applied"], 1)
    check("정원 미달이라 커트라인 없음", quota["전주시"]["cutoff_120"], None)
    check("선정 건수 초기값", quota["전주시"]["selected"], 0)

    city = client.get(
        "/api/officer/applications", params={"role": ROLE_CITY, "region": "군산시"}
    ).json()
    check("시군 역할은 관할 시군 배지만", [q["region"] for q in city["quota"]], ["군산시"])


# ---------------------------------------------------------------- 3. 역할 3종


def test_roles(client, ids) -> None:
    print("\n[3] 역할 전환 — 보이는 범위와 가능한 액션이 달라진다 (R4.5)")

    roles = client.get("/api/officer/roles").json()
    check("역할 3종", [r["name"] for r in roles], ["읍·면·동", "시군", "도·청년허브센터"])

    town = client.get(
        "/api/officer/applications",
        params={"role": ROLE_TOWN, "region": "전주시", "town": "효자동"},
    ).json()
    city = client.get(
        "/api/officer/applications", params={"role": ROLE_CITY, "region": "전주시"}
    ).json()
    province = client.get(
        "/api/officer/applications", params={"role": ROLE_PROVINCE}
    ).json()

    check("읍면동(전주 효자동)이 보는 건수", town["total"], 2)
    check("시군(전주시)이 보는 건수", city["total"], 3)
    check("도가 보는 건수", province["total"], 4)
    check("범위가 실제로 좁아진다", town["total"] < city["total"] < province["total"], True)

    check("읍면동 범위 표기", town["role"]["scope"], "관할 읍·면·동 접수 건")
    check("선택된 읍면동", town["scope"]["town"], "효자동")
    check("전주시 읍면동 후보", sorted(town["scope"]["towns"]), ["인후동", "효자동"])

    other_town = client.get(
        "/api/officer/applications",
        params={"role": ROLE_TOWN, "region": "전주시", "town": "인후동"},
    ).json()
    check("다른 읍면동으로 바꾸면 목록이 바뀐다", other_town["total"], 1)
    check("인후동 담당자가 보는 건", other_town["rows"][0]["name"], "김영희")

    print("\n  -- 같은 승인이라도 역할마다 뜻이 다르다")
    check(
        "읍면동 승인 버튼",
        next(a["label"] for a in town["role"]["actions"] if a["key"] == "approve"),
        "구비서류 완비 확인",
    )
    check(
        "시군 승인 버튼",
        next(a["label"] for a in city["role"]["actions"] if a["key"] == "approve"),
        "1차 선발 (배정인원 120%)",
    )
    check(
        "도 승인 버튼",
        next(a["label"] for a in province["role"]["actions"] if a["key"] == "approve"),
        "최종 선정 (100%)",
    )
    check("읍면동 선발 비율 없음", town["role"]["quota_ratio"], None)
    check("시군 120%", city["role"]["quota_ratio"], 1.2)
    check("도 100%", province["role"]["quota_ratio"], 1.0)

    print("\n  -- 일괄 처리 권한")
    check("읍면동은 일괄 처리 불가", town["role"]["can_bulk"], False)
    check("시군은 일괄 처리 가능", city["role"]["can_bulk"], True)
    blocked = client.post(
        "/api/officer/applications/decisions",
        json={
            "role": ROLE_TOWN,
            "decision": "approve",
            "memo": "",
            "application_ids": [ids["A"]],
        },
    )
    check("읍면동 일괄 처리 시도 → 403", blocked.status_code, 403)
    check("잘못된 역할 → 400", client.get(
        "/api/officer/applications", params={"role": "무엇"}
    ).status_code, 400)


# ---------------------------------------------------------------- 4. 심사 상세


def test_review_detail(rec, ids) -> None:
    print("\n[4] 분할 심사 뷰 — 판독 결과·심사표·자격요건·제외대상 (R4.2)")
    app_id = ids["A"]
    detail = rec.get(f"/api/officer/applications/{app_id}", params={"role": ROLE_CITY}).json()

    check("신청번호", detail["application_no"].startswith("DS-2026-"), True)
    check("성명", detail["name"], "홍길동")
    check("시군", detail["region"], "전주시")
    check("읍면동", detail["town"], "효자동")
    check("AI 최종 판정", detail["ai"]["final_status"], "PASS")
    check("1단계", detail["ai"]["stage1_status"], "PASS")
    check("2단계", detail["ai"]["stage2_status"], "PASS")
    check("권고 조치", detail["ai"]["recommended_action"], "자동 승인")

    print("\n  -- 서류 탭 (좌측 뷰어)")
    check("서류 5건", len(detail["documents"]), 5)
    check(
        "탭 라벨",
        [d["label"] for d in detail["documents"]][:2],
        ["주민등록초본", "2025년 건강보험료 납부확인서"],
    )
    check(
        "모든 서류에 인라인 스트리밍 주소",
        all(d["file_url"].startswith("/api/files/") for d in detail["documents"]),
        True,
    )
    check("판독 계층 노출", detail["documents"][0]["ocr_tier"], "fixture")

    print("\n  -- 심사표 (서식6)")
    sheet = detail["score_sheet"]
    check("총점", sheet["total"], 99)
    check("만점", sheet["max_total"], 100)
    check("항목 4개", [i["key"] for i in sheet["items"]], ["income", "residence", "work", "age"])
    check("배점", [i["max_score"] for i in sheet["items"]], [40, 25, 25, 10])
    check("(데모 추정치) 라벨", any("데모 추정치" in n for n in sheet["notes"]), True)
    for item in sheet["items"]:
        check_true(f"{item['label']} 근거 문장", item["basis"])
    print(f"         근거 예시: {sheet['items'][1]['basis']}")

    print("\n  -- 자격요건 체크리스트 / 제외대상 조회 결과")
    check("자격요건 4항목", [e["key"] for e in detail["eligibility"]], ["residence", "age", "work", "income"])
    check("모두 충족", all(e["ok"] for e in detail["eligibility"]), True)
    check_true("자격요건 근거가 심사표 근거와 같은 문장", detail["eligibility"][1]["basis"])
    check("제외대상 조회 5줄", len(detail["exclusions"]), 5)
    check("제외 해당 없음", all(x["ok"] for x in detail["exclusions"]), True)
    check(
        "자가진단 6번이 근거로 들어옴",
        detail["exclusions"][0]["label"].startswith("자가진단 6."),
        True,
    )

    print("\n  -- 부적합 건의 사유 (S7)")
    fail_detail = rec.get(
        f"/api/officer/applications/{ids['B']}", params={"role": ROLE_CITY}
    ).json()
    check("AI 최종 판정", fail_detail["ai"]["final_status"], "FAIL")
    check(
        "사유 코드",
        [r["code"] for r in fail_detail["ai"]["reasons"]],
        ["INCOME_OVER_THRESHOLD"],
    )
    check("권고 조치", fail_detail["ai"]["recommended_action"], "반려/보완요청 안내")
    income_row = next(e for e in fail_detail["eligibility"] if e["key"] == "income")
    check("소득 요건 불충족", income_row["ok"], False)
    check("중위소득 %", fail_detail["score_sheet"]["income_percent"], 153.0)

    return detail


# ------------------------------------------------- 5. 근거 클릭 → 원본 하이라이트


BBOX_KEYS = ("page", "x0", "y0", "x1", "y1")


def test_bbox_link(rec, detail) -> None:
    print("\n[5] 심사표 항목 클릭 → 좌측 원본 스크롤 + bbox 하이라이트 (R4.3)")
    documents = {d["document_id"]: d for d in detail["documents"]}
    items = {i["key"]: i for i in detail["score_sheet"]["items"]}

    linked = [i for i in items.values() if i["source_document_id"]]
    check("근거 서류가 연결된 항목 수", len(linked), 4)

    for item in linked:
        doc = documents.get(item["source_document_id"])
        check(f"{item['key']} → 실재하는 서류", doc is not None, True)
        if doc is None:
            continue
        check(f"{item['key']} 근거 서류 종류", item["source_doc"], doc["detected_doc_type"])
        check(f"{item['key']} 탭 슬롯", item["source_slot_key"], doc["slot_key"])
        check(f"{item['key']} 뷰어 주소", item["source_file_url"], doc["file_url"])

    with_bbox = [i for i in linked if i["bbox"]]
    check("좌표가 붙은 항목 수", len(with_bbox), 2)
    for item in with_bbox:
        box = item["bbox"]
        check(f"{item['key']} 좌표 4점 + 페이지", sorted(box), sorted(BBOX_KEYS))
        check(f"{item['key']} 좌표가 유효한 사각형", box["x0"] < box["x1"] and box["y0"] < box["y1"], True)
        # 하이라이트하려면 원본을 브라우저에서 열 수 있어야 한다.
        res = rec.get(item["source_file_url"])
        check(f"{item['key']} 원본 열림", res.status_code, 200)
        check(f"{item['key']} 인라인", res.headers["content-disposition"].startswith("inline"), True)

    print("\n  -- 판독 필드 좌표도 함께 온다 (서류 탭에서 통째 하이라이트)")
    abstract = next(d for d in detail["documents"] if d["slot_key"] == "resident_abstract")
    check("초본 bbox 키", sorted(abstract["bboxes"]), ["발급일", "성명", "전입일"])
    check("전입일 판독값", abstract["extracted"]["전입일"], "2020-11-20")


# ---------------------------------------------------------------- 6. 다운로드 0회


def test_inline_only(rec, detail) -> None:
    print("\n[6] 다운로드 0회 — 심사 세션 전 구간 헤더 검사 (R4.1) ★ P4 게이트")

    for doc in detail["documents"]:
        res = rec.get(doc["file_url"])
        check(f"{doc['label']} 응답", res.status_code, 200)
        check(f"{doc['label']} MIME", res.headers["content-type"], "application/pdf")
        check(
            f"{doc['label']} Content-Disposition",
            res.headers["content-disposition"].split(";")[0],
            "inline",
        )

    check("없는 서류 → 404", rec.get("/api/files/999999").status_code, 404)

    print(f"\n  -- 기록된 응답 {len(rec.log)}건 (심사 1건을 여는 동안 오간 전부)")
    check("attachment 응답 건수", len(rec.attachments), 0)
    check(
        "Content-Disposition이 붙은 응답은 전부 inline",
        all(d.lower().startswith("inline") for d in rec.dispositions),
        True,
    )
    check("원본 스트리밍 호출 건수", sum(1 for e in rec.log if e["path"].startswith("/api/files/")), 8)
    for entry in rec.log:
        if entry["content_disposition"]:
            print(f"         {entry['path']} → {entry['content_disposition']}")


#: 다운로드 경로를 만들 수 있는 토큰. 소스에 하나라도 있으면 P4 게이트 실패다.
FORBIDDEN_TOKENS = ("attachment", "download")

#: 이 검사 자체가 토큰을 들고 있으므로 스스로는 제외한다. P6 시연 검증 스크립트도
#: 같은 이유로 제외한다 — "attachment 응답이 0건"을 세려면 그 낱말을 들고 있어야 한다.
SCAN_SKIP = {"run_p4_scenarios.py", "run_p6_scenarios.py"}


def _scan(root: Path, suffixes: tuple[str, ...]) -> list[str]:
    hits: list[str] = []
    for path in sorted(root.rglob("*")):
        if path.suffix not in suffixes or path.name in SCAN_SKIP:
            continue
        if "node_modules" in path.parts or "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8").lower()
        for token in FORBIDDEN_TOKENS:
            if token in text:
                hits.append(f"{path.relative_to(DEMO_ROOT)}:{token}")
    return hits


def test_no_download_in_source() -> None:
    print("\n[7] 소스에 다운로드 경로가 없다 — 정적 검사")
    backend = _scan(DEMO_ROOT / "backend", (".py",))
    frontend = _scan(DEMO_ROOT / "frontend" / "src", (".ts", ".tsx", ".css"))
    check("백엔드 attachment/download 사용", backend, [])
    check("프론트 attachment/download 사용", frontend, [])


# ---------------------------------------------------------------- 7. 담당자 판단


def test_decisions(client, ids) -> None:
    print("\n[8] 승인 / 반려 / 보류 + 담당자 메모")

    town_memo = "구비서류 5종 확인. 초본 주소이력 포함 확인함."
    res = client.post(
        f"/api/officer/applications/{ids['A']}/decision",
        json={"role": ROLE_TOWN, "decision": "approve", "memo": town_memo},
    )
    check("읍면동 승인", res.status_code, 200)
    check("읍면동 승인 표기", res.json()["label"], "서류 완비 확인")

    with models.get_session() as s:
        review = s.exec(
            select(models.Review).where(models.Review.application_id == ids["A"])
        ).first()
        app = s.get(models.Application, ids["A"])
    assert review is not None and app is not None
    check("DB 역할", review.officer_role, ROLE_TOWN)
    check("DB 판단", review.officer_decision, "approve")
    check("DB 메모", review.officer_memo, town_memo)
    check_true("DB 처리시각", review.decided_at)
    check("신청 상태", app.status, "decided")

    rejected = client.post(
        f"/api/officer/applications/{ids['B']}/decision",
        json={"role": ROLE_CITY, "decision": "reject", "memo": "중위소득 140% 초과."},
    )
    check("시군 반려", rejected.json()["label"], "반려")

    held = client.post(
        f"/api/officer/applications/{ids['C']}/decision",
        json={"role": ROLE_PROVINCE, "decision": "hold", "memo": "판독 신뢰도 낮음 — 육안 확인 필요."},
    )
    check("도 보류", held.json()["label"], "보류")
    with models.get_session() as s:
        held_app = s.get(models.Application, ids["C"])
    check("보류는 결정 완료가 아니다", held_app.status if held_app else None, "reviewing")

    print("\n  -- 처리 후 목록이 실제로 바뀐다")
    def total(**params) -> int:
        return client.get(
            "/api/officer/applications", params={"role": ROLE_PROVINCE, **params}
        ).json()["total"]

    check("미처리", total(status="pending"), 1)
    check("승인", total(status="approve"), 1)
    check("반려", total(status="reject"), 1)
    check("보류", total(status="hold"), 1)

    quota = {
        q["region"]: q
        for q in client.get(
            "/api/officer/applications", params={"role": ROLE_PROVINCE}
        ).json()["quota"]
    }
    check("전주시 선정 건수 반영", quota["전주시"]["selected"], 1)

    print("\n  -- 일괄 처리 (시군·도만)")
    bulk = client.post(
        "/api/officer/applications/decisions",
        json={
            "role": ROLE_PROVINCE,
            "decision": "approve",
            "memo": "2차 검증 완료.",
            "application_ids": [ids["D"]],
        },
    )
    check("일괄 승인", bulk.json()["processed"], 1)
    check("일괄 승인 표기", bulk.json()["results"][0]["label"], "최종 선정")
    check("승인 건수", total(status="approve"), 2)

    detail = client.get(
        f"/api/officer/applications/{ids['A']}", params={"role": ROLE_TOWN}
    ).json()
    check("상세 화면에 판단 이력", detail["decision"]["memo"], town_memo)
    check("상세 화면 역할 표기", detail["decision"]["officer_role"], ROLE_TOWN)


# ---------------------------------------------------------------- 8. 점수 비노출


def test_applicant_still_blind(client, ids) -> None:
    print("\n[9] 담당자 화면이 생겨도 신청자 마이페이지에는 여전히 점수가 없다 (R5.3)")
    status = client.get(f"/api/applications/{ids['A']}/status").json()
    raw = json.dumps(status, ensure_ascii=False)
    check("총점 숫자(99) 없음", "99" in raw, False)
    check("점수 키 없음", any(k in status for k in ("total_score", "score_json", "score_sheet")), False)
    check("담당자 메모 없음", "구비서류 5종" in raw, False)


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
        f"sqlite:///{tmp / 'p4.db'}", connect_args={"check_same_thread": False}
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

    tmp = Path(tempfile.mkdtemp(prefix="p4-scenarios-"))
    _isolate(tmp)

    try:
        with TestClient(app) as client:
            ids = seed(client)
            test_list_and_filters(client, ids)
            test_quota(client)
            test_roles(client, ids)

            # 여기서부터가 S9 — "심사 1건을 여는 동안 다운로드 0회"의 구간이다.
            rec = Recorder(client)
            rec.get("/api/officer/roles")
            rec.get("/api/officer/applications", params={"role": ROLE_CITY, "region": "전주시"})
            detail = test_review_detail(rec, ids)
            test_bbox_link(rec, detail)
            test_inline_only(rec, detail)
            test_no_download_in_source()

            test_decisions(client, ids)
            test_applicant_still_blind(client, ids)
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

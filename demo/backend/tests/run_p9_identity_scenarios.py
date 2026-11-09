"""P9 검증 — 본인인증(데모)과 서류 본인 대조.

저장소 루트에서:
    python -m demo.backend.tests.run_p9_identity_scenarios

확인하는 것:
  1. 본인인증: 서약·서명 없으면 거절, 인증 후 재인증 불가, 연락처는 가려서 저장
  2. 신청서 성명·생년월일 잠금: API로 바꿔도 서버가 인증 값으로 되돌린다
  3. 본인 초본 → 적합 / 타인 초본 → 부적합(본인 서류 아님) / 동명이인(생년월일 다름) → 부적합
  4. 판독이 불확실해 다르게 읽힌 경우 → 부적합이 아니라 확인필요 (남의 서류로 단정 금지)
  5. 신청자 안내에 서류 속 남의 이름을 되읊지 않는다
  6. 시연용 샘플(가상 인물 '홍길동')은 대조하지 않는다 — 본인 초본 + 샘플로 시연 가능
  7. 본인인증 없이 올리면 대조하지 않는다 (기존 동작 유지)
  8. 담당자 화면에 본인인증·서약 여부가 보이고, 연락처는 나가지 않는다

HTTP 경로(업로드 → 판정 → 제출 → 담당자 상세)를 그대로 탄다. 이미지 초본은
가짜 OCR 엔진이 실측 레이아웃의 가상 인물 '김전북 / 1999-01-01'을 돌려준다.
DB·저장소는 임시 폴더로 격리하고 끝나면 지운다. 실제 개인정보는 쓰지 않는다.
"""

import shutil
import tempfile
from pathlib import Path

from . import run_p4_scenarios as p4
from .run_p8_localocr_scenarios import (
    fake_abstract_words,
    install_fake_ocr,
    make_image_pdf,
)

SIG = "data:image/png;base64,iVBORw0KGgo="

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


def new_app(client) -> int:
    return client.post("/api/applications", json={"program_code": p4.DOUBLE_SAVINGS}).json()["id"]


def identify(client, app_id: int, name: str, birth: str, **over):
    body = {"name": name, "birth": birth, "phone": "010-1234-5678", "pledge": True,
            "signature_data_url": SIG, **over}
    return client.post(f"/api/applications/{app_id}/identity", json=body)


def upload_abstract(client, app_id: int, tmp: Path, words: list, stem: str) -> dict:
    pdf = make_image_pdf(tmp / f"{stem}.pdf")
    install_fake_ocr(words)
    with pdf.open("rb") as fh:
        return client.post(
            f"/api/applications/{app_id}/documents",
            files={"file": (pdf.name, fh, "application/pdf")},
            data={"slot_key": "resident_abstract", "declared_issue_date": "2026-11-10"},
        ).json()


def codes(doc: dict) -> list[str]:
    return [f["code"] for f in doc.get("findings", [])]


# ------------------------------------------------------------------ 시나리오

def test_identity_api(client) -> None:
    print("\n[1] 본인인증 API")
    app_id = new_app(client)
    check("서약 없이 → 400", identify(client, app_id, "김전북", "1999-01-01", pledge=False).status_code, 400)
    check("서명 없이 → 400", identify(client, app_id, "김전북", "1999-01-01", signature_data_url="").status_code, 400)
    check("미래 생년월일 → 400", identify(client, app_id, "김전북", "2999-01-01").status_code, 400)
    r = identify(client, app_id, "김 전북", "1999-01-01")
    check("인증 → 200", r.status_code, 200)
    ident = r.json()["identity"]
    check("성명 공백 정리", ident["name"], "김전북")
    check("연락처 가림", ident["phone"], "010-****-5678")
    check("방식", ident["method"], "demo")
    check("재인증 → 409", identify(client, app_id, "이익산", "1998-05-05").status_code, 409)

    print("\n[2] 신청서 성명·생년월일 잠금")
    patched = client.patch(
        f"/api/applications/{app_id}",
        json={"form1": {"name": "이익산", "birth": {"y": "1998", "m": "5", "d": "5"}, "phone": "010"}},
    ).json()["form1_json"]
    check("성명은 인증 값 유지", patched["name"], "김전북")
    check("생년월일은 인증 값 유지", patched["birth"], {"y": "1999", "m": "1", "d": "1"})
    check("다른 칸은 그대로 저장", patched["phone"], "010")


def test_matching(client, tmp: Path) -> None:
    print("\n[3] 서류 본인 대조")
    own = new_app(client)
    identify(client, own, "김전북", "1999-01-01")
    doc = upload_abstract(client, own, tmp, fake_abstract_words(), "본인초본")
    check("본인 초본 → 판정", doc["status"], "PASS")

    other = new_app(client)
    identify(client, other, "이익산", "1998-05-05")
    doc = upload_abstract(client, other, tmp, fake_abstract_words(), "타인초본")
    check("타인 초본 → 판정", doc["status"], "FAIL")
    check_true("사유: IDENTITY_MISMATCH", "IDENTITY_MISMATCH" in codes(doc))
    msg = " ".join(f["message"] + f["how_to_fix"] for f in doc["findings"])
    check_true("안내에 서류 속 이름 미노출", "김전북" not in msg)
    check_true("안내에 다른 항목 명시", "성명·생년월일" in msg)

    namesake = new_app(client)
    identify(client, namesake, "김전북", "2000-02-02")
    doc = upload_abstract(client, namesake, tmp, fake_abstract_words(), "동명이인")
    check("동명이인(생년월일 다름) → 판정", doc["status"], "FAIL")
    check_true("다른 항목은 생년월일만", any("생년월일이(가)" in f["message"] for f in doc["findings"]))

    print("\n[4] 판독 불확실 → 확인필요")
    shaky = new_app(client)
    identify(client, shaky, "김전북", "1999-01-01")
    words = fake_abstract_words()
    for page in (1, 2):  # 3쪽 중 2쪽 성명을 OCR이 잘못 읽음 → 다수결도 틀림, 쪽 간 불일치
        for w in words[page]:
            if w.text == "김전북":
                w.text = "김전복"
    doc = upload_abstract(client, shaky, tmp, words, "오독초본")
    check("판정", doc["status"], "NEEDS_REVIEW")
    check_true("사유: IDENTITY_UNCERTAIN", "IDENTITY_UNCERTAIN" in codes(doc))
    check_true("본인 서류 아님으로 단정 안 함", "IDENTITY_MISMATCH" not in codes(doc))


def test_samples_and_no_identity(client, tmp: Path) -> None:
    print("\n[5] 시연용 샘플은 대조 제외")
    app_id = new_app(client)
    identify(client, app_id, "조테스트", "2001-01-01")
    client.put(f"/api/applications/{app_id}/doc-context",
               json={"work_category": "직장가입자", "workplace_count": 1})
    for slot, filename in p4.S2_UPLOADS.items():
        if slot == "resident_abstract":
            continue
        with (p4.SAMPLES / filename).open("rb") as fh:
            doc = client.post(
                f"/api/applications/{app_id}/documents",
                files={"file": (filename, fh, "application/pdf")},
                data={"slot_key": slot, "declared_issue_date": "2026-03-05"},
            ).json()
        check(f"{slot} (홍길동 샘플) → 판정", doc["status"], "PASS")

    print("\n[6] 본인인증 없이 → 대조하지 않음")
    bare = new_app(client)
    doc = upload_abstract(client, bare, tmp, fake_abstract_words(), "미인증")
    check("판정", doc["status"], "PASS")


def test_officer_view(client, tmp: Path) -> None:
    print("\n[7] 담당자 화면")
    app_id = new_app(client)
    identify(client, app_id, "김전북", "1999-01-01")
    form1 = {**p4.BASE_FORM1, "name": "김전북"}
    client.patch(f"/api/applications/{app_id}", json={"form1": form1})
    client.post(f"/api/applications/{app_id}/self-check", json={"answers": p4.SELF_CHECK_ANSWERS})
    client.post(f"/api/applications/{app_id}/consents", json={"consents": p4.CONSENTS})
    client.put(f"/api/applications/{app_id}/doc-context",
               json={"work_category": "직장가입자", "workplace_count": 1})
    upload_abstract(client, app_id, tmp, fake_abstract_words(), "제출초본")
    for slot, filename in p4.S2_UPLOADS.items():
        if slot == "resident_abstract":
            continue
        with (p4.SAMPLES / filename).open("rb") as fh:
            client.post(f"/api/applications/{app_id}/documents",
                        files={"file": (filename, fh, "application/pdf")},
                        data={"slot_key": slot, "declared_issue_date": "2026-03-05"})
    check("제출", client.post(f"/api/applications/{app_id}/submit").status_code, 200)
    detail = client.get(f"/api/officer/applications/{app_id}", params={"role": p4.ROLE_CITY}).json()
    ident = detail["identity"]
    check("본인인증 여부", ident["verified"], True)
    check("서약 서명", ident["pledge_signed"], True)
    check_true("연락처 미노출", "phone" not in ident and "010" not in str(ident))


def main() -> int:
    from fastapi.testclient import TestClient

    from ..main import app

    tmp = Path(tempfile.mkdtemp(prefix="p9-identity-"))
    p4._isolate(tmp)
    try:
        with TestClient(app) as client:
            test_identity_api(client)
            test_matching(client, tmp)
            test_samples_and_no_identity(client, tmp)
            test_officer_view(client, tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n통과 {_passed} / 실패 {len(_failed)}")
    if _failed:
        for name in _failed:
            print(f"  - {name}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

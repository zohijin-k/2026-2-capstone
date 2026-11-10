"""P9 검증 — 본인인증(데모)과 서류 본인 대조.

저장소 루트에서:
    python -m demo.backend.tests.run_p9_identity_scenarios

확인하는 것:
  1. 본인인증: 서약·서명 없으면 거절, 인증 후 재인증 불가, 연락처는 가려서 저장
  2. 신청서 성명·생년월일 잠금: API로 바꿔도 서버가 인증 값으로 되돌린다
  3. 본인 초본 → 적합 / 타인 초본 → 부적합(본인 서류 아님) / 동명이인(생년월일 다름) → 부적합
  4. 판독이 불확실해 다르게 읽힌 경우 → 부적합이 아니라 확인필요 (남의 서류로 단정 금지)
  5. 신청자 안내에 서류 속 남의 이름을 되읊지 않는다
  6. NHIS 시연 샘플도 본인인증 정보와 대조한다. 이름이 다르면 관계 확인이 필요하다.
  7. 본인인증 없이 올리면 대조하지 않는다 (기존 동작 유지)
  8. 담당자 화면에 본인인증·서약 여부가 보이고, 연락처는 나가지 않는다
  9. 서약 서명은 직접 서명(PNG) 또는 서명 파일(PNG·JPG·PDF, 5MB 이하)로 받는다
 10. 신청자도 자기가 올린 서류를 다시 열어 볼 수 있다 (인라인 주소, 저장 경로 없음)

HTTP 경로(업로드 → 판정 → 제출 → 담당자 상세)를 그대로 탄다. 이미지 초본은
가짜 OCR 엔진이 실측 레이아웃의 가상 인물 '김전북 / 1999-01-01'을 돌려준다.
DB·저장소는 임시 폴더로 격리하고 끝나면 지운다. 실제 개인정보는 쓰지 않는다.
"""

import base64
import json
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


def upload_fixture(client, app_id: int, tmp: Path, stem: str, slot: str) -> dict:
    from ...fixtures.make_samples import make

    pdf = make(stem, tmp)
    with pdf.open("rb") as fh:
        return client.post(
            f"/api/applications/{app_id}/documents",
            files={"file": (pdf.name, fh, "application/pdf")},
            data={"slot_key": slot, "declared_issue_date": "2026-03-05"},
        ).json()


def check_applicant_name_hidden(client, app_id: int, parent_name: str, uploads: list[dict]) -> None:
    responses: list[object] = list(uploads)
    for path in (
        f"/api/applications/{app_id}/documents",
        f"/api/applications/{app_id}/required-documents",
        f"/api/applications/{app_id}/final-check",
    ):
        response = client.get(path)
        check(f"신청자 응답 {path.rsplit('/', 1)[-1]} → 200", response.status_code, 200)
        responses.append(response.json())
    serialized = json.dumps(responses, ensure_ascii=False)
    check_true("신청자 API 전체 응답에 가입자 이름 미노출", parent_name not in serialized)


def test_nhis_dependent_reconciliation(client, tmp: Path) -> None:
    print("\n[9] 건강보험 가입자(부모) 명의 대조와 신청자 응답")
    parent = "김보호자"

    own = new_app(client)
    identify(client, own, "홍길동", "1999-01-01")
    own_doc = upload_fixture(
        client, own, tmp, "S2_건강보험료납부확인서_적합", "nhis_payment"
    )
    check("본인 명의 납부확인서 → 통과", own_doc["status"], "PASS")

    dependent = new_app(client)
    identify(client, dependent, "김전북", "1999-01-01")
    first = upload_fixture(
        client, dependent, tmp, "P9_건강보험료납부확인서_부모명의", "nhis_payment"
    )
    check("부모 명의 납부확인서만 → 확인필요", first["status"], "NEEDS_REVIEW")
    second = upload_fixture(
        client, dependent, tmp, "P9_건강보험자격확인서_부모명의_본인포함", "nhis_qualification"
    )
    docs = client.get(f"/api/applications/{dependent}/documents").json()
    by_slot = {doc["slot_key"]: doc for doc in docs}
    check("같은 가입자 + 가구원 본인 → 납부확인서 통과",
          by_slot["nhis_payment"]["status"], "PASS")
    check("같은 가입자 + 가구원 본인 → 자격확인서 통과",
          by_slot["nhis_qualification"]["status"], "PASS")
    check_true("피부양자 판정 사유 코드 기록",
               "NHIS_DEPENDENT_INSURED_PERSON" in codes(by_slot["nhis_payment"]))
    check_applicant_name_hidden(client, dependent, parent, [first, second])

    # 담당자 상세에는 같은 근거와 가입자 이름이 보인다.
    form1 = {**p4.BASE_FORM1, "name": "김전북", "birth": {"y": "1999", "m": "1", "d": "1"}}
    client.patch(f"/api/applications/{dependent}", json={"form1": form1})
    client.post(f"/api/applications/{dependent}/self-check", json={"answers": p4.SELF_CHECK_ANSWERS})
    client.post(f"/api/applications/{dependent}/consents", json={"consents": p4.CONSENTS})
    client.put(f"/api/applications/{dependent}/doc-context",
               json={"work_category": "직장가입자", "workplace_count": 1})
    for slot, stem in (
        ("resident_abstract", "S2_주민등록초본_적합"),
        ("nhis_acquisition_loss", "S2_건강보험자격득실확인서_적합"),
        ("work_proof", "S2_4대보험가입내역확인서_적합"),
    ):
        upload_fixture(client, dependent, tmp, stem, slot)
    check("부모 명의 서류가 포함된 신청 제출", client.post(
        f"/api/applications/{dependent}/submit").status_code, 200)
    officer = client.get(
        f"/api/officer/applications/{dependent}", params={"role": p4.ROLE_CITY}
    ).json()
    officer_docs = {doc["slot_key"]: doc for doc in officer["documents"]}
    officer_finding = next(
        finding for finding in officer_docs["nhis_payment"]["findings"]
        if finding["code"] == "NHIS_DEPENDENT_INSURED_PERSON"
    )
    check_true("담당자 근거에 가입자 이름 포함",
               parent in officer_finding.get("detail", ""))
    check_true("담당자 근거에 두 서류·가구원 대조 포함",
               "납부확인서" in officer_finding["detail"]
               and "자격확인서" in officer_finding["detail"]
               and "가구원 목록" in officer_finding["detail"])

    missing_qual = new_app(client)
    identify(client, missing_qual, "김전북", "1999-01-01")
    miss_upload = upload_fixture(
        client, missing_qual, tmp, "P9_건강보험료납부확인서_부모명의", "nhis_payment"
    )
    check("자격확인서 없음 → 확인필요", miss_upload["status"], "NEEDS_REVIEW")
    check_applicant_name_hidden(client, missing_qual, parent, [miss_upload])

    absent_member = new_app(client)
    identify(client, absent_member, "김전북", "1999-01-01")
    absent_payment = upload_fixture(
        client, absent_member, tmp, "P9_건강보험료납부확인서_부모명의", "nhis_payment"
    )
    absent_qualification = upload_fixture(
        client, absent_member, tmp, "P9_건강보험자격확인서_부모명의_본인미포함", "nhis_qualification"
    )
    absent_docs = client.get(f"/api/applications/{absent_member}/documents").json()
    check("가구원 목록에 본인 없음 → 확인필요",
          absent_docs[0]["status"], "NEEDS_REVIEW")
    check_applicant_name_hidden(
        client, absent_member, parent, [absent_payment, absent_qualification]
    )

    reverse = new_app(client)
    identify(client, reverse, "김전북", "1999-01-01")
    reverse_qualification = upload_fixture(
        client, reverse, tmp, "P9_건강보험자격확인서_부모명의_본인포함", "nhis_qualification"
    )
    check("자격확인서 먼저 → 확인필요", reverse_qualification["status"], "NEEDS_REVIEW")
    reverse_payment = upload_fixture(
        client, reverse, tmp, "P9_건강보험료납부확인서_부모명의", "nhis_payment"
    )
    reverse_docs = client.get(f"/api/applications/{reverse}/documents").json()
    reverse_by_slot = {doc["slot_key"]: doc for doc in reverse_docs}
    check("납부확인서 나중 → 두 서류 모두 통과",
          [reverse_by_slot[k]["status"] for k in ("nhis_payment", "nhis_qualification")],
          ["PASS", "PASS"])
    deleted = client.delete(
        f"/api/applications/{reverse}/documents/{reverse_by_slot['nhis_qualification']['document_id']}"
    )
    check("자격확인서 삭제", deleted.status_code, 200)
    remaining = client.get(f"/api/applications/{reverse}/documents").json()
    check("자격확인서 삭제 뒤 납부확인서 → 확인필요",
          remaining[0]["status"], "NEEDS_REVIEW")
    check_applicant_name_hidden(
        client, reverse, parent,
        [reverse_qualification, reverse_payment, deleted.json()],
    )

    parent_abstract = new_app(client)
    identify(client, parent_abstract, "이익산", "1998-05-05")
    abstract = upload_abstract(client, parent_abstract, tmp, fake_abstract_words(), "부모명의초본")
    check("부모 명의 초본 → 기존과 같은 부적합", abstract["status"], "FAIL")


# ------------------------------------------------------------------ 시나리오

def test_identity_api(client) -> None:
    print("\n[1] 본인인증 API")
    app_id = new_app(client)
    check("서약 없이 → 400", identify(client, app_id, "김전북", "1999-01-01", pledge=False).status_code, 400)
    check("서명 없이 → 400", identify(client, app_id, "김전북", "1999-01-01", signature_data_url="").status_code, 400)
    check("미래 생년월일 → 400", identify(client, app_id, "김전북", "2999-01-01").status_code, 400)
    invalid_phone_message = "010으로 시작하는 휴대폰 번호를 입력해 주세요."
    invalid_prefix = identify(client, app_id, "김전북", "1999-01-01", phone="011-1234-5678")
    check("011 시작 → 400", invalid_prefix.status_code, 400)
    check("011 시작 오류 안내", invalid_prefix.json()["detail"], invalid_phone_message)
    check("011-123-4567 (10자리) → 400",
          identify(client, app_id, "김전북", "1999-01-01", phone="011-123-4567").status_code, 400)
    check("010 10자리 → 400",
          identify(client, app_id, "김전북", "1999-01-01", phone="0101234567").status_code, 400)
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

    print("\n[3-1] 올린 서류 다시 보기")
    check_true("신청자 응답에 파일 주소", doc["file_url"].startswith("/api/files/"))
    res = client.get(doc["file_url"])
    check("파일 열기", res.status_code, 200)
    check_true("인라인으로만 연다", res.headers["content-disposition"].startswith("inline"))
    listed = client.get(f"/api/applications/{own}/documents").json()
    rows = listed["documents"] if isinstance(listed, dict) else listed
    check_true("목록에도 같은 주소", any(d["file_url"] == doc["file_url"] for d in rows))

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
    print("\n[5] 시연용 건강보험 서류 — 인증된 본인 명의는 통과")
    app_id = new_app(client)
    identify(client, app_id, "홍길동", "1999-01-01")
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

    print("\n[5-1] 본인인증 이름이 시연 샘플과 다름 — 샘플도 본인 대조 대상")
    different = new_app(client)
    identify(client, different, "김전북", "1999-01-01")
    payment = upload_fixture(
        client, different, tmp, "S2_건강보험료납부확인서_적합", "nhis_payment"
    )
    qualification = upload_fixture(
        client, different, tmp, "S2_건강보험자격확인서_적합", "nhis_qualification"
    )
    sample_docs = client.get(f"/api/applications/{different}/documents").json()
    check("시연 샘플의 명의가 인증 정보와 다르면 확인필요",
          [doc["status"] for doc in sample_docs], ["NEEDS_REVIEW", "NEEDS_REVIEW"])
    check_applicant_name_hidden(client, different, "홍길동", [payment, qualification])

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
    check("서약 방식", ident["pledge_kind"], "electronic")
    check_true("연락처 미노출", "phone" not in ident and "010" not in str(ident))


def test_signature_upload(client) -> None:
    print("\n[8] 서명 파일 올리기")

    def data_url(mime: str, raw: bytes) -> str:
        return f"data:{mime};base64,{base64.b64encode(raw).decode()}"

    def attempt(kind: str, url: str) -> int:
        app_id = new_app(client)
        return identify(client, app_id, "김전북", "1999-01-01",
                        signature_kind=kind, signature_data_url=url).status_code

    check("PNG 파일 → 200", attempt("uploaded", data_url("image/png", b"\x89PNG\r\n")), 200)
    check("JPG 파일 → 200", attempt("uploaded", data_url("image/jpeg", b"\xff\xd8\xff")), 200)
    check("PDF 파일 → 200", attempt("uploaded", data_url("application/pdf", b"%PDF-1.7")), 200)
    check("텍스트 파일 → 400", attempt("uploaded", data_url("text/plain", b"sign")), 400)
    check("5MB 초과 → 400", attempt("uploaded", data_url("image/png", b"0" * (5 * 1024 * 1024 + 1))), 400)
    check("깨진 base64 → 400", attempt("uploaded", "data:image/png;base64,@@@"), 400)
    check("직접 서명인데 JPG → 400", attempt("electronic", data_url("image/jpeg", b"\xff\xd8")), 400)
    check("알 수 없는 방식 → 400", attempt("stamp", data_url("image/png", b"\x89PNG")), 400)

    app_id = new_app(client)
    r = identify(client, app_id, "김전북", "1999-01-01", signature_kind="uploaded",
                 signature_data_url=data_url("application/pdf", b"%PDF-1.7"))
    check("저장된 서명 방식", r.json()["identity"]["pledge_signature_kind"], "uploaded")
    check_true("PDF는 .pdf로 저장", r.json()["identity"]["pledge_signature_path"].endswith(".pdf"))


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
            test_nhis_dependent_reconciliation(client, tmp)
            test_officer_view(client, tmp)
            test_signature_upload(client)
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

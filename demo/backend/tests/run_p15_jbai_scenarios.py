"""P15 검증 — 전북AI OCR을 기본 판독으로 연결.

저장소 루트에서:
    python -m demo.backend.tests.run_p15_jbai_scenarios

확인하는 것 (실제 네트워크 없음 — engine_v2 `jbai_ocr._http_post`를 가짜로 바꿔 끼운다):
  (가) 전송 이미지가 JPEG(시작 바이트 FF D8, data:image/jpeg)다 — 이미지 PDF·사진 모두
  (나) 키·허용값이 없거나, 판독기 없는 서류 칸이거나, 텍스트 PDF면 전북AI를 부르지 않는다
  (다) 401·429·시간 초과(·응답 형식 오류·연결 끊김·판독기 실패)면 LocalOcr로 넘어가고 대체 사유가 남는다
  (라) 응답의 주민번호 뒷자리가 DB·저장 파일·로그·API 응답 어디에도 없다
  (마) 같은 파일을 두 번 올리면 전북AI 호출은 한 번이다
  (바) 합성 응답으로 초본·납부확인서·자격득실의 데모 필드가 LocalOcr 경로와 같은 이름으로 나온다
  (사) 판독 엔진·대체 사유는 담당자 화면에만 있고 신청자 응답에는 없다

합성 응답은 engine_v2/tests/fixtures/jbai_synthetic(가상 인물 '김가상')을 쓰고, 주민번호도
가상 값(990101-2718281)을 끼워 넣는다. 실서류·개인정보는 쓰지 않는다. 임시 파일은 끝나면 지운다.
"""

import base64
import io
import json
import logging
import os
import re
import shutil
import tempfile
import urllib.error
from datetime import date
from pathlib import Path

from . import run_p4_scenarios as p4
from .run_p8_localocr_scenarios import (
    fake_abstract_words,
    install_fake_ocr,
    make_image_pdf,
    make_text_pdf,
)
from .run_p9_identity_scenarios import identify, new_app
from ..engine_adapter import apply_runtime_overrides
from ..ocr import read_document
from ..ocr import jbai as jbai_adapter
from ..ocr.localocr import ENGINE_ENV
from ..rules.doc_check import check_document
from ..rules.doc_types import DocType
from ..rules.identity import Identity, compare
from ..rules.programs import DOUBLE_SAVINGS, PROGRAMS
from ..rules.required_docs import ApplicantDocInput, WorkCategory, build_checklist, find_slot

REPO = Path(__file__).resolve().parents[3]
SYNTHETIC = REPO / "engine_v2" / "tests" / "fixtures" / "jbai_synthetic"
JPEG_PREFIX = "data:image/jpeg;base64,"
FAKE_KEY = "fake-jbai-test-key"
#: 가상 주민번호. 성별 자리(2)만 남고 뒤 6자리(718281)는 어디에도 남으면 안 된다.
FAKE_RRN = "990101-2718281"
RRN_TAIL = "718281"
ENV_KEYS = ("JBAI_API_KEY", "JBAI_ALLOW_REAL_DOCS", "JBAI_BASE_URL", "JBAI_TIMEOUT_SEC", ENGINE_ENV)

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


# ------------------------------------------------------------- 가짜 전북AI

class FakeJbai:
    """engine_v2 `jbai_ocr._http_post` 자리에 끼우는 가짜 서버. 요청을 기록하고 정해진 응답을 준다."""

    def __init__(self) -> None:
        self.requests: list[dict] = []
        self.mode: object = "ok"
        self.pages: list[dict] = []
        self._page = 0

    def serve(self, pages: list[dict], mode: object = "ok") -> None:
        self.pages, self.mode, self._page = pages, mode, 0

    @property
    def calls(self) -> int:
        return len(self.requests)

    def __call__(self, request, timeout):
        payload = json.loads(request.data)
        parts = payload["messages"][0]["content"]
        task = parts[0]["text"]
        url = parts[1]["image_url"]["url"]
        head, _, data = url.partition(",")
        self.requests.append({"task": task, "prefix": head + ",", "image": base64.b64decode(data),
                              "timeout": timeout})
        if self.mode == "timeout":
            raise TimeoutError("timed out")
        if self.mode == "network":
            raise urllib.error.URLError("network is unreachable")
        if self.mode == "badjson":
            return 200, b"<html>gateway</html>", {}
        if isinstance(self.mode, int):
            return self.mode, b"", {"Retry-After": "0"}
        page = self.pages[min(self._page, len(self.pages) - 1)]
        content = page["ocr_content"] if task == "OCR:" else page["table_content"]
        if task != "OCR:":
            self._page += 1
        return 200, json.dumps({"choices": [{"message": {"content": content}}]}).encode(), {}


FAKE = FakeJbai()


def enable() -> None:
    os.environ["JBAI_API_KEY"] = FAKE_KEY
    os.environ["JBAI_ALLOW_REAL_DOCS"] = "true"


def disable() -> None:
    os.environ.pop("JBAI_API_KEY", None)
    os.environ.pop("JBAI_ALLOW_REAL_DOCS", None)


def synthetic(kind: str, *, with_rrn: bool = False) -> list[dict]:
    pages = json.loads((SYNTHETIC / f"{kind}.json").read_text(encoding="utf-8"))["pages"]
    if with_rrn:
        first = dict(pages[0])
        first["ocr_content"] = first["ocr_content"].replace(
            "성명 김가상", f"성명 김가상\n주민등록번호 {FAKE_RRN}", 1)
        first["table_content"] = ("<fcel>주민등록번호 " + FAKE_RRN.replace("-", "") +
                                  "<lcel><lcel><lcel><lcel><nl>" + first["table_content"])
        pages = [first, *pages[1:]]
    return pages


def scaled_words(pages_fn) -> list:
    """engine_v2 테스트 좌표(1000×1400)를 이미지 PDF 크기로 늘린다 (P8과 같은 방식)."""
    words = pages_fn()[0][1].words
    sx, sy = 2066 / 1000, 2923 / 1400
    return [type(w)(w.text, w.confidence, (w.bbox_px[0] * sx, w.bbox_px[1] * sy,
                                           w.bbox_px[2] * sx, w.bbox_px[3] * sy)) for w in words]


def slot(key: str):
    items = build_checklist(PROGRAMS[DOUBLE_SAVINGS], ApplicantDocInput(work_category=WorkCategory.EMPLOYEE))
    return find_slot(items, key)


def jpeg_ok(requests: list[dict]) -> bool:
    from PIL import Image

    for item in requests:
        if item["prefix"] != JPEG_PREFIX or item["image"][:2] != b"\xff\xd8":
            return False
        with Image.open(io.BytesIO(item["image"])) as image:
            if image.format != "JPEG" or image.mode != "RGB":
                return False
    return bool(requests)


# ------------------------------------------------------------------ 시나리오

def test_same_fields_as_localocr(tmp: Path) -> None:
    print("\n[바] 합성 응답 → LocalOcr 경로와 같은 데모 필드 이름")
    from engine_v2.tests.test_nhis_extractors import acquisition_pages, payment_pages

    identity = Identity("김가상", date(1999, 1, 1))
    cases = [
        ("초본", "resident_abstract", DocType.RESIDENT_ABSTRACT, "resident_abstract",
         lambda: (install_fake_ocr(fake_abstract_words()), 3)),
        ("납부확인서", "nhis_payment", DocType.NHIS_PAYMENT, "nhis_payment",
         lambda: (install_fake_ocr([scaled_words(payment_pages)]), 1)),
        ("자격득실", "nhis_acquisition_loss", DocType.NHIS_ACQUISITION_LOSS, "nhis_acquisition_loss",
         lambda: (install_fake_ocr([scaled_words(acquisition_pages)]), 1)),
    ]
    #: 같은 추출기가 데이터에 따라서만 내는 진단·보조 필드 (합성 납부확인서에만 장기요양 열이 있다).
    optional = {"판독검증실패", "판독경고", "과거주소미포함의심", "장기요양보험료", "월별장기요양보험료"}
    for label, kind, doc_type, slot_key, prepare_local in cases:
        disable()
        _, local_pages = prepare_local()
        local = read_document(str(make_image_pdf(tmp / f"local_{kind}.pdf", pages=local_pages)), doc_type)

        enable()
        pages = synthetic(kind)
        FAKE.serve(pages)
        before = FAKE.calls
        ocr = read_document(str(make_image_pdf(tmp / f"remote_{kind}.pdf", pages=len(pages))), doc_type)
        sent = FAKE.requests[before:]

        check(f"{label} 판독 계층", (ocr.tier, ocr.engine), ("jbai", "jbai"))
        check(f"{label} 대체 없음", ocr.fallback_reason, "")
        check(f"{label} LocalOcr 계층(비교 기준)", local.tier, "localocr")
        check(f"{label} 서류 종류 = LocalOcr", ocr.detected_doc_type, local.detected_doc_type)
        check(f"{label} 쪽마다 OCR·표 인식 2회", len(sent), 2 * len(pages))
        check_true(f"(가) {label} 전송 이미지 JPEG(FF D8 · data:image/jpeg · RGB)", jpeg_ok(sent))
        check(f"{label} 요청 시간 제한(기본 60초)", {item["timeout"] for item in sent}, {60.0})
        check_true(f"{label} LocalOcr 필드 이름이 모두 있음", set(local.fields) <= set(ocr.fields))
        check(f"{label} 더 있는 필드는 보조 필드뿐", sorted(set(ocr.fields) - set(local.fields) - optional), [])
        if doc_type is not DocType.NHIS_PAYMENT:
            check(f"{label} 필드 이름 동일", sorted(ocr.fields), sorted(local.fields))
        check(f"{label} 발급일", ocr.issue_date, date(2026, 11, 10))
        check(f"{label} 성명·생년월일", (ocr.fields.get("성명"), ocr.fields.get("생년월일")),
              ("김가상", "1999-01-01"))
        check(f"{label} 본인 대조(rules.identity)", compare(identity, ocr.fields), (["성명", "생년월일"], []))
        check(f"{label} 좌표 없음(임시 격자 좌표를 내보내지 않음)", ocr.bboxes, {})
        check(f"{label} 화질 = LocalOcr 기준", ocr.image_quality, local.image_quality)
        result = check_document(slot(slot_key), ocr, date(2026, 11, 10), identity=identity)
        print(f"         판정 {result.status} {result.codes}")
        if doc_type is DocType.NHIS_PAYMENT:
            check_true(f"{label} 판정 규칙 동작(부적합 아님)", result.status in {"PASS", "NEEDS_REVIEW"})
        else:
            check(f"{label} 판정 규칙 그대로 적합", result.status, "PASS")
        if doc_type is DocType.RESIDENT_ABSTRACT:
            check("초본 전입일·주소변동내역", (ocr.fields.get("전입일"), ocr.fields.get("주소변동내역")),
                  ("2020-04-10", "포함"))


def test_photo_upload_is_jpeg(tmp: Path) -> None:
    print("\n[가] 사진 업로드(투명 PNG)도 RGB JPEG로 바꿔 보낸다")
    from PIL import Image

    photo = tmp / "초본사진.png"
    Image.new("RGBA", (1240, 1754), (255, 255, 255, 0)).save(photo)
    enable()
    FAKE.serve(synthetic("resident_abstract")[:1])
    before = FAKE.calls
    read_document(str(photo), DocType.RESIDENT_ABSTRACT)
    sent = FAKE.requests[before:]
    check("사진 1장 → OCR·표 인식 2회", len(sent), 2)
    check_true("사진도 JPEG(FF D8 · data:image/jpeg · RGB)", jpeg_ok(sent))


def test_not_called(tmp: Path) -> None:
    print("\n[나] 전북AI를 부르지 않는 경우 → 지금처럼 LocalOcr부터")
    image_pdf = make_image_pdf(tmp / "초본_호출없음.pdf")
    FAKE.serve(synthetic("resident_abstract"))
    for label, env in (
        ("키·허용값 모두 없음", {}),
        ("키만 있음", {"JBAI_API_KEY": FAKE_KEY}),
        ("허용값만 참", {"JBAI_ALLOW_REAL_DOCS": "true"}),
        ("허용값 false", {"JBAI_API_KEY": FAKE_KEY, "JBAI_ALLOW_REAL_DOCS": "false"}),
    ):
        disable()
        os.environ.update(env)
        install_fake_ocr(fake_abstract_words())
        before = FAKE.calls
        ocr = read_document(str(image_pdf), DocType.RESIDENT_ABSTRACT)
        check(f"{label} → 전북AI 호출 0회", FAKE.calls - before, 0)
        check(f"{label} → LocalOcr가 읽음", (ocr.tier, ocr.engine, ocr.fallback_reason), ("localocr", "fake", ""))

    enable()
    for label, expected in (("판독기 없는 칸(자격확인서)", DocType.NHIS_QUALIFICATION),
                            ("판독기 없는 칸(행정정보동의서)", DocType.ADMIN_INFO_CONSENT),
                            ("기대 칸 없음", None)):
        install_fake_ocr([])
        before = FAKE.calls
        read_document(str(make_image_pdf(tmp / "기타서류.pdf", pages=1)), expected)
        check(f"{label} → 전북AI 호출 0회", FAKE.calls - before, 0)

    text_pdf = make_text_pdf(tmp / "초본_텍스트.pdf", [
        "주민등록표 (초본)", "발급일 2026년 11월 10일", "성명 김전북", "생년월일 1999-01-01",
    ])
    before = FAKE.calls
    ocr = read_document(str(text_pdf), DocType.RESIDENT_ABSTRACT)
    check("텍스트 PDF → 전북AI 호출 0회", FAKE.calls - before, 0)
    check("텍스트 PDF → 지금처럼 PdfText", (ocr.tier, ocr.engine), ("pdftext", "pdftext"))


def test_fallback(tmp: Path) -> None:
    print("\n[다] 전북AI 오류 → LocalOcr 대체, 대체 사유 기록")
    from engine_v2.extractors import jbai_text
    from engine_v2.pipeline import jbai_ocr

    enable()
    pdf = make_image_pdf(tmp / "초본_대체.pdf")
    cases = [
        ("인증 401", 401, "전북AI 인증 실패(401)", 1),
        ("재시도 후에도 429", 429, "전북AI 요청 제한(429, 재시도 후에도)", jbai_ocr.MAX_ATTEMPTS),
        ("시간 초과", "timeout", "전북AI 응답 시간 초과", 1),
        ("응답 형식 오류", "badjson", "전북AI 응답 형식 오류", 1),
        ("네트워크 끊김", "network", "전북AI 연결 실패", 1),
        ("서버 오류 503", 503, "전북AI 요청 실패(HTTP 503)", 1),
    ]
    for label, mode, reason, attempts in cases:
        jbai_adapter.clear_cache()
        FAKE.serve(synthetic("resident_abstract"), mode)
        install_fake_ocr(fake_abstract_words())
        before = FAKE.calls
        ocr = read_document(str(pdf), DocType.RESIDENT_ABSTRACT)
        check(f"{label} → 전북AI 시도 {attempts}회 후 중단", FAKE.calls - before, attempts)
        check(f"{label} → LocalOcr로 대체", (ocr.tier, ocr.engine), ("localocr", "fake"))
        check(f"{label} → 대체 사유", ocr.fallback_reason, reason)
        check(f"{label} → 로컬 판독값 그대로", ocr.fields.get("성명"), "김전북")

    jbai_adapter.clear_cache()
    FAKE.serve(synthetic("resident_abstract"))
    original = jbai_text.extract
    jbai_text.extract = lambda *_a, **_k: (_ for _ in ()).throw(ValueError("synthetic reader failure"))
    try:
        install_fake_ocr(fake_abstract_words())
        ocr = read_document(str(pdf), DocType.RESIDENT_ABSTRACT)
    finally:
        jbai_text.extract = original
    check("판독기 실패 → LocalOcr 대체·사유", (ocr.tier, ocr.fallback_reason), ("localocr", "전북AI 판독기 오류"))

    jbai_adapter.clear_cache()
    FAKE.serve([{"ocr_content": "안내문\n자료 목록", "table_content": ""}] * 3)
    install_fake_ocr(fake_abstract_words())
    ocr = read_document(str(pdf), DocType.RESIDENT_ABSTRACT)
    check("서류 종류 판별 실패 → LocalOcr 대체·사유",
          (ocr.tier, ocr.fallback_reason), ("localocr", "전북AI 판독 결과로 서류 종류를 알아보지 못함"))

    jbai_adapter.clear_cache()
    noisy_pages = synthetic("resident_abstract")
    noisy_pages[1]["table_content"] = "<fcel>" + "漢" * 5000 + "<nl>"
    FAKE.serve(noisy_pages)
    install_fake_ocr(fake_abstract_words())
    ocr = read_document(str(pdf), DocType.RESIDENT_ABSTRACT)
    check("잡음 많아도 판독 검증 통과 → 전북AI 유지", (ocr.tier, ocr.engine, ocr.fallback_reason), ("jbai", "jbai", ""))
    check("검증 통과한 잡음은 담당자 참고 메모로", ocr.quality_note, "잡음 있음")

    jbai_adapter.clear_cache()
    FAKE.serve(noisy_pages)
    from engine_v2.extractors import jbai_text
    original_noisy_extract = jbai_text.extract
    def noisy_empty_history(document, doc_type):
        from dataclasses import replace
        return replace(original_noisy_extract(document, doc_type), history=[])
    jbai_text.extract = noisy_empty_history
    try:
        install_fake_ocr(fake_abstract_words())
        noisy_failure = read_document(str(pdf), DocType.RESIDENT_ABSTRACT)
    finally:
        jbai_text.extract = original_noisy_extract
    check("잡음 많고 검증 실패 → LocalOcr 대체", (noisy_failure.tier, noisy_failure.engine), ("localocr", "fake"))
    check("검증 실패 대체 사유에 환각 쪽 표시", noisy_failure.fallback_reason,
          "전북AI 판독 검증 실패: 주소 이력 없음 · 환각 의심 2·3쪽")

    print("  -- 판독 검증 실패 → LocalOcr로 대체, 이유를 담당자 메타데이터에 기록")
    jbai_adapter.clear_cache()
    FAKE.serve(synthetic("resident_abstract"))
    from engine_v2.extractors import jbai_text
    original = jbai_text.extract
    def empty_history(document, doc_type):
        from dataclasses import replace
        extracted = original(document, doc_type)
        return replace(extracted, history=[])
    jbai_text.extract = empty_history
    try:
        install_fake_ocr(fake_abstract_words())
        result = read_document(str(pdf), DocType.RESIDENT_ABSTRACT)
    finally:
        jbai_text.extract = original
    check("주소 이력 0건 → 로컬 OCR 결과 사용", (result.tier, result.engine), ("localocr", "fake"))
    check("품질 fallback 사유 기록", result.fallback_reason, "전북AI 판독 검증 실패: 주소 이력 없음")

    print("  -- LocalOcr를 사용할 수 없음 → JBAI 결과를 확인필요 수준으로 낮춤")
    jbai_adapter.clear_cache()
    FAKE.serve(synthetic("resident_abstract"))
    jbai_text.extract = empty_history
    try:
        install_fake_ocr([])
        result = read_document(str(pdf), DocType.RESIDENT_ABSTRACT)
    finally:
        jbai_text.extract = original
    check("로컬 OCR 미사용 시 JBAI 결과 유지", (result.tier, result.engine), ("jbai", "jbai"))
    check("로컬 OCR 미사용 시 신뢰도 낮춤", result.confidence, 0.4)
    check("로컬 OCR 미사용 시 사유 보존", result.fallback_reason, "전북AI 판독 검증 실패: 주소 이력 없음")
    review = check_document(slot("resident_abstract"), result, date(2026, 11, 10),
                            identity=Identity("김가상", date(1999, 1, 1)))
    check("품질 실패 결과는 확인필요", review.status, "NEEDS_REVIEW")

    os.environ["JBAI_TIMEOUT_SEC"] = "5"
    jbai_adapter.clear_cache()
    FAKE.serve(synthetic("resident_abstract"), "timeout")
    install_fake_ocr(fake_abstract_words())
    before = FAKE.calls
    read_document(str(pdf), DocType.RESIDENT_ABSTRACT)
    check("JBAI_TIMEOUT_SEC 반영", FAKE.requests[before]["timeout"], 5.0)
    os.environ.pop("JBAI_TIMEOUT_SEC", None)


class _Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def _scan_files(root: Path, needle: bytes) -> list[str]:
    return [str(path.relative_to(root)) for path in root.rglob("*")
            if path.is_file() and needle in path.read_bytes()]


def test_api_privacy_cache_and_views(client, tmp: Path) -> None:
    print("\n[라·마·사] 업로드 API — 주민번호 뒷자리 폐기, 결과 캐시, 담당자 전용 엔진 정보")
    from ..api.common import list_documents
    from ..api.officer import _document_view
    from engine_v2.extractors import jbai_text

    capture = _Capture()
    root = logging.getLogger()
    old_level = root.level
    root.addHandler(capture)
    root.setLevel(logging.DEBUG)
    try:
        enable()
        jbai_adapter.clear_cache()
        app_id = new_app(client)
        identify(client, app_id, "김가상", "1999-01-01")
        pages = synthetic("resident_abstract", with_rrn=True)
        pdf = make_image_pdf(tmp / "제출초본.pdf", pages=len(pages))

        responses = []
        counts = []
        for _ in range(2):
            FAKE.serve(pages)
            install_fake_ocr(fake_abstract_words())
            before = FAKE.calls
            with pdf.open("rb") as fh:
                res = client.post(f"/api/applications/{app_id}/documents",
                                  files={"file": (pdf.name, fh, "application/pdf")},
                                  data={"slot_key": "resident_abstract", "declared_issue_date": "2026-11-10"})
            responses.append(res)
            counts.append(FAKE.calls - before)
        check("(마) 같은 파일 두 번 → 전북AI 호출 횟수", counts, [2 * len(pages), 0])
        check("업로드 응답", [r.status_code for r in responses], [200, 200])
        doc = responses[-1].json()
        check("판정(캐시 결과로도 같은 규칙)", doc["status"], "PASS")

        listed = client.get(f"/api/applications/{app_id}/documents").text
        checklist = client.get(f"/api/applications/{app_id}/required-documents").text
        rows = list_documents(app_id)
        officer = [_document_view(row, {"resident_abstract": "주민등록초본"}) for row in rows]
        officer_text = json.dumps(officer, ensure_ascii=False)
        stored = json.dumps([(row.ocr_json, row.findings_json) for row in rows], ensure_ascii=False)
        cache_text = repr(list(jbai_adapter._cache.values()))

        print("  -- (라) 주민번호 뒷자리")
        check_true("가린 번호는 판독 결과에 남음(성별 자리까지)", "990101-2******" in cache_text)
        for label, text in (("신청자 업로드 응답", "".join(r.text for r in responses)),
                            ("신청자 서류 목록", listed), ("신청자 체크리스트", checklist),
                            ("담당자 화면", officer_text), ("DB 행(ocr_json·findings)", stored),
                            ("메모리 캐시", cache_text)):
            check_true(f"{label}에 뒷자리 없음", RRN_TAIL not in text)
        check("임시 저장소·DB 파일에 뒷자리 없음", _scan_files(tmp, RRN_TAIL.encode()), [])
        messages = [f"{record.name} {record.getMessage()}" for record in capture.records]
        log_text = "\n".join(messages)
        check_true("로그에 뒷자리 없음", RRN_TAIL not in log_text)
        check_true("로그에 키 없음", FAKE_KEY not in log_text)
        check_true("로그에 이미지·본문 없음", "base64" not in log_text and "김가상" not in log_text)
        jbai_lines = [r.getMessage() for r in capture.records if r.name == jbai_adapter.log.name]
        check("전북AI 로그 = 엔진·상태·쪽 수·소요 시간뿐",
              [bool(re.fullmatch(r"engine=jbai status=\S+ pages=\d+ elapsed_ms=\d+", m)) for m in jbai_lines],
              [True] * len(jbai_lines))
        check_true("전북AI 성공·캐시 로그가 남음",
                   any("status=200 pages=2" in m for m in jbai_lines)
                   and any("status=cache" in m for m in jbai_lines))

        print("  -- (사) 판독 엔진·품질 메모·대체 사유는 담당자 화면에만")
        hidden = {"ocr_tier", "ocr_engine", "ocr_fallback_reason", "ocr_quality_note", "engine", "fallback_reason", "quality_note", "tier"}
        check("신청자 응답 키에 엔진·대체 정보 없음", sorted(hidden & set(doc)), [])
        check_true("신청자 응답 본문에 엔진 이름 없음",
                   all("jbai" not in r.text and "전북AI" not in r.text for r in responses))
        check("담당자 화면 엔진", (officer[0]["ocr_tier"], officer[0]["ocr_engine"]), ("jbai", "jbai"))
        check("담당자 화면 대체 사유(없음)", officer[0]["ocr_fallback_reason"], None)

        print("  -- 검증 통과 잡음은 담당자 판독 엔진 줄에 참고 표시")
        jbai_adapter.clear_cache()
        note_app = new_app(client)
        identify(client, note_app, "김전북", "1999-01-01")
        note_pages = synthetic("resident_abstract", with_rrn=True)
        note_pages[1]["table_content"] = "<fcel>" + "漢" * 5000 + "<nl>"
        FAKE.serve(note_pages)
        install_fake_ocr(fake_abstract_words())
        note_pdf = make_image_pdf(tmp / "잡음포함_검증통과.pdf", pages=len(note_pages))
        with note_pdf.open("rb") as fh:
            note_response = client.post(f"/api/applications/{note_app}/documents",
                files={"file": (note_pdf.name, fh, "application/pdf")},
                data={"slot_key": "resident_abstract", "declared_issue_date": "2026-11-10"})
        check("잡음 포함 업로드는 유지", note_response.status_code, 200)
        check_true("신청자 응답에 품질 메모 없음", "quality_note" not in note_response.text and "잡음 있음" not in note_response.text)
        note_view = _document_view(list_documents(note_app)[0], {"resident_abstract": "주민등록초본"})
        check("담당자 판독 엔진 참고 표시", (note_view["ocr_engine"], note_view["ocr_quality_note"]), ("jbai", "잡음 있음"))

        print("  -- 품질 검증 fallback 사유는 담당자 판독 엔진 줄에 표시")
        jbai_adapter.clear_cache()
        quality_app = new_app(client)
        identify(client, quality_app, "김전북", "1999-01-01")
        FAKE.serve(pages)
        original_extract = jbai_text.extract
        def quality_failure(document, doc_type):
            from dataclasses import replace
            return replace(original_extract(document, doc_type), history=[])
        jbai_text.extract = quality_failure
        try:
            install_fake_ocr(fake_abstract_words())
            with pdf.open("rb") as fh:
                response = client.post(f"/api/applications/{quality_app}/documents",
                    files={"file": (pdf.name, fh, "application/pdf")},
                    data={"slot_key": "resident_abstract", "declared_issue_date": "2026-11-10"})
        finally:
            jbai_text.extract = original_extract
        check("품질 실패 업로드는 이어짐", response.status_code, 200)
        quality_view = _document_view(list_documents(quality_app)[0], {"resident_abstract": "주민등록초본"})
        check("판독 엔진 줄에 품질 대체 사유", quality_view["ocr_fallback_reason"],
              "전북AI 판독 검증 실패: 주소 이력 없음")

        print("  -- (다) 시연 중 네트워크가 끊겨도 업로드는 끝난다")
        jbai_adapter.clear_cache()
        other = new_app(client)
        identify(client, other, "김전북", "1999-01-01")
        FAKE.serve(pages, "network")
        install_fake_ocr(fake_abstract_words())
        with pdf.open("rb") as fh:
            res = client.post(f"/api/applications/{other}/documents",
                              files={"file": (pdf.name, fh, "application/pdf")},
                              data={"slot_key": "resident_abstract", "declared_issue_date": "2026-11-10"})
        check("네트워크 끊김에도 업로드 응답", res.status_code, 200)
        check("로컬 OCR 결과로 판정", res.json()["status"], "PASS")
        check_true("신청자 응답에 대체 사유 없음", "전북AI" not in res.text and "jbai" not in res.text)
        view = _document_view(list_documents(other)[0], {"resident_abstract": "주민등록초본"})
        check("담당자 화면 엔진·대체 사유",
              (view["ocr_engine"], view["ocr_fallback_reason"]), ("fake", "전북AI 연결 실패"))
    finally:
        root.removeHandler(capture)
        root.setLevel(old_level)


def main() -> int:
    from fastapi.testclient import TestClient

    from engine_v2.pipeline import jbai_ocr

    from ..main import app

    apply_runtime_overrides()
    saved_env = {key: os.environ.get(key) for key in ENV_KEYS}
    saved = (jbai_ocr._http_post, jbai_ocr._RATE_LIMITER.acquire, jbai_ocr.urllib.request.urlopen)

    def no_network(*_args, **_kwargs):
        raise AssertionError("P15는 실제 네트워크를 쓰지 않습니다.")

    jbai_ocr._http_post = FAKE
    jbai_ocr._RATE_LIMITER.acquire = lambda: None
    jbai_ocr.urllib.request.urlopen = no_network
    os.environ["JBAI_BASE_URL"] = "https://ocr.example.invalid/open-api/v1"
    os.environ.pop("JBAI_TIMEOUT_SEC", None)
    tmp = Path(tempfile.mkdtemp(prefix="p15-jbai-"))
    p4._isolate(tmp)
    try:
        jbai_adapter.clear_cache()
        test_same_fields_as_localocr(tmp)
        test_photo_upload_is_jpeg(tmp)
        test_not_called(tmp)
        test_fallback(tmp)
        with TestClient(app) as client:
            test_api_privacy_cache_and_views(client, tmp)
    finally:
        jbai_ocr._http_post, jbai_ocr._RATE_LIMITER.acquire, jbai_ocr.urllib.request.urlopen = saved
        jbai_adapter.clear_cache()
        for key, value in saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n통과 {_passed} / 실패 {len(_failed)}")
    if _failed:
        for name in _failed:
            print(f"  - {name}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

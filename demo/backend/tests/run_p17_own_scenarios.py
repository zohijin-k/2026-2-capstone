"""P17 검증 — 모든 플랫폼의 demo 기본 own 및 모델 미설치 시에만 easyocr 대체.

저장소 루트에서:
    python -m demo.backend.tests.run_p17_own_scenarios

합성 서류와 임시 DB·저장소만 사용한다. 모델 경로는 monkeypatch하며 설치 자산은
건드리지 않는다. own 모델이 없는 기계에서는 실제 CPU 추론 항목만 SKIP한다.
"""

import os
import sys
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import patch

from ..engine_adapter import apply_runtime_overrides
from ..ocr import localocr
from ..ocr.localocr import ENGINE_ENV, LocalOcr, engine_decision
from ..rules.doc_check import check_document
from ..rules.doc_types import DocType
from . import run_p4_scenarios as p4
from .run_p8_localocr_scenarios import (
    abstract_slot, fake_abstract_words, make_image_pdf, make_text_pdf,
)
from .run_p9_identity_scenarios import identify, new_app

_passed = 0
_failed: list[str] = []
_skipped: list[str] = []


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


def test_defaults(tmp: Path) -> None:
    from engine_v2.pipeline.ocr import own
    from engine_v2.tools.fetch_own_models import ASSETS

    print("\n[1] 환경변수 없음·빈 값: macOS/Linux 모두 기본 own")
    complete = tmp / "present"
    complete.mkdir()
    for name in ASSETS:
        (complete / name).write_bytes(b"synthetic-placeholder")
    with patch.object(own, "MODEL_DIR", complete), patch.object(localocr._logger, "warning") as warning:
        for platform in ("darwin", "linux"):
            with patch.object(sys, "platform", platform):
                os.environ.pop(ENGINE_ENV, None)
                check(f"{platform} 기본 선택", engine_decision(), ("own", ""))
                check(f"{platform} 기존 이름 함수", localocr._engine_name(), "own")
                os.environ[ENGINE_ENV] = ""
                check(f"{platform} 빈 값", engine_decision(), ("own", ""))
        check("선택 조회만으로는 경고 없음", warning.call_count, 0)
    os.environ.pop(ENGINE_ENV, None)


def test_missing_default(tmp: Path, image: Path) -> None:
    from engine_v2.pipeline import ocr as v2ocr
    from engine_v2.pipeline.ocr import own
    from engine_v2.tools.fetch_own_models import ASSETS

    print("\n[2] 기본 own 모델 누락: easyocr·사유·판독당 경고 한 줄·메타데이터")
    words = fake_abstract_words()[0]
    with patch.object(own, "MODEL_DIR", tmp / "missing"), patch.object(localocr._logger, "warning") as warning:
        engine, reason = engine_decision()
        check("대체 엔진", engine, "easyocr")
        check_true("대체 사유에 own 모델 누락 명시", "own" in reason and "모델" in reason and "없음" in reason)
        check_true("대체 사유에 easyocr 명시", "easyocr" in reason)
        check("선택 조회 시 경고 없음", warning.call_count, 0)
        with patch.dict(v2ocr.ENGINES, {"easyocr": lambda png, size: words}):
            result = LocalOcr().read(str(image), DocType.RESIDENT_ABSTRACT)
        check("판독 시 경고 한 번", warning.call_count, 1)
        check("로그와 반환 사유 일치", warning.call_args.args, ("%s", reason))
        check_true("대체 엔진으로 판독 성공", result is not None)
        if result is not None:
            check("실제 엔진 이름", result.engine, "easyocr")
            check("fallback_reason 비어 있음", result.fallback_reason, "")
            check("quality_note 비어 있음", result.quality_note, "")

    for missing in ASSETS:
        partial = tmp / f"without-{missing}"
        partial.mkdir()
        for name in ASSETS:
            if name != missing:
                (partial / name).write_bytes(b"synthetic-placeholder")
        with patch.object(own, "MODEL_DIR", partial):
            engine, reason = engine_decision()
            check(f"필수 파일 누락 ({missing})", engine, "easyocr")
            check_true(f"필수 파일 누락 사유 ({missing})", reason)


def test_explicit_and_errors(tmp: Path, image: Path) -> None:
    from engine_v2.pipeline import ocr as v2ocr
    from engine_v2.pipeline.ocr import own

    print("\n[3] 명시한 own 모델 누락·일반 추론 오류·해시 오류: 엔진 대체 없음")
    actual_run = v2ocr.run_ocr
    recorded = []

    def record_run(*args, **kwargs):
        result = actual_run(*args, **kwargs)
        recorded.append(result)
        return result

    own.sessions.cache_clear()
    os.environ[ENGINE_ENV] = "own"
    with patch.object(own, "MODEL_DIR", tmp / "missing"), \
            patch.object(localocr._logger, "warning") as warning, \
            patch.object(v2ocr, "run_ocr", side_effect=record_run):
        check("명시한 own 선택", engine_decision(), ("own", ""))
        check("명시한 own 모델 누락은 다음 계층으로", LocalOcr().read(str(image), None), None)
        check("own 한 번만 시도", [r.engine for r in recorded], ["own"])
        check_true("기존 모델 누락 오류 보존", len(recorded) == 1 and "FileNotFoundError" in (recorded[0].error or ""))
        check("대체 경고 없음", warning.call_count, 0)

    os.environ.pop(ENGINE_ENV, None)
    recorded.clear()
    with patch.object(own, "MODEL_DIR", tmp / "present"), \
            patch.object(own, "sessions", side_effect=RuntimeError("synthetic inference failure")), \
            patch.object(localocr._logger, "warning") as warning, \
            patch.object(v2ocr, "run_ocr", side_effect=record_run):
        check("파일이 있으면 기본 own", engine_decision(), ("own", ""))
        check("일반 추론 오류는 다음 계층으로", LocalOcr().read(str(image), None), None)
        check("추론 오류 뒤 다른 엔진 호출 없음", [r.engine for r in recorded], ["own"])
        check_true("일반 추론 오류 보존", len(recorded) == 1 and "RuntimeError" in (recorded[0].error or ""))
        check("추론 오류에 대체 경고 없음", warning.call_count, 0)

    recorded.clear()
    own.sessions.cache_clear()
    with patch.object(own, "MODEL_DIR", tmp / "present"), \
            patch.object(localocr._logger, "warning") as warning, \
            patch.object(v2ocr, "run_ocr", side_effect=record_run):
        check("해시 불일치 파일도 존재하므로 own", engine_decision(), ("own", ""))
        check("해시 오류는 다음 계층으로", LocalOcr().read(str(image), None), None)
        check("해시 오류 뒤 다른 엔진 호출 없음", [r.engine for r in recorded], ["own"])
        check_true("기존 해시 오류 보존", len(recorded) == 1 and "SHA256 mismatch" in (recorded[0].error or ""))
        check("해시 오류에 대체 경고 없음", warning.call_count, 0)
    own.sessions.cache_clear()


def test_explicit_easyocr_and_off(tmp: Path, image: Path) -> None:
    from engine_v2.pipeline import ocr as v2ocr
    from engine_v2.pipeline.ocr import own

    print("\n[4] 명시 선택 우선·easyocr 미설치·off 이미지/텍스트 PDF 경계 유지")
    with patch.object(own, "MODEL_DIR", tmp / "missing"), patch.object(localocr._logger, "warning") as warning:
        for engine in ("easyocr", "applevision", "paddle", "off", "custom-value"):
            os.environ[ENGINE_ENV] = engine
            check(f"명시 값 그대로 ({engine})", engine_decision(), (engine, ""))
        os.environ[ENGINE_ENV] = "easyocr"
        with patch.dict(v2ocr.ENGINES, {"easyocr": lambda png, size: fake_abstract_words()[0]}):
            result = LocalOcr().read(str(image), None)
        check_true("명시 easyocr 판독 성공", result is not None)
        if result is not None:
            check("명시 easyocr 엔진·사유", (result.engine, result.fallback_reason, result.quality_note), ("easyocr", "", ""))
        with patch.dict(sys.modules, {"easyocr": None}):
            check("easyocr 미설치면 조용히 다음 계층으로", LocalOcr().read(str(image), None), None)
        check("명시 easyocr는 대체 경고 없음", warning.call_count, 0)

        os.environ.pop(ENGINE_ENV, None)
        with patch.dict(sys.modules, {"easyocr": None}):
            check("기본 대체 후 easyocr 미설치도 다음 계층으로", LocalOcr().read(str(image), None), None)
        check("기본 대체 때만 경고 한 번", warning.call_count, 1)

    os.environ[ENGINE_ENV] = "off"
    text_pdf = make_text_pdf(tmp / "synthetic-text.pdf", [
        "건강보험료 납부확인서", "성명 가상시험", "생년월일 1999.01.01", "발급일 2026.11.10",
        "가입구분 직장가입자", "고지년월 고지금액 납부금액", "2025.10 100,000 100,000",
    ])
    with patch.object(v2ocr, "run_ocr", side_effect=AssertionError("off must not run OCR")) as run:
        check("off 이미지 건너뜀", LocalOcr().read(str(image), None), None)
        result = LocalOcr().read(str(text_pdf), None)
        check_true("off도 지원 텍스트 PDF는 읽음", result is not None)
        if result is not None:
            check("텍스트 PDF 실제 엔진", result.engine, "pdftext")
        check("off OCR 호출 없음", run.call_count, 0)
    os.environ.pop(ENGINE_ENV, None)


def test_real_upload(tmp: Path) -> None:
    from engine_v2.pipeline.ocr import own
    from engine_v2.tools.fetch_own_models import ASSETS

    print("\n[5] 합성 1쪽 업로드 → LocalOcr.read 실제 own CPU 추론 → 추출 → 기존 판정")
    if not all((own.MODEL_DIR / name).is_file() for name in ASSETS):
        _skipped.append("실제 own CPU 추론 (모델 파일 미설치)")
        print(f"  [SKIP] {_skipped[-1]}")
        return

    from fastapi.testclient import TestClient
    from engine_v2.tools.make_synth_eval import documents, render
    from ..api.common import list_documents
    from ..api.officer import _document_view
    from ..main import app

    _, cells, expected = next(documents())
    path = tmp / "synthetic-upload.png"
    render(cells).save(path, dpi=(300, 300))
    p4._isolate(tmp)
    actual_read = LocalOcr.read
    results = []

    def capture_read(reader, *args, **kwargs):
        result = actual_read(reader, *args, **kwargs)
        results.append(result)
        return result

    with patch.object(LocalOcr, "read", autospec=True, side_effect=capture_read):
        with TestClient(app) as client:
            app_id = new_app(client)
            identify(client, app_id, expected["name"], expected["birth_date"])
            with path.open("rb") as stream:
                response = client.post(
                    f"/api/applications/{app_id}/documents",
                    files={"file": (path.name, stream, "image/png")},
                    data={"slot_key": "resident_abstract", "declared_issue_date": expected["issue_date"]},
                )
            check("합성 업로드 성공", response.status_code, 200)
            check("LocalOcr.read 실제 호출 한 번", len(results), 1)
            result = results[0] if results else None
            check_true("실제 own 판독 결과 있음", result is not None)
            if result is not None:
                check("실제 판독 계층·엔진", (result.tier, result.engine), ("localocr", "own"))
                check("합성 1쪽", result.page_count, 1)
                check("실제 서류 분류", result.detected_doc_type, DocType.RESIDENT_ABSTRACT)
                for key, truth in (("성명", expected["name"]), ("생년월일", expected["birth_date"]), ("발급일", expected["issue_date"])):
                    check(f"실제 추출 ({key})", result.fields.get(key), truth)
                    check_true(f"실제 추출 좌표 ({key})", key in result.bboxes)
                check("실제 판독 대체 메모 없음", (result.fallback_reason, result.quality_note), ("", ""))
                decision = check_document(abstract_slot(), result, date.fromisoformat(expected["issue_date"]))
                check("합성 서류의 부족한 이력·신청인 정보는 담당자 확인", decision.status, "NEEDS_REVIEW")
                check_true("부족한 이력·신청인 정보를 채우지 않음", {"PAST_ADDRESS_OMISSION_SUSPECTED", "RESIDENT_APPLICANT_UNREADABLE"} <= set(decision.codes))
            body = response.json()
            check("업로드 API도 기존 판정 적용", body.get("status"), "NEEDS_REVIEW")
            texts = [response.text,
                     client.get(f"/api/applications/{app_id}/documents").text,
                     client.get(f"/api/applications/{app_id}/required-documents").text]
            for label, text in zip(("업로드 응답", "서류 목록", "체크리스트"), texts):
                check_true(f"신청자 {label}에 엔진 메타데이터 없음", all(token not in text for token in ('"own"', 'ocr_engine', 'fallback_reason', 'engine_decision')))
            rows = list_documents(app_id)
            check("저장한 합성 서류 한 건", len(rows), 1)
            if rows:
                officer = _document_view(rows[0], {"resident_abstract": "주민등록초본"})
                check("담당자 실제 엔진", officer.get("ocr_engine"), "own")


def main() -> int:
    from engine_v2.pipeline import jbai_ocr

    apply_runtime_overrides()
    with patch.dict(os.environ), tempfile.TemporaryDirectory(prefix="p17-own-") as directory:
        for key in (ENGINE_ENV, "JBAI_API_KEY", "JBAI_ALLOW_REAL_DOCS"):
            os.environ.pop(key, None)
        with patch.object(jbai_ocr, "_http_post", side_effect=AssertionError("P17 must not call JBAI")) as remote:
            tmp = Path(directory)
            image = make_image_pdf(tmp / "synthetic-image.pdf", pages=1)
            test_defaults(tmp)
            test_missing_default(tmp, image)
            test_explicit_and_errors(tmp, image)
            test_explicit_easyocr_and_off(tmp, image)
            test_real_upload(tmp)
            check("전북AI 호출 없음", remote.call_count, 0)
    print(f"\n통과 {_passed} / 실패 {len(_failed)} / SKIP {len(_skipped)}")
    if _failed:
        for name in _failed:
            print(f"  - {name}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

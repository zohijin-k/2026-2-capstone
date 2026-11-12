"""P20 — 자격득실 이어지는 쪽 신원 생략과 문서확인번호 비교 합성 시나리오."""

from __future__ import annotations

import os
import shutil
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import patch

from ..engine_adapter import apply_runtime_overrides
from ..ocr.localocr import ENGINE_ENV, LocalOcr
from ..rules.doc_types import DocType
from ..rules.required_docs import DocRequirement

NAME = "가상가입자"
BIRTH = date(1984, 2, 3)
IMAGE_SIZE = (2066, 2923)
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


def _words(page_no: int, *, identity: bool):
    from engine_v2.pipeline.ocr import OcrWord

    def word(x: float, y: float, text: str, width: float = 8):
        return OcrWord(text, 0.99, (x / 100 * IMAGE_SIZE[0], y / 100 * IMAGE_SIZE[1],
                                    (x + width) / 100 * IMAGE_SIZE[0],
                                    (y + 0.8) / 100 * IMAGE_SIZE[1]))

    words = [word(5, 4, "건강보험 자격득실확인서", 35),
             word(8, 7, "문서확인번호"), word(22, 7, "7310-2468-1357-9024", 32)]
    if identity:
        words += [word(8, 10, "성명"), word(18, 10, NAME, 12),
                  word(8, 13, "주민등록번호"), word(26, 13, "840203-3******", 25),
                  word(8, 16, "발급일"), word(20, 16, "2031.07.08", 15)]
    words += [word(8, 22, "가입자구분"), word(32, 22, "자격취득일"),
              word(55, 22, "자격상실일"), word(76, 22, "사업장명칭"),
              word(8, 27, "직장가입자"), word(32, 27, "2025.03.04", 15),
              word(76, 27, "가상회사", 12)]
    if page_no == 1:
        words += [word(8, 70, "위와 같이 확인합니다", 40),
                  word(42, 73, "2031 년 7 월 8 일", 25),
                  word(35, 76, "국민건강보험공단 이사장", 40)]
    return words


def test_upload_headerless_continuation(tmp: Path) -> None:
    from fastapi.testclient import TestClient
    from .. import models
    from ..main import app
    from . import run_p4_scenarios as p4
    from .run_p8_localocr_scenarios import install_fake_ocr, make_image_pdf
    from .run_p9_identity_scenarios import identify, new_app

    p4._isolate(tmp)
    req = DocRequirement(slot_key="nhis_acquisition_loss", doc_type=DocType.NHIS_ACQUISITION_LOSS,
                         label="가상 자격득실 확인서", recent_years=5)
    try:
        with TestClient(app) as client:
            app_id = new_app(client)
            check("합성 신청자 인증", identify(client, app_id, NAME, BIRTH.isoformat()).status_code, 200)
            path = make_image_pdf(tmp / "synthetic-continuation.pdf", pages=2)
            install_fake_ocr([_words(0, identity=True), _words(1, identity=False)])
            captured = []
            original_read = LocalOcr.read

            def capture_read(reader, *args, **kwargs):
                result = original_read(reader, *args, **kwargs)
                captured.append(result)
                return result

            with patch.object(LocalOcr, "read", autospec=True, side_effect=capture_read), path.open("rb") as stream:
                response = client.post(
                    f"/api/applications/{app_id}/documents",
                    files={"file": (path.name, stream, "application/pdf")},
                    data={"slot_key": "nhis_acquisition_loss"},
                )
            check("업로드 응답", response.status_code, 200)
            check("LocalOcr 판독 건수", len(captured), 1)
            result = captured[0] if captured else None
            check("판독 계층", result.tier if result else None, "localocr")
            check("신뢰도 기준 통과", bool(result and result.confidence >= 0.85), True)
            check("번호 원문 비노출", bool(result and "문서확인번호" not in result.fields), True)
            codes = [finding.get("code") for finding in response.json().get("findings", [])]
            check("페이지 신원 검토 없음", "LOW_OCR_CONFIDENCE" not in codes, True)
    finally:
        models.engine.dispose()
        shutil.rmtree(tmp / "storage", ignore_errors=True)


def main() -> int:
    from ..engine_adapter import apply_runtime_overrides

    apply_runtime_overrides()
    with patch.dict(os.environ):
        os.environ[ENGINE_ENV] = "fake"
        with tempfile.TemporaryDirectory(prefix="p20-nhis-continuation-") as directory:
            test_upload_headerless_continuation(Path(directory))
    print(f"\n통과 {_passed} / 실패 {len(_failed)}")
    if _failed:
        for name in _failed:
            print(f"  - {name}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""P19 — 자격득실 5년 포함 결과가 OCR·업로드 판정 사이에서 일치하는지 확인.

저장소 루트에서:
    python -m demo.backend.tests.run_p19_nhis_history_scenarios

두 합성 서류는 이미지 PDF로 업로드하고, 가짜 OCR 엔진을 거쳐 LocalOcr와 문서 점검까지 탄다.
실제 서류와 실제 개인정보는 사용하지 않는다.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import patch

from ..engine_adapter import apply_runtime_overrides
from ..ocr.base import OcrResult
from ..ocr.localocr import ENGINE_ENV, LocalOcr
from ..rules.doc_check import check_document
from ..rules.doc_types import DocType
from ..rules.required_docs import DocRequirement

ISSUE = date(2031, 7, 8)
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


def check_true(name: str, value: object) -> None:
    check(name, bool(value), True)


def words_for_history(*, old_loss: bool):
    from engine_v2.pipeline.ocr import OcrWord

    def word(x: float, y: float, text: str, width: float = 8) -> OcrWord:
        return OcrWord(text, 0.99, (x / 100 * IMAGE_SIZE[0], y / 100 * IMAGE_SIZE[1],
                                    (x + width) / 100 * IMAGE_SIZE[0],
                                    (y + 0.8) / 100 * IMAGE_SIZE[1]))

    output = [word(5, 4, "건강보험 자격득실확인서", 35),
              word(8, 9, "성명"), word(20, 9, NAME, 12),
              word(8, 12, "생년월일"), word(25, 12, "1984.02.03", 12),
              word(8, 15, "발급일"), word(25, 15, "2031.07.08", 12),
              word(8, 22, "가입자구분"), word(32, 22, "자격취득일"),
              word(55, 22, "자격상실일"), word(76, 22, "사업장명칭")]
    rows = []
    if old_loss:
        rows.append(("직장피부양자", "2019-02-03", "2020-04-05"))
    rows.extend([
        ("지역가입자", "2027-01-02", "2028-03-04"),
        ("직장피부양자", "2029-05-06", ""),
    ])
    for index, (category, acquired, lost) in enumerate(rows):
        y = 27 + index * 4
        output.extend([word(8, y, category, 18), word(32, y, acquired, 12)])
        if lost:
            output.append(word(55, y, lost, 12))
        output.append(word(76, y, "가상사업장", 14))
    return output


def _legacy_result(*, old_loss: bool) -> OcrResult:
    rows = []
    if old_loss:
        rows.append({"category": "직장피부양자", "acquired": "2019-02-03", "lost": "2020-04-05"})
    rows.extend([
        {"category": "지역", "acquired": "2027-01-02", "lost": "2028-03-04"},
        {"category": "직장피부양자", "acquired": "2029-05-06", "lost": None},
    ])
    fields = {"발급일": ISSUE.isoformat(),
              "자격이력자료": json.dumps({"period": None, "rows": rows}, separators=(",", ":"))}
    return OcrResult(detected_doc_type=DocType.NHIS_ACQUISITION_LOSS, confidence=0.95,
                     image_quality=0.9, issue_date=ISSUE, fields=fields, tier="pdftext")


def test_upload_read_decision(tmp: Path) -> None:
    from fastapi.testclient import TestClient
    from .. import models
    from ..main import app
    from . import run_p4_scenarios as p4
    from .run_p8_localocr_scenarios import install_fake_ocr, make_image_pdf
    from .run_p9_identity_scenarios import identify, new_app

    print("\n[1] 이미지 PDF 업로드 → LocalOcr → 최근 5년 판정")
    p4._isolate(tmp)
    req = DocRequirement(slot_key="nhis_acquisition_loss", doc_type=DocType.NHIS_ACQUISITION_LOSS,
                         label="자격득실확인서", recent_years=5)
    try:
        with TestClient(app) as client:
            for index, old_loss in enumerate((True, False)):
                app_id = new_app(client)
                check(f"합성 신청자 인증 {index}", identify(client, app_id, NAME, BIRTH.isoformat()).status_code, 200)
                path = make_image_pdf(tmp / f"synthetic-history-{index}.pdf", pages=1)
                install_fake_ocr([words_for_history(old_loss=old_loss)])
                captured = []
                original_read = LocalOcr.read

                def capture_read(reader, *args, **kwargs):
                    value = original_read(reader, *args, **kwargs)
                    captured.append(value)
                    return value

                with patch.object(LocalOcr, "read", autospec=True, side_effect=capture_read), path.open("rb") as stream:
                    response = client.post(
                        f"/api/applications/{app_id}/documents",
                        files={"file": (path.name, stream, "application/pdf")},
                        data={"slot_key": "nhis_acquisition_loss"},
                    )
                body = response.json()
                check(f"업로드 응답 {index}", response.status_code, 200)
                check(f"LocalOcr 판독 {index}", len(captured), 1)
                result = captured[0] if captured else None
                check_true(f"판독 계층 localocr {index}", result is not None and result.tier == "localocr")
                if result is not None:
                    history = json.loads(result.fields["자격이력자료"])
                    check(f"엔진 5년 세 상태 {index}", history.get("recent_five_years_covered"),
                          True if old_loss else None)
                    check(f"엔진 5년 판단 근거 {index}", history.get("coverage_basis"),
                          "history_rows" if old_loss else "undetermined")
                    check_true(f"피부양자를 현 직장 취득일로 오인하지 않음 {index}", "취득일" not in result.fields)
                codes = [finding.get("code") for finding in body.get("findings", [])]
                check(f"NHIS_HISTORY_PERIOD_MISSING {index}",
                      "NHIS_HISTORY_PERIOD_MISSING" in codes, False)
                check(f"NHIS_HISTORY_PERIOD_UNREADABLE {index}",
                      "NHIS_HISTORY_PERIOD_UNREADABLE" in codes, not old_loss)
                check_true(f"범위 불확실로 자동 FAIL하지 않음 {index}",
                           not any(finding.get("severity") == "FAIL" for finding in body.get("findings", [])
                                   if finding.get("code", "").startswith("NHIS_HISTORY_PERIOD")))

        print("\n[2] 기존 JSON(엔진 불리언 없음) 하위 호환")
        for index, old_loss in enumerate((True, False)):
            decision = check_document(req, _legacy_result(old_loss=old_loss))
            codes = decision.codes
            check(f"기존 JSON NHIS_HISTORY_PERIOD_MISSING {index}",
                  "NHIS_HISTORY_PERIOD_MISSING" in codes, not old_loss)
            check_true(f"기존 JSON 범위 불확실은 확인필요 {index}",
                       all(finding.severity == "NEEDS_REVIEW" for finding in decision.findings
                           if finding.code == "NHIS_HISTORY_PERIOD_MISSING"))
    finally:
        models.engine.dispose()
        shutil.rmtree(tmp / "storage", ignore_errors=True)


def main() -> int:
    from .. import models

    apply_runtime_overrides()
    with patch.dict(os.environ):
        os.environ[ENGINE_ENV] = "fake"
        with tempfile.TemporaryDirectory(prefix="p19-nhis-history-") as directory:
            test_upload_read_decision(Path(directory))
    print(f"\n통과 {_passed} / 실패 {len(_failed)}")
    if _failed:
        for name in _failed:
            print(f"  - {name}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

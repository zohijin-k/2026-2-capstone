"""Research only: synthetic upload API probes; all temporary files stay here."""
import io
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
TASK = Path(__file__).resolve().parent
os.environ.pop("DEMO_OCR_ENGINE", None)
os.environ.pop("JBAI_API_KEY", None)
os.environ.pop("JBAI_BASE_URL", None)
os.environ.pop("JBAI_ALLOW_REAL_DOCS", None)

from fastapi.testclient import TestClient
from PIL import ImageFilter
from demo.backend.tests import run_p4_scenarios as p4
from demo.backend.tests.run_p9_identity_scenarios import identify, new_app
from demo.backend.ocr.localocr import ENGINE_ENV, engine_decision
from demo.backend.api.common import list_documents
from demo.backend.main import app
from demo.backend import models
from engine_v2.tools.make_synth_eval import documents, render
from engine_v2.tests.test_insurance_4 import employed_words


def main():
    os.environ.pop(ENGINE_ENV, None)
    print("DEFAULT", engine_decision(), flush=True)
    with tempfile.TemporaryDirectory(prefix="probe-", dir=TASK) as directory:
        tmp = Path(directory)
        p4._isolate(tmp)
        _, resident, truth = next(documents())
        resident = list(resident) + [
            (10, 24, "신청인: 가상시험 (1999-01-01)"),
            (8, 44, "2"), (15, 44, "전북특별자치도 전주시 가상동"),
            (54, 44, "2021-01-01"), (69, 44, "2021-01-01"),
            (84, 44, "본인"), (73, 47, "전입"),
        ]

        def modified(replacements):
            return [(x, y, replacements.get(text, text)) for x, y, text in resident]

        base = render(resident)
        insurance = []
        full_insurance = []
        for word in employed_words():
            x0, y0, _, _ = word.bbox_px
            text = word.text.replace("990101-1123456", "990101-1******")
            insurance.append((x0 / 10, y0 / 14 + .8, text))
            full_insurance.append((x0 / 10, y0 / 14 + .8, word.text))
        cases = [
            ("normal", base, truth["name"], "resident_abstract", "2026-11-10"),
            ("other_name", render(modified({"신청인: 가상시험 (1999-01-01)": "신청인: 김가상 (1999-01-01)", "가상시험": "김가상"})), truth["name"], "resident_abstract", "2026-11-10"),
            ("missing_page", render(modified({"1/1": "1/2"})), truth["name"], "resident_abstract", "2026-11-10"),
            ("old_issue", render(modified({"2026년 11월 10일": "2025년 11월 10일"})), truth["name"], "resident_abstract", "2025-11-10"),
            ("wrong_type", render(modified({next(t for _, _, t in resident if "(초본)" in t): "주민등록표 (등본)"})), truth["name"], "resident_abstract", "2026-11-10"),
            ("blur", base.filter(ImageFilter.GaussianBlur(5)), truth["name"], "resident_abstract", "2026-11-10"),
            ("rotate90", base.rotate(90, expand=True, fillcolor="white"), truth["name"], "resident_abstract", "2026-11-10"),
            ("insurance4", render(insurance), "김전북", "work_proof", "2026-11-10"),
            ("insurance4_complete", render(full_insurance), "김전북", "work_proof", "2026-11-10"),
        ]
        if len(sys.argv) > 1:
            cases = [case for case in cases if case[0] in sys.argv[1:]]
        print("CLIENT_START", flush=True)
        with TestClient(app) as client:
            print("CLIENT_READY", flush=True)
            for name, image, owner, slot, declared in cases:
                app_id = new_app(client)
                assert identify(client, app_id, owner, "1999-01-01").status_code == 200
                client.put(f"/api/applications/{app_id}/doc-context", json={"work_category": "직장가입자"})
                buffer = io.BytesIO()
                image.save(buffer, format="PNG", dpi=(300, 300))
                response = client.post(f"/api/applications/{app_id}/documents",
                    files={"file": (f"probe-{name}.png", buffer.getvalue(), "image/png")},
                    data={"slot_key": slot, "declared_issue_date": declared})
                body = response.json()
                forbidden = {"tier", "engine", "ocr_engine", "ocr_tier", "fallback_reason", "quality_note", "detail", "bboxes"}
                def leaks(value):
                    if isinstance(value, dict):
                        return sorted(forbidden.intersection(value)) + [s for v in value.values() for s in leaks(v)]
                    if isinstance(value, list):
                        return [s for v in value for s in leaks(v)]
                    return []
                outputs = [body,
                    client.get(f"/api/applications/{app_id}/documents").json(),
                    client.get(f"/api/applications/{app_id}/required-documents").json()]
                internal = list_documents(app_id)[0].ocr_json
                print(json.dumps({"case": name, "http": response.status_code,
                    "response": body, "metadata_leaks": [leaks(v) for v in outputs],
                    "engine_strings_absent": all(token not in json.dumps(outputs) for token in ('"own"', '"localocr"', '"pdftext"', '"easyocr"', '"jbai"')),
                    "internal": {k: internal.get(k) for k in ("tier", "engine", "confidence", "image_quality")},
                    "validations": {k: v for k, v in internal.get("fields", {}).items()
                        if k in {"판독검증", "판독검증실패", "주소이력건수", "근로관련가입여부"}}}, ensure_ascii=False), flush=True)
        models.engine.dispose()


if __name__ == "__main__":
    main()

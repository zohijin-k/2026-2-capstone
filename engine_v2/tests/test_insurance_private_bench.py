"""Fictitious insurance_4 benchmark: complete contract and value-free output."""
from datetime import date
import json
import os
import sys

import pytest
from PIL import Image

from engine_v2.pipeline.ocr import OcrResult
from engine_v2.tools import private_bench as bench
from engine_v2.tests.test_insurance_4 import synthetic_words, page

TODAY = date(2026, 11, 11)
SECRET = "가짜정답절대출력금지"
RECOGNIZED = "가짜인식절대출력금지"


def truth():
    return {"name": "김전북", "birth_date": "1999-01-01", "issue_date": "2026-11-10",
            "document_number": "1234-5678-9012-3456", "rows": [
                {"insurance": "국민연금", "status": "가입", "name": "김전북",
                 "subscriber_category": "지역가입자", "management_number": "", "workplace_name": "",
                 "acquired": "2020-01-02", "received": None},
                {"insurance": "건강보험", "status": "가입", "name": "김전북",
                 "subscriber_category": "직장피부양자", "management_number": "", "workplace_name": "",
                 "acquired": "2021-02-03", "received": "2021-02-04"},
                {"insurance": "산재보험", "status": "미가입"},
                {"insurance": "고용보험", "status": "미가입"}]}


def test_make_gt_contract_and_value_only_row_cer():
    from engine_v2.extractors.insurance_4 import extract
    from engine_v2.tools.synth_bench import cer
    from engine_v2.tools.insurance_bench import ROW_KEYS
    result = extract([page(synthetic_words())], today=TODAY)
    gt = truth()
    metrics = bench.field_metrics("insurance_4", gt, result)
    assert set(metrics) == set(gt)
    assert all(item == {"match": "O", "cer": 0} for item in metrics.values())
    gt["rows"][0]["received"] = "(-)"
    assert bench.field_metrics("insurance_4", gt, result)["rows"]["match"] == "O"
    gt["rows"] = list(reversed(gt["rows"]))
    assert bench.field_metrics("insurance_4", gt, result)["rows"]["match"] == "X"
    gt = truth()
    gt["rows"][0]["name"] = SECRET
    metrics = bench.field_metrics("insurance_4", gt, result)
    assert metrics["rows"]["cer"] > 0
    assert metrics["rows"]["match"] == "X"
    row = dict.fromkeys(ROW_KEYS, "")
    row["name"] = SECRET
    assert bench._value_text("rows", [row]) == "␀\n" + SECRET + "\n␀" * 6
    assert cer(SECRET, RECOGNIZED) > 0


def jbai_document():
    from engine_v2.pipeline.jbai_ocr import JBAIDocumentResult, JBAIPageResult, JBAITable, JBAITableCell
    rows = [["내역", "성명", "가입자종별", "사업장 관리번호", "사업장명칭", "자격취득일 (신고접수일)"]]
    for row in truth()["rows"]:
        if row["status"] == "미가입":
            rows.append([row["insurance"]] + ["미가입"] * 5)
        else:
            rows.append([row["insurance"], row["name"], row["subscriber_category"], "-", "-",
                         row["acquired"] + " (" + (row["received"] or "-") + ")"])
    return JBAIDocumentResult([JBAIPageResult(0, ["문서확인번호 1234-5678-9012-3456",
        "4대 사회보험", "가입자 가입내역 확인서", "발급일시 2026.11.10 10:20", "성명 김전북",
        "주민(외국인)등록번호 990101-1******"],
        [JBAITable([[JBAITableCell(text) for text in row] for row in rows])], 0)], 0)


def test_jbai_uses_existing_extractor_without_geometry_or_rrn_tail():
    from engine_v2.tools.insurance_bench import extract_jbai
    result = extract_jbai(jbai_document(), today=TODAY)
    metrics = bench.field_metrics("insurance_4", truth(), result)
    assert all(item == {"match": "O", "cer": 0} for item in metrics.values())
    assert all(field.bbox is None for field in result.fields.values())
    assert "******" not in str(result.fields)
    document = jbai_document()
    document.pages[0].tables.clear()
    assert "가입내역" not in extract_jbai(document, today=TODAY).fields


@pytest.mark.parametrize("engine", ["own", "applevision", "jbai"])
def test_private_cli_synthetic_extractor_suppresses_all_values(tmp_path, monkeypatch, capfd, engine):
    from engine_v2.pipeline import ocr, jbai_ocr
    from engine_v2.tools import ocr_bench
    image = tmp_path / f"{SECRET}.png"
    Image.new("RGB", (1000, 1400), "white").save(image)
    gt = truth()
    gt["name"] = SECRET
    gt_file = tmp_path / "truth.json"
    gt_file.write_text(json.dumps(gt), encoding="utf-8")
    output = tmp_path / "metrics.json"
    monkeypatch.setattr(bench, "unavailable", lambda name: 0)
    def noisy(*args, **kwargs):
        print(SECRET)
        print(RECOGNIZED, file=sys.stderr)
        os.write(1, SECRET.encode())
        os.write(2, RECOGNIZED.encode())
        if engine == "jbai":
            return jbai_document()
        return OcrResult(engine, synthetic_words())
    monkeypatch.setattr(ocr, "run_ocr", noisy)
    monkeypatch.setattr(jbai_ocr, "run_jbai_file_pair", noisy)
    monkeypatch.setattr(sys, "argv", ["ocr_bench", str(image), "--gt", str(gt_file),
        "--doc", "insurance_4", "--engines", engine, "--out", str(output), "--today", TODAY.isoformat()])
    ocr_bench.main()
    captured = capfd.readouterr()
    combined = captured.out + captured.err + output.read_text()
    for value in (SECRET, RECOGNIZED, str(image), image.name, "김전북", "1234-5678-9012-3456",
                  "1999-01-01", "2026-11-10", "2020-01-02", "2021-02-03", "2021-02-04",
                  "국민연금", "지역가입자", "직장피부양자", "990101", "1123456"):
        assert value not in combined
    report = json.loads(output.read_text())
    assert report["input_failed"] == "X"
    row = report["rows"][0]
    assert set(row) == {"engine", "skipped", "failed", "fallback", "reason_code", "pages",
                        "seconds_per_page", "mean_confidence", "confidence_available", "fields"}
    assert row["failed"] == "X" and row["pages"] == 1
    assert row["seconds_per_page"] >= 0
    assert row["mean_confidence"] == pytest.approx(-1 if engine == "jbai" else .99)
    assert set(row["fields"]) == {"name", "birth_date", "issue_date", "document_number", "rows"}
    assert row["fields"]["name"]["match"] == "X"
    assert row["fields"]["rows"] == {"match": "O", "cer": 0}
    assert all(set(item) == {"match", "cer"} for item in row["fields"].values())


def test_insurance_input_and_engine_failures_remain_value_free(tmp_path, monkeypatch, capfd):
    image = tmp_path / f"{SECRET}.png"
    Image.new("RGB", (100, 100), "white").save(image)
    gt = tmp_path / "truth.json"
    gt.write_text(json.dumps({SECRET: RECOGNIZED}))
    assert bench.run_private(image, gt, ["own"], doc="insurance_4")["input_failed"] == "O"
    gt.write_text(json.dumps(truth()))
    monkeypatch.setattr(bench, "unavailable", lambda engine: 0)
    def fail(*args):
        os.write(2, RECOGNIZED.encode())
        raise ValueError(SECRET)
    monkeypatch.setattr(bench, "run_engine", fail)
    report = bench.run_private(image, gt, ["own"], doc="insurance_4")
    assert report["rows"][0]["reason_code"] == 5
    assert report["rows"][0]["failed"] == "O"
    captured = capfd.readouterr()
    assert SECRET not in captured.out + captured.err
    assert RECOGNIZED not in captured.out + captured.err


def test_actual_own_insurance_synthetic_cli_is_value_free(tmp_path):
    import subprocess
    from engine_v2.tools.fetch_own_models import verify_models
    from engine_v2.tools.make_synth_eval import render
    try:
        verify_models()
    except (ValueError, FileNotFoundError):
        pytest.skip("own models unavailable")
    words = synthetic_words()
    cells = [(word.bbox_px[0] / 10, word.bbox_px[1] / 14, word.text) for word in words]
    image = tmp_path / f"{SECRET}.png"
    render(cells).save(image)
    gt = tmp_path / "truth.json"
    gt.write_text(json.dumps(truth()))
    output = tmp_path / "metrics.json"
    completed = subprocess.run([sys.executable, "-m", "engine_v2.tools.ocr_bench", str(image),
        "--gt", str(gt), "--doc", "insurance_4", "--engines", "own", "applevision", "jbai",
        "--out", str(output), "--today", TODAY.isoformat()], capture_output=True, text=True,
        env={key: value for key, value in os.environ.items() if not key.startswith("JBAI_")})
    assert completed.returncode == 0
    combined = completed.stdout + completed.stderr + output.read_text()
    for value in (SECRET, str(image), "김전북", "1234-5678-9012-3456", "990101-1123456",
                  "지역가입자", "직장피부양자", "2020.01.02", "2021.02.03"):
        assert value not in combined
    report = json.loads(output.read_text())
    assert report["input_failed"] == "X"
    own = report["rows"][0]
    assert own["failed"] == "X" and own["pages"] == 1
    assert set(own["fields"]) == set(truth())
    assert report["rows"][2]["skipped"] == "O"
    assert report["rows"][2]["reason_code"] == 3

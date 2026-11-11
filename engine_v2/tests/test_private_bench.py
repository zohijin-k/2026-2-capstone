"""Private benchmark output allowlist, exercised only with fictitious inputs."""
from datetime import date
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest
from PIL import Image

from engine_v2.pipeline.ocr import OcrResult, OcrWord
from engine_v2.schemas.models import ExtractedField, FieldSource
from engine_v2.tools import private_bench as bench

SECRET = "가짜비밀값절대출력금지"
RECOGNIZED = "가짜인식문자열출력금지"


def inputs(tmp_path):
    image = tmp_path / f"{SECRET}.png"
    Image.new("RGB", (300, 400), "white").save(image)
    gt = tmp_path / "truth.json"
    gt.write_text(json.dumps({"name": SECRET}), encoding="utf-8")
    return image, gt


def field(value):
    return ExtractedField(value=value, raw_text=RECOGNIZED, confidence=.9, source=FieldSource.OCR)


def test_real_mode_suppresses_values_native_logs_and_optional_file(tmp_path, monkeypatch, capfd):
    image, gt = inputs(tmp_path)
    before = set(tmp_path.iterdir())
    monkeypatch.setattr(bench, "unavailable", lambda engine: 0)
    def noisy_engine(engine, path, pages, doc, truth, today):
        print(SECRET)
        print(RECOGNIZED, file=sys.stderr)
        os.write(1, SECRET.encode())
        os.write(2, RECOGNIZED.encode())
        result = SimpleNamespace(fields={"name": field(RECOGNIZED)}, history=[])
        return {"failed": "X", "fallback": "X", "fields": bench.field_metrics(doc, truth, result)}
    monkeypatch.setattr(bench, "run_engine", noisy_engine)
    report = bench.run_private(image, gt, ["own"])
    assert set(tmp_path.iterdir()) == before
    output = tmp_path / "metrics.json"
    bench.run_private(image, gt, ["own"], out=output)
    captured = capfd.readouterr()
    all_output = captured.out + captured.err + output.read_text()
    assert SECRET not in all_output and RECOGNIZED not in all_output
    assert report["rows"][0]["fields"]["name"]["match"] == "X"
    assert report["rows"][0]["fields"]["name"]["cer"] > 0


def test_exception_logs_discarded_and_later_engine_continues(tmp_path, monkeypatch, capfd):
    image, gt = inputs(tmp_path)
    monkeypatch.setattr(bench, "unavailable", lambda engine: 0)
    def fail(engine, *args):
        if engine == "own":
            import ctypes
            ctypes.CDLL(None).printf((SECRET + "\n").encode())
            raise RuntimeError(RECOGNIZED)
        return {"failed": "X", "fallback": "X", "fields": {}}
    monkeypatch.setattr(bench, "run_engine", fail)
    output = tmp_path / "report.json"
    report = bench.run_private(image, gt, ["own", "applevision"], out=output)
    assert [row["failed"] for row in report["rows"]] == ["O", "X"]
    captured = capfd.readouterr()
    combined = captured.out + captured.err + output.read_text()
    assert SECRET not in combined and RECOGNIZED not in combined


def test_unknown_keys_and_input_failures_never_echo(tmp_path, capfd):
    image, gt = inputs(tmp_path)
    gt.write_text(json.dumps({SECRET: RECOGNIZED}))
    result = bench.run_private(image, gt, ["own"])
    assert result["input_failed"] == "O"
    gt.write_text(SECRET)
    result = bench.run_private(image, gt, ["own"])
    assert result["input_failed"] == "O"
    captured = capfd.readouterr()
    assert SECRET not in captured.out + captured.err
    assert RECOGNIZED not in captured.out + captured.err


def test_no_default_directory_no_input_overwrite(tmp_path, monkeypatch, capfd):
    image, gt = inputs(tmp_path)
    monkeypatch.setattr(bench, "unavailable", lambda engine: 2)
    original = gt.read_bytes()
    report = bench.run_private(image, gt, ["own"], out=gt)
    assert report["output_failed"] == "O"
    assert gt.read_bytes() == original
    destination = tmp_path / "missing" / "report.json"
    report = bench.run_private(image, gt, ["own"], out=destination)
    assert report["output_failed"] == "O"
    assert not destination.parent.exists()


def test_missing_platform_credentials_and_external_opt_in(monkeypatch):
    monkeypatch.setattr(bench.sys, "platform", "linux")
    monkeypatch.delenv("JBAI_API_KEY", raising=False)
    assert bench.unavailable("applevision") == 1
    assert bench.unavailable("jbai") == 3
    monkeypatch.setenv("JBAI_API_KEY", "fictitious")
    monkeypatch.delenv("JBAI_ALLOW_REAL_DOCS", raising=False)
    assert bench.unavailable("jbai") == 4
    monkeypatch.setenv("JBAI_ALLOW_REAL_DOCS", "true")
    assert bench.unavailable("jbai") == 0


def test_complete_make_gt_contracts_and_generic_keys():
    payment = {"name": SECRET, "birth_date": "1999-01-01", "issue_date": "2026-11-10",
               "insurance_type": "직장", "billed_by_month": {"2025-10": "123456"},
               "long_term_care_by_month": {"2025-10": "12345"}}
    fields = {"성명": field(SECRET), "생년월일": field(payment["birth_date"]), "발급일": field(payment["issue_date"]),
              "가입구분": field("직장"), "월별고지금액": field(json.dumps(payment["billed_by_month"])),
              "월별장기요양보험료": field(json.dumps(payment["long_term_care_by_month"]))}
    measured = bench.field_metrics("nhis_payment", payment, SimpleNamespace(fields=fields))
    assert set(measured) == set(payment)
    assert all(row == {"match": "O", "cer": 0} for row in measured.values())
    history = [{"category": "직장", "acquired": "2020-01-01", "lost": None}]
    period = ["2020-01-01", "2026-11-10"]
    truth = {"history": history, "query_period": period, "recent_five_years": True}
    fields = {"자격이력자료": field(json.dumps({"period": period, "rows": history})), "변동내역": field("최근 5년 포함")}
    measured = bench.field_metrics("nhis_acquisition_loss", truth, SimpleNamespace(fields=fields))
    assert all(row == {"match": "O", "cer": 0} for row in measured.values())


def test_contains_contracts_do_not_penalize_unannotated_address_or_dates():
    result = SimpleNamespace(fields={"current_address": field("전북 전주시 가상동")},
                             history=[SimpleNamespace(occurred=date(2020, 1, 1), reported=date(2020, 1, 2))])
    measured = bench.field_metrics("resident_abstract", {"address_contains": ["전주시"], "move_in_dates": ["2020-01-01"]}, result)
    assert all(row == {"match": "O", "cer": 0} for row in measured.values())


def test_pdf_text_layer_is_rasterized(tmp_path):
    import pymupdf
    path = tmp_path / "fictitious.pdf"
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((30, 30), "FAKE " * 30)
        document.save(path)
    pages = bench.raster_pages(path)
    assert len(pages) == 1 and pages[0].png and pages[0].text is None


def test_cli_argument_errors_are_value_free(tmp_path):
    result = subprocess.run([sys.executable, "-m", "engine_v2.tools.ocr_bench", "--doc", SECRET], capture_output=True, text=True)
    assert result.returncode == 2
    assert SECRET not in result.stdout + result.stderr
    assert "argument_error: O" in result.stderr


def test_actual_own_synthetic_image_cli_has_no_value_or_recognition_output(tmp_path):
    from engine_v2.tools.fetch_own_models import verify_models
    try:
        verify_models()
    except (ValueError, FileNotFoundError):
        pytest.skip("own models unavailable")
    from engine_v2.tools.make_synth_eval import documents, render
    _, cells, _ = next(documents())
    image = tmp_path / "synthetic.png"
    render(cells).save(image)
    gt = tmp_path / "synthetic.gt.json"
    gt.write_text(json.dumps({"name": SECRET, "birth_date": "1999-01-01"}), encoding="utf-8")
    output = tmp_path / "numeric.json"
    result = subprocess.run([sys.executable, "-m", "engine_v2.tools.ocr_bench", str(image), "--gt", str(gt),
                             "--engines", "own", "applevision", "jbai", "--out", str(output)], capture_output=True, text=True,
                            env={key: value for key, value in os.environ.items() if not key.startswith("JBAI_")})
    assert result.returncode == 0
    combined = result.stdout + result.stderr + output.read_text()
    for value in (SECRET, "가상시험", "1999-01-01", "문서확인번호", str(image)):
        assert value not in combined
    report = json.loads(output.read_text())
    assert report["input_failed"] == "X"
    assert report["rows"][0]["failed"] == "X"


def test_history_cer_counts_values_without_json_property_name_credit():
    from engine_v2.tools.synth_bench import cer
    truth = {"history": [{"category": "직장", "acquired": "2020-01-01", "lost": None}]}
    observed = [{"category": "지역", "acquired": "9999-99-99", "lost": "INVALID"}]
    extracted = SimpleNamespace(fields={"자격이력자료": field(json.dumps({"rows": observed}))})
    result = bench.field_metrics("nhis_acquisition_loss", truth, extracted)["history"]
    assert result["match"] == "X"
    assert result["cer"] == cer("직장2020-01-01␀", "지역9999-99-99INVALID")
    assert result["cer"] > .5
    assert bench._value_text("history", None) == ""
    assert bench._value_text("history", [{"category": None, "acquired": None, "lost": None}]) == "␀\n␀\n␀"

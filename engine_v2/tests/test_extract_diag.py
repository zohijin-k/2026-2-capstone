"""Privacy and trace tests use fake OCR, never private documents or model assets."""
from datetime import date
import json
from types import SimpleNamespace

import pytest

from engine_v2.pipeline.ocr import OcrResult, OcrWord
from engine_v2.pipeline.preprocess import PageImage, PageSource
from engine_v2.schemas.models import ExtractedField, FieldSource
from engine_v2.tools import extract_diag


def test_real_trace_masks_all_values_and_unknown_gt_keys(monkeypatch):
    secret = "SensitivePersonQX"
    field = ExtractedField(value=secret, raw_text=secret, source=FieldSource.OCR, confidence=.9)
    monkeypatch.setitem(extract_diag.EXTRACTORS, "resident_abstract", lambda *a, **kw: SimpleNamespace(fields={"name": field}))
    page = PageImage(0, PageSource.UPLOAD, (100, 100), pixel_size=(1000, 1000))
    result = OcrResult("own", [OcrWord(secret, .9, (100, 100, 500, 130))])
    report = extract_diag.diagnose([(page, result)], "resident_abstract", truth={"name": secret, "PrivateCustomFieldQX": secret})
    text = json.dumps(report)
    assert secret not in text and "PrivateCustomFieldQX" not in text
    assert report["fields"]["name"]["match"] is True
    assert report["fields"]["name"]["actual"] == "[masked]"
    assert report["pages"][0]["lines"][0][0]["bbox_percent"] == [10, 10, 50, 13]


def test_unmask_requires_synthetic_and_explicit_opt_in(monkeypatch):
    field = ExtractedField(value=date(1999, 1, 1), raw_text="990101", source=FieldSource.OCR, confidence=.9)
    monkeypatch.setitem(extract_diag.EXTRACTORS, "resident_abstract", lambda *a, **kw: SimpleNamespace(fields={"birth_date": field}))
    with pytest.raises(ValueError, match="internally generated"):
        extract_diag.diagnose([], "resident_abstract", unmasked=True)
    masked = extract_diag.diagnose([], "resident_abstract", synthetic=True)
    assert masked["fields"]["birth_date"]["actual"] == "[masked]"
    shown = extract_diag.diagnose([], "resident_abstract", synthetic=True, unmasked=True)
    assert shown["fields"]["birth_date"]["actual"] == "1999-01-01"


def test_cli_never_unmasks_file_input(capsys):
    with pytest.raises(SystemExit) as error:
        extract_diag.main(["sensitive-file.pdf", "--unmasked-synthetic"])
    assert error.value.code == 2
    assert "sensitive-file.pdf" not in capsys.readouterr().err


def test_cli_suppresses_failure_details(monkeypatch, capsys):
    def fail(*args, **kwargs):
        raise RuntimeError("DoNotPrintThisQX")
    monkeypatch.setattr(extract_diag, "run_file", fail)
    assert extract_diag.main(["fake.pdf"]) == 1
    output = capsys.readouterr().out
    assert "DoNotPrintThisQX" not in output
    assert "diagnostic_input_or_execution_failed" in output


def test_cli_suppresses_invalid_argument_values(capsys):
    with pytest.raises(SystemExit) as error:
        extract_diag.main(["fake.pdf", "--doc", "SensitiveBadArgumentQX"])
    assert error.value.code == 2
    assert "SensitiveBadArgumentQX" not in capsys.readouterr().err

"""Synthetic source-shaped images traverse real upload/check boundaries."""
from datetime import date
import json
import pytest
from PIL import Image
from demo.backend.ocr import read_document
from demo.backend.ocr.base import OcrResult
from demo.backend.ocr.localocr import _from_resident, LocalOcr
from demo.backend.rules.doc_check import check_document
from demo.backend.rules.doc_types import DocType
from demo.backend.rules.required_docs import DocRequirement
from demo.backend.rules.facts import build_facts
from engine_v2.extractors import resident_abstract
from engine_v2.schemas.models import DocType as V2Type
from engine_v2.tests import fail_case_samples as sample
from demo.backend.tests.test_portal_uploads import client, new_app, upload
from demo.backend.tests.test_p2_resident_uploads import use_own_words


def req():
    return DocRequirement(slot_key="resident_abstract",doc_type=DocType.RESIDENT_ABSTRACT,label="가짜 초본")


def convert(pages):
    return _from_resident(resident_abstract.extract(pages),pages,resident_abstract,V2Type)


def test_date_headers_with_blank_body_fail_independent_of_history_confidence():
    read=convert(sample.missing_address_dates())
    assert read.confidence == .4
    result=check_document(req(),read,file_format="jpg")
    assert result.status == "FAIL"
    finding=next(f for f in result.findings if f.code=="MISSING_ADDRESS_DATES")
    assert finding.severity == "FAIL" and "발생일·신고일" in finding.how_to_fix


def test_missing_header_stays_review_and_has_no_definite_date_omission():
    result=check_document(req(),convert(sample.missing_address_dates(header=False)))
    assert result.status == "NEEDS_REVIEW"
    assert "MISSING_ADDRESS_DATES" not in result.codes


def test_fallback_residence_value_remains_explicitly_unproven():
    read=convert(sample.missing_address_dates())
    facts=build_facts({"transferIn":"2020-01-01"},[{"doc_type":str(DocType.RESIDENT_ABSTRACT),"fields":read.fields}])
    assert facts.transfer_in_date == date(2020,1,1)
    assert "입력값으로 대체" in facts.source("residence").origin
    assert "증명 아님" in facts.source("residence").origin


@pytest.mark.parametrize("kind,expected",[("date","MISSING_ADDRESS_DATES"),("tiny","IMAGE_RESOLUTION_TOO_LOW")])
def test_actual_synthetic_image_upload_fails_with_certain_codes(client,tmp_path,monkeypatch,kind,expected):
    pages=sample.missing_address_dates() if kind=="date" else sample.tiny_unknown()
    use_own_words(monkeypatch,pages)
    # Include PdfText fallback to reproduce the old word-discarding route.
    import demo.backend.ocr as chain
    from demo.backend.ocr.pdftext import PdfTextOcr
    monkeypatch.setattr(chain,"CHAIN",[LocalOcr(),PdfTextOcr()])
    path=tmp_path/"FAKE.png"
    Image.new("RGB",pages[0][0].pixel_size,"white").save(path)
    data,stored=upload(client,new_app(client),path,"resident_abstract",filename="FAKE.png")
    assert data["status"] == "FAIL"
    assert expected in {f["code"] for f in data["findings"] if f["severity"]=="FAIL"}
    if kind=="tiny":
        assert data["detected_doc_type"] is None
        assert "PAGES_INCOMPLETE" in {f["code"] for f in data["findings"]}
        assert stored["engine"] == "own"
    else:
        assert "IMAGE_RESOLUTION_TOO_LOW" not in {f["code"] for f in data["findings"]}

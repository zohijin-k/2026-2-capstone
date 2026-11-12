"""Fictitious text-layer PDFs exercise the complete upload and verdict boundary."""
from datetime import date

import pymupdf
import pytest
from fastapi.testclient import TestClient
from sqlmodel import create_engine

from demo.backend import models
from demo.backend.api import applications, common, documents, files
from demo.backend.main import app
from demo.backend.ocr import read_document
from demo.backend.rules.doc_types import DocType
from demo.backend.rules.programs import DOUBLE_SAVINGS
from engine_v2.tests.nhis_form_samples import (
    NAME, BIRTH, ISSUE, acquisition_cells, qualification_cells, insurance_portal_cells, text_pdf,
)

FORMS = {
    "acquisition": (acquisition_cells, "nhis_acquisition_loss", DocType.NHIS_ACQUISITION_LOSS),
    "qualification": (qualification_cells, "nhis_qualification", DocType.NHIS_QUALIFICATION),
    "insurance": (insurance_portal_cells, "work_proof", DocType.INSURANCE_4),
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    isolated = create_engine(f"sqlite:///{tmp_path / 'fake.db'}", connect_args={"check_same_thread": False})
    monkeypatch.setattr(models, "engine", isolated)
    storage = tmp_path / "storage"
    for module in (applications, common, documents, files):
        monkeypatch.setattr(module, "STORAGE", storage)
    monkeypatch.setattr(applications, "SIGNATURES", storage / "signatures")
    monkeypatch.setattr(documents, "DOCUMENTS", storage / "documents")
    monkeypatch.setenv("ENGINE_V2_OCR", "off")
    try:
        with TestClient(app) as connected:
            yield connected
    finally:
        isolated.dispose()


def new_app(client, *, name=NAME, birth=BIRTH):
    response = client.post("/api/applications", json={"program_code": DOUBLE_SAVINGS})
    assert response.status_code == 200
    aid = response.json()["id"]
    assert client.put(f"/api/applications/{aid}/doc-context", json={"work_category": "직장가입자"}).status_code == 200
    with models.get_session() as session:
        application = session.get(models.Application, aid)
        application.identity_json = {"name": name, "birth": birth}
        session.add(application)
        session.commit()
    return aid


def upload(client, aid, path, slot, *, filename="FAKE-upload.pdf"):
    response = client.post(f"/api/applications/{aid}/documents",
                           files={"file": (filename, path.read_bytes(), "application/pdf")},
                           data={"slot_key": slot, "declared_issue_date": ISSUE})
    assert response.status_code == 200
    data = response.json()
    with models.get_session() as session:
        row = session.get(models.Document, data["document_id"])
        return data, dict(row.ocr_json)


@pytest.mark.parametrize("kind", FORMS)
def test_text_pdf_direct_expected_renaming_and_actual_upload_agree(kind, client, tmp_path):
    cells, slot, detected = FORMS[kind]
    path = text_pdf(tmp_path / "FAKE-source.pdf", cells())
    aid = new_app(client)
    direct = read_document(str(path))
    wrong_expected = read_document(str(path), DocType.RESIDENT_ABSTRACT)
    assert direct.detected_doc_type == wrong_expected.detected_doc_type == detected
    assert direct.fields == wrong_expected.fields
    assert direct.fields["성명"] == NAME
    assert direct.fields["생년월일"] == BIRTH
    assert direct.issue_date == date.fromisoformat(ISSUE)
    assert not direct.fields.get("판독검증실패")
    for filename in ("FAKE-one.pdf", "FAKE-arbitrary-data.pdf"):
        data, raw = upload(client, aid, path, slot, filename=filename)
        assert data["detected_doc_type"] == str(detected)
        assert data["status"] == "PASS"
        assert not data["findings"]
        assert (raw["tier"], raw["engine"]) == (direct.tier, direct.engine) == ("localocr", "pdftext")
        assert raw["fields"] == direct.fields
        assert raw["issue_date"] == ISSUE
    if kind != "insurance":
        assert not any(key in direct.fields for key in ("발급번호", "통보번호", "유효기간"))


@pytest.mark.parametrize("kind", FORMS)
def test_multiple_portal_pages_are_reviewed_in_actual_upload(kind, client, tmp_path):
    cells, slot, detected = FORMS[kind]
    single = text_pdf(tmp_path / "FAKE-single.pdf", cells())
    path = tmp_path / "FAKE-multiple.pdf"
    with pymupdf.open(single) as source, pymupdf.open() as merged:
        merged.insert_pdf(source)
        merged.insert_pdf(source)
        merged.save(path)
    data, raw = upload(client, new_app(client), path, slot)
    assert data["detected_doc_type"] == str(detected)
    assert data["status"] == "NEEDS_REVIEW"
    assert raw["confidence"] < .85
    assert raw["fields"]["양식판독상태"] == "불완전"
    assert raw["fields"]["판독검증실패"]
    assert all(finding["severity"] != "FAIL" for finding in data["findings"])


def test_acquisition_still_cannot_replace_qualification(client, tmp_path):
    path = text_pdf(tmp_path / "FAKE-wrong-slot.pdf")
    data, _ = upload(client, new_app(client), path, "nhis_qualification")
    assert data["status"] == "FAIL"
    assert [finding["code"] for finding in data["findings"]] == ["WRONG_DOCUMENT_TYPE"]


@pytest.mark.parametrize("kind", ["missing-name", "different-name", "different-birth"])
def test_acquisition_identity_problem_is_review_in_actual_upload(kind, client, tmp_path):
    path = text_pdf(tmp_path / "FAKE-identity.pdf", name=None if kind == "missing-name" else NAME)
    aid = new_app(client, name="가짜다름" if kind == "different-name" else NAME,
                  birth="1991-01-01" if kind == "different-birth" else BIRTH)
    data, raw = upload(client, aid, path, "nhis_acquisition_loss")
    assert data["status"] == "NEEDS_REVIEW"
    assert all(finding["severity"] != "FAIL" for finding in data["findings"])
    if kind == "missing-name":
        assert "성명" not in raw["fields"]
        assert "성명" in raw["fields"]["판독검증실패"]
        assert raw["confidence"] < .85


@pytest.mark.parametrize("pair,listed", [(False, True), (True, True), (True, False)])
def test_qualification_member_upload_preserves_existing_pair_rule(pair, listed, client, tmp_path):
    aid = new_app(client, name="가짜가족" if listed else "가짜외부", birth="2001-01-01")
    if pair:
        with models.get_session() as session:
            session.add(models.Document(application_id=aid, slot_key="nhis_payment",
                doc_type=str(DocType.NHIS_PAYMENT), expected_doc_type=str(DocType.NHIS_PAYMENT),
                file_path="storage/FAKE-payment.pdf", file_format="pdf",
                declared_issue_date=date.fromisoformat(ISSUE), stage1_status="PASS",
                ocr_json={"detected_doc_type": str(DocType.NHIS_PAYMENT), "tier": "localocr",
                    "confidence": .95, "image_quality": .9, "issue_date": ISSUE,
                    "fields": {"성명": NAME, "생년월일": BIRTH, "발급일": ISSUE}, "bboxes": {}}))
            session.commit()
    path = text_pdf(tmp_path / "FAKE-members.pdf", qualification_cells())
    data, _ = upload(client, aid, path, "nhis_qualification")
    codes = [finding["code"] for finding in data["findings"]]
    if pair and listed:
        assert data["status"] == "PASS"
        assert "NHIS_DEPENDENT_INSURED_PERSON" in codes
        assert "NHIS_SUBSCRIBER_IDENTITY_REVIEW" not in codes
    else:
        assert data["status"] == "NEEDS_REVIEW"
        assert "NHIS_SUBSCRIBER_IDENTITY_REVIEW" in codes

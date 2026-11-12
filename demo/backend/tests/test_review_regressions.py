"""Upload and scoring boundaries retain review for confirmed uncertain inputs."""
from dataclasses import asdict
from datetime import date
import json
from types import SimpleNamespace

import pytest

from demo.backend.engine_adapter import run_pipeline, to_engine_applicant, to_engine_documents
from demo.backend import models
from demo.backend.api.common import document_fact
from demo.backend.ocr import read_document
from demo.backend.ocr.localocr import _from_nhis
from demo.backend.rules.doc_check import check_document
from demo.backend.rules.doc_types import DocType
from demo.backend.rules.facts import build_facts
from demo.backend.rules.identity import Identity
from demo.backend.rules.programs import DOUBLE_SAVINGS, PROGRAMS
from demo.backend.rules.required_docs import DocRequirement
from demo.backend.rules.scoring import score_application
from demo.backend.tests.test_p2_nhis_uploads import image_pdf, use_own_words
from demo.backend.tests.test_p2_payment_facts import payment_fact
from demo.backend.tests.test_portal_uploads import client, new_app, upload
from demo.backend.tests.test_resident_number_privacy import image_pdf as raster_pdf, privacy_cells
from engine_v2.pipeline import ocr
from engine_v2.extractors import nhis_payment
from engine_v2.schemas.models import DocType as V2DocType
from engine_v2.tests import p2_form_samples as nhis_sample, p2_payment_samples as sample
from engine_v2.tests.nhis_form_samples import text_pdf


@pytest.mark.parametrize("prefix", ["RRN", "TAG"])
@pytest.mark.parametrize("image", [False, True])
def test_ascii_prefixed_resident_text_is_safe_after_actual_upload(
        prefix, image, client, tmp_path, monkeypatch, caplog):
    suffix = "654321"
    cells = [*privacy_cells(False), (10, 85, prefix + "900101-1" + suffix)]
    source = text_pdf(tmp_path / "FAKE-prefixed-source.pdf", cells)
    path = raster_pdf(source, tmp_path / "FAKE-prefixed-image.pdf") if image else source
    observed = []
    if image:
        monkeypatch.setenv("ENGINE_V2_OCR", "own")

        def recognize(_png, size):
            scale_x, scale_y = size[0] / 1000, size[1] / 1400
            words = [ocr.OcrWord(text, .99, (x * 10 * scale_x, y * 14 * scale_y,
                     (x + len(text) * .8) * 10 * scale_x, (y + .8) * 14 * scale_y)) for x, y, text in cells]
            observed.append(words)
            return words

        monkeypatch.setitem(ocr.ENGINES, "own", recognize)
    response, saved = upload(client, new_app(client), path, "nhis_acquisition_loss")
    assert response["status"] == "PASS"
    assert saved["fields"]["생년월일"] == "1990-01-01"
    direct = read_document(str(path))
    result_file = tmp_path / "FAKE-review-result.json"
    result_file.write_text(json.dumps([response, saved, asdict(direct)], default=str), encoding="utf-8")
    assert suffix not in result_file.read_text(encoding="utf-8")
    assert suffix not in repr(observed)
    assert suffix not in caplog.text


@pytest.mark.parametrize("kind", ["crossing-name", "crossing-payer", "period-conflict", "same-period", "document-residue"])
def test_payment_ambiguous_metadata_is_reviewed_in_actual_upload(kind, client, tmp_path, monkeypatch):
    cells, size = sample.payment()
    if kind == "crossing-name":
        cells.append(sample.cell(1100, 509, 1250, 560, "가상다름", 1))
    elif kind == "crossing-payer":
        cells.append(sample.cell(1250, 590, 1350, 634, "12345678901", 1))
    elif kind in {"period-conflict", "same-period"}:
        text = "2024년 01월 ~ 2024년 12월 납부내역" if kind == "period-conflict" else "2025년 10월 ~ 2025년 12월 납부내역"
        cells.append(sample.cell(757, 705, 1310, 746, text, 1))
    else:
        cells = [(*cell[:4], cell[4] + "가상추가" if "문서확인번호" in cell[4] else cell[4], cell[5]) for cell in cells]
    use_own_words(monkeypatch, cells, size)
    path = image_pdf(tmp_path / "FAKE-ambiguous-payment.pdf", size)
    response, stored = upload(client, new_app(client, name=sample.NAME, birth=sample.BIRTH), path, "nhis_payment")
    assert response["status"] == "NEEDS_REVIEW"
    assert stored["fields"]["양식판독상태"] == "불완전"
    assert stored["confidence"] <= .4
    assert all(finding["severity"] != "FAIL" for finding in response["findings"])


@pytest.mark.parametrize("corrupt", ["2025.OI.OI", "OOOO.OI.OI"])
def test_malformed_loss_never_becomes_employer_in_actual_upload(corrupt, client, tmp_path, monkeypatch):
    cells, size = nhis_sample.acquisition()
    cells.extend([nhis_sample.cell(845, 1115, 2260, 1161, "가상상사" * 17, .99),
                  nhis_sample.cell(2048, 1115, 2263, 1161, corrupt, .99)])
    use_own_words(monkeypatch, cells, size)
    path = image_pdf(tmp_path / "FAKE-malformed-loss.pdf", size)
    response, stored = upload(client, new_app(client, name=sample.NAME, birth=sample.BIRTH),
                              path, "nhis_acquisition_loss")
    assert response["status"] == "NEEDS_REVIEW"
    assert stored["fields"]["양식판독상태"] == "불완전"
    assert all(finding["severity"] != "FAIL" for finding in response["findings"])


@pytest.mark.parametrize("confidence", [.4, .8, None])
@pytest.mark.parametrize("structure_marker", [False, True])
def test_legacy_uncertain_payment_confidence_blocks_income_rejection(confidence, structure_marker):
    payment, requirement = payment_fact(high=True, damaged=True)
    payment.pop("status")
    payment["confidence"] = confidence
    if not structure_marker:
        payment["fields"].pop("양식판독상태")
    qualification = {"doc_type": str(DocType.NHIS_QUALIFICATION), "fields": {"가구원수": "1"}}
    facts = build_facts({}, [payment, qualification], ["2025-10", "2025-11", "2025-12"])
    assert facts.monthly_premium is None
    program = PROGRAMS[DOUBLE_SAVINGS]
    sheet = score_application(facts, announcement_date=program.announcement_date, age_basis_date=program.age_basis_date)
    applicant = to_engine_applicant(application_no="FAKE", name=sample.NAME, birth_date=date(1990, 1, 1),
                                    residence_region="전주시", program=program, income_percent=sheet.income_percent)
    result = run_pipeline(applicant, to_engine_documents([payment]), [requirement])
    assert result.status.value == "NEEDS_REVIEW"
    assert all(finding.code.value != "INCOME_OVER_THRESHOLD" for finding in result.stage2.findings)


def test_missing_confidence_legacy_payment_fact_keeps_supported_contract():
    payment, _ = payment_fact()
    for key in ("status", "confidence"):
        payment.pop(key)
    payment["fields"].pop("양식판독상태")
    qualification = {"doc_type": str(DocType.NHIS_QUALIFICATION), "fields": {"가구원수": "1"}}
    assert build_facts({}, [payment, qualification]).monthly_premium == 50000


def legacy_payment_pages(kind, *, incorrect=False):
    from engine_v2.tests.test_nhis_extractors import payment_pages, month_only_payment_pages

    if kind == "month-only":
        return month_only_payment_pages((2025, 10), [10, 11, 12], mismatch=incorrect)
    pages = payment_pages()
    if incorrect:
        for _, result in pages:
            for word in result.words:
                if word.text == "330,000":
                    word.text = "330,001"
    return pages


@pytest.mark.parametrize("kind", ["legacy", "month-only"])
@pytest.mark.parametrize("incorrect", [False, True])
def test_legacy_payment_sum_failure_controls_direct_verdict_and_financial_trust(kind, incorrect):
    pages = legacy_payment_pages(kind, incorrect=incorrect)
    result = _from_nhis(nhis_payment.extract(pages), pages, V2DocType)
    requirement = DocRequirement("nhis_payment", DocType.NHIS_PAYMENT, "가상납부확인서")
    verdict = check_document(requirement, result, identity=Identity("김전북", date(1999, 1, 1)))
    assert verdict.status == ("NEEDS_REVIEW" if incorrect else "PASS")
    assert "양식판독상태" not in result.fields
    payment = {"doc_type": str(DocType.NHIS_PAYMENT), "fields": result.fields,
               "confidence": result.confidence, "status": verdict.status,
               "image_quality": 1, "issue_date": result.issue_date, "file_format": "pdf"}
    qualification = {"doc_type": str(DocType.NHIS_QUALIFICATION), "fields": {"가구원수": "1"}}
    facts = build_facts({}, [payment, qualification], ["2025-10", "2025-11", "2025-12"])
    assert (facts.monthly_premium is None) == incorrect
    program = PROGRAMS[DOUBLE_SAVINGS]
    applicant = to_engine_applicant(application_no="FAKE", name="김전북", birth_date=date(1999, 1, 1),
                                    residence_region="전주시", program=program, income_percent=90)
    pipeline = run_pipeline(applicant, to_engine_documents([payment]), [requirement])
    assert pipeline.status.value == ("NEEDS_REVIEW" if incorrect else "PASS")


@pytest.mark.parametrize("kind", ["legacy", "month-only"])
@pytest.mark.parametrize("incorrect", [False, True])
def test_legacy_payment_sum_failure_reaches_actual_text_layer_upload(
        kind, incorrect, client, tmp_path, monkeypatch):
    pages = legacy_payment_pages(kind, incorrect=incorrect)
    cells = [(word.bbox_px[0] / 10, word.bbox_px[1] / 14, word.text) for word in pages[0][1].words]
    path = text_pdf(tmp_path / "FAKE-legacy-payment.pdf", cells)
    monkeypatch.setenv("ENGINE_V2_OCR", "off")
    aid = new_app(client, name="김전북", birth="1999-01-01")
    response = client.post(f"/api/applications/{aid}/documents",
                           files={"file": ("FAKE-quarter.pdf", path.read_bytes(), "application/pdf")},
                           data={"slot_key": "nhis_payment", "declared_issue_date": "2026-11-10"})
    assert response.status_code == 200
    assert response.json()["status"] == ("NEEDS_REVIEW" if incorrect else "PASS")
    if incorrect:
        assert all(finding["severity"] != "FAIL" for finding in response.json()["findings"])


@pytest.mark.parametrize("field", ["purpose", "workplace"])
@pytest.mark.parametrize("header", ["성명", "보험료"])
def test_header_only_payment_values_reach_review_in_direct_read_and_upload(
        field, header, client, tmp_path, monkeypatch):
    cells, size = sample.payment(workplace=header if field == "workplace" else "")
    if field == "purpose":
        cells = [(*cell[:4], header if cell[4] == "납부확인용" else cell[4], cell[5]) for cell in cells]
    use_own_words(monkeypatch, cells, size)
    path = image_pdf(tmp_path / "FAKE-header-only-value.pdf", size)
    direct = read_document(str(path))
    assert direct.fields["양식판독상태"] == "불완전"
    assert direct.confidence <= .4
    response, stored = upload(client, new_app(client, name=sample.NAME, birth=sample.BIRTH), path, "nhis_payment")
    assert response["status"] == "NEEDS_REVIEW"
    assert stored["fields"]["양식판독상태"] == "불완전"
    assert all(finding["severity"] != "FAIL" for finding in response["findings"])


@pytest.mark.parametrize("key", ["성명", "생년월일", "발급일", "용도구분", "사업장명칭"])
def test_final_shared_filter_cannot_leave_payment_complete_after_required_value_removal(monkeypatch, key):
    import demo.backend.ocr as chain

    cells, size = sample.payment()
    pages = [sample.page(cells, size=size)]
    result = _from_nhis(nhis_payment.extract(pages), pages, V2DocType)
    result.fields[key] = "성명"
    monkeypatch.setattr(chain, "CHAIN", [SimpleNamespace(read=lambda *_: result)])
    final = read_document("FAKE-unused.pdf")
    assert key not in final.fields
    assert final.fields["양식판독상태"] == "불완전"
    assert f"{key}_required" in final.fields["판독검증실패"]
    assert final.confidence <= .4


@pytest.mark.parametrize("failed_check", ["monthly_amounts_numeric", "months_continuous",
                                         "monthly_total_matches", "paid_total_matches"])
def test_cached_legacy_payment_failed_checks_override_old_pass_without_deleting_saved_data(failed_check):
    payment, requirement = payment_fact(high=True)
    payment["fields"].pop("양식판독상태")
    payment["fields"]["판독검증실패"] = failed_check
    row = models.Document(application_id=1, slot_key="nhis_payment", file_path="storage/FAKE.pdf",
                          file_format="pdf", doc_type=str(DocType.NHIS_PAYMENT), stage1_status="PASS",
                          ocr_json={"confidence": .95, "image_quality": 1, "issue_date": sample.ISSUE,
                                    "fields": payment["fields"]})
    fact = document_fact(row)
    qualification = {"doc_type": str(DocType.NHIS_QUALIFICATION), "fields": {"가구원수": "1"}}
    facts = build_facts({}, [fact, qualification], ["2025-10", "2025-11", "2025-12"])
    assert facts.monthly_premium is None
    converted = to_engine_documents([fact])
    assert converted[0].ocr_confidence <= .4
    program = PROGRAMS[DOUBLE_SAVINGS]
    sheet = score_application(facts, announcement_date=program.announcement_date, age_basis_date=program.age_basis_date)
    applicant = to_engine_applicant(application_no="FAKE", name=sample.NAME, birth_date=date(1990, 1, 1),
                                    residence_region="전주시", program=program, income_percent=sheet.income_percent)
    result = run_pipeline(applicant, converted, [requirement])
    assert result.status.value == "NEEDS_REVIEW"
    assert all(finding.code.value != "INCOME_OVER_THRESHOLD" for finding in result.stage2.findings)
    assert row.stage1_status == "PASS"
    assert row.ocr_json["confidence"] == .95
    assert row.ocr_json["fields"]["판독검증실패"] == failed_check

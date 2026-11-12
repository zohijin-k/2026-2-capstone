"""Business proofs traverse actual uploads, identity checks and persistence."""
from copy import deepcopy
from datetime import date
import json

import pytest

from demo.backend.ocr import read_document
from demo.backend.rules.doc_check import check_document
from demo.backend.rules.doc_types import DocType
from demo.backend.rules.identity import Identity
from demo.backend.rules.required_docs import DocRequirement
from demo.backend.tests.test_p2_nhis_uploads import image_pdf, use_own_words
from demo.backend.tests.test_portal_uploads import client, new_app, upload
from engine_v2.tests import p2_business_samples as sample


def business_app(client, *, name=sample.NAME, birth=sample.BIRTH):
    aid = new_app(client, name=name, birth=birth)
    response = client.put(f"/api/applications/{aid}/doc-context", json={"work_category": "사업소득 사업자"})
    assert response.status_code == 200
    return aid


@pytest.mark.parametrize("count", [0, 1, 3, 10])
@pytest.mark.parametrize("multiline", [False, True])
def test_own_proof_upload_reads_complete_fields_and_matches_identity(client, tmp_path, monkeypatch, count, multiline):
    cells, size = sample.business(joint_count=count, multiline=multiline)
    use_own_words(monkeypatch, cells, size)
    path = image_pdf(tmp_path / "FAKE-arbitrary-image.pdf", size)
    direct = read_document(str(path), DocType.NHIS_ACQUISITION_LOSS)
    assert direct.detected_doc_type is DocType.BIZ_REG_PROOF
    assert direct.fields["양식판독상태"] == "완전"
    assert not direct.fields.get("판독검증실패")
    assert not direct.fields.get("판독경고")
    assert direct.fields["성명"] == sample.NAME
    assert direct.fields["생년월일"] == sample.BIRTH
    assert direct.fields["공동사업자유무"] == ("있음" if count else "없음")
    assert json.loads(direct.fields["업태"])[0] == "가상업종가"
    assert direct.issue_date == date(2026, 3, 3)
    response, saved = upload(client, business_app(client), path, "work_proof", filename="FAKE-renamed.pdf")
    assert response["status"] == "PASS"
    assert response["findings"] == []
    assert saved["fields"] == direct.fields
    assert saved["engine"] == "own"
    assert saved["confidence"] >= .85
    assert "654321" not in json.dumps(saved, ensure_ascii=False)
    assert not {"사업장소재지", "업태", "종목"}.intersection(response["extracted"])


@pytest.mark.parametrize("defect", ["checksum", "corporate", "corporate-label", "missing-name", "missing-birth", "missing-date",
                                  "missing-label", "partial-joint", "conflicting-joint", "duplicate-date",
                                  "wrong-name", "wrong-birth"])
def test_incomplete_or_uncertain_proofs_are_reviewed_without_fail(client, tmp_path, monkeypatch, defect):
    cells, size = sample.business(noise=False)
    replacements = {
        "checksum": (sample.NUMBER, "123-45-67890"),
        "corporate": (sample.NUMBER, sample.CORPORATE_NUMBER),
        "corporate-label": ("(일반과세자)", "(법인사업자)"),
    }
    if defect in replacements:
        before, after = replacements[defect]
        cells = [(*cell[:4], after, cell[5]) if cell[4] == before else cell for cell in cells]
    elif defect in {"missing-name", "missing-birth", "missing-date", "missing-label"}:
        value = {"missing-name": sample.NAME, "missing-birth": "900101-1654321", "missing-date": "2026년 3월 3일",
                 "missing-label": "사업자등록번호"}[defect]
        cells = [cell for cell in cells if cell[4] != value]
    elif defect in {"partial-joint", "conflicting-joint"}:
        cells.append(sample.cell(867, 1690, 1047, 1735, "이합성", .99))
        if defect == "conflicting-joint":
            cells.append(sample.cell(1445, 1690, 1740, 1735, "910202-2******", .99))
    elif defect == "duplicate-date":
        cells.append(sample.cell(1311, 2190, 1567, 2234, "2026년 3월 3일", .99))
    use_own_words(monkeypatch, cells, size)
    path = image_pdf(tmp_path / "FAKE-damaged-image.pdf", size)
    aid = business_app(client, name="이합성" if defect == "wrong-name" else sample.NAME,
                       birth="1991-02-02" if defect == "wrong-birth" else sample.BIRTH)
    response, saved = upload(client, aid, path, "work_proof")
    assert response["status"] == "NEEDS_REVIEW"
    assert response["findings"]
    assert all(finding["severity"] != "FAIL" for finding in response["findings"])
    if defect not in {"wrong-name", "wrong-birth"}:
        assert saved["confidence"] <= .4
        assert saved["fields"]["양식판독상태"] == "불완전"
        assert saved["fields"]["판독검증실패"]
    if defect in {"corporate", "corporate-label"}:
        assert "생년월일" not in saved["fields"]


def test_text_layer_proof_uses_same_fields_under_arbitrary_names(client, tmp_path, monkeypatch):
    cells, size = sample.business(representative_role="대표자", multiline=True)
    path = sample.text_pdf(tmp_path / "FAKE-random.pdf", cells, size)
    monkeypatch.setenv("ENGINE_V2_OCR", "off")
    direct = read_document(str(path), DocType.RESIDENT_ABSTRACT)
    assert direct.detected_doc_type is DocType.BIZ_REG_PROOF
    assert direct.engine == "pdftext"
    assert direct.fields["양식판독상태"] == "완전"
    assert direct.fields["성명"] == sample.NAME
    response, saved = upload(client, business_app(client), path, "work_proof")
    assert response["status"] == "PASS"
    assert not response["findings"]
    assert saved["fields"] == direct.fields


@pytest.mark.parametrize("identity", [None, Identity("이합성", date(1990, 1, 1)), Identity(sample.NAME, date(1991, 2, 2))])
def test_missing_or_different_applicant_identity_stays_reviewed_at_high_confidence(tmp_path, monkeypatch, identity):
    cells, size = sample.business()
    use_own_words(monkeypatch, cells, size)
    path = image_pdf(tmp_path / "FAKE-proof.pdf", size)
    direct = read_document(str(path))
    assert direct.confidence >= .85
    requirement = DocRequirement(slot_key="work_proof", doc_type=DocType.BIZ_REG_PROOF,
                                 label="사업자등록증명", min_issue_date=date(2027, 1, 1))
    decision = check_document(requirement, direct, date(2026, 3, 3), identity=identity)
    assert decision.status == "NEEDS_REVIEW"
    assert all(finding.severity != "FAIL" for finding in decision.findings)


@pytest.mark.parametrize("key", ["성명", "대표자성명", "생년월일", "발급일", "사업자등록번호", "업태", "공동사업자유무"])
def test_final_guard_invalidates_stale_completeness_after_field_safety(tmp_path, monkeypatch, key):
    import demo.backend.ocr as chain

    cells, size = sample.business()
    use_own_words(monkeypatch, cells, size)
    path = image_pdf(tmp_path / "FAKE-proof.pdf", size)
    direct = read_document(str(path))
    assert direct.fields["양식판독상태"] == "완전"
    mutated = deepcopy(direct)
    actual_key = "성명" if key == "대표자성명" else key
    mutated.fields[actual_key] = key if actual_key == "성명" else ""

    class Prepared:
        def read(self, *_):
            return mutated

    monkeypatch.setattr(chain, "CHAIN", [Prepared()])
    final = read_document(str(path))
    assert final.fields["양식판독상태"] == "불완전"
    assert final.confidence <= .4
    assert actual_key + "_required" in final.fields["판독검증실패"]
    if key == "발급일":
        assert final.issue_date is None


def test_wrong_slot_keeps_existing_document_type_failure(client, tmp_path, monkeypatch):
    cells, size = sample.business()
    use_own_words(monkeypatch, cells, size)
    path = image_pdf(tmp_path / "FAKE-wrong-slot.pdf", size)
    response, _ = upload(client, business_app(client), path, "nhis_qualification")
    assert response["status"] == "FAIL"
    assert [finding["code"] for finding in response["findings"]] == ["WRONG_DOCUMENT_TYPE"]


def test_future_opening_metadata_does_not_add_an_employment_rule(client, tmp_path, monkeypatch):
    cells, size = sample.business()
    cells = [(*cell[:4], "2030년 01월 02일", cell[5]) if cell[4] == "2018년 01월 02일" else cell for cell in cells]
    use_own_words(monkeypatch, cells, size)
    path = image_pdf(tmp_path / "FAKE-future-opening.pdf", size)
    response, saved = upload(client, business_app(client), path, "work_proof")
    assert response["status"] == "PASS"
    assert response["findings"] == []
    assert saved["fields"]["개업일"] == "2030-01-02"


def test_final_guard_suppresses_birth_when_corporate_type_is_added(tmp_path, monkeypatch):
    import demo.backend.ocr as chain

    cells, size = sample.business()
    use_own_words(monkeypatch, cells, size)
    path = image_pdf(tmp_path / "FAKE-proof.pdf", size)
    direct = read_document(str(path))
    direct.fields["과세유형"] = "법인사업자"

    class Prepared:
        def read(self, *_):
            return direct

    monkeypatch.setattr(chain, "CHAIN", [Prepared()])
    result = read_document(str(path))
    assert "생년월일" not in result.fields
    assert result.fields["양식판독상태"] == "불완전"
    assert result.confidence <= .4


@pytest.mark.parametrize("extra", ["2025.01.01", "2026.13.01"])
def test_issuer_overlapping_date_evidence_stays_reviewed(client, tmp_path, monkeypatch, extra):
    cells, size = sample.business()
    cells.append(sample.cell(1311, 2240, 1567, 2284, extra, 1))
    use_own_words(monkeypatch, cells, size)
    path = image_pdf(tmp_path / "FAKE-overlapping-date.pdf", size)
    response, saved = upload(client, business_app(client), path, "work_proof")
    assert response["status"] == "NEEDS_REVIEW"
    assert all(finding["severity"] != "FAIL" for finding in response["findings"])
    assert saved["confidence"] <= .4
    assert "발급일" not in saved["fields"]


def test_dense_joint_rows_survive_column_skew_in_actual_upload(client, tmp_path, monkeypatch):
    from engine_v2.pipeline import ocr

    cells, size = sample.business(joint_count=10)
    use_own_words(monkeypatch, cells, size)
    monkeypatch.setitem(ocr.ENGINES, "own", lambda *_: sample.page(cells, size=size, jitter=3, skew=16)[1].words)
    path = image_pdf(tmp_path / "FAKE-dense-joint.pdf", size)
    response, saved = upload(client, business_app(client), path, "work_proof")
    assert response["status"] == "PASS"
    assert response["findings"] == []
    assert saved["fields"]["공동사업자유무"] == "있음"


def test_last_category_continuation_is_retained_in_actual_upload(client, tmp_path, monkeypatch):
    cells, size = sample.business(noise=False)
    cells.append(sample.cell(633, 1560, 1380, 1600, "|추가누락가상품목", .99))
    use_own_words(monkeypatch, cells, size)
    path = image_pdf(tmp_path / "FAKE-last-category.pdf", size)
    response, saved = upload(client, business_app(client), path, "work_proof")
    assert response["status"] == "PASS"
    assert response["findings"] == []
    assert json.loads(saved["fields"]["종목"])[-1] == "추가누락가상품목"


@pytest.mark.parametrize("defect", ["crossing-inside", "crossing-outside", "left-column"])
def test_unreadable_grid_boundary_reaches_actual_upload_review(client, tmp_path, monkeypatch, defect):
    cells, size = sample.business(noise=False)
    if defect == "left-column":
        extra = sample.cell(260, 1550, 500, 1590, "가상추가표제", .99)
    else:
        top = 1590 if defect == "crossing-inside" else 1605
        extra = sample.cell(633, top, 1380, top + 40, "|경계확인품목", .99)
    cells.append(extra)
    use_own_words(monkeypatch, cells, size)
    path = image_pdf(tmp_path / "FAKE-grid-boundary.pdf", size)
    response, saved = upload(client, business_app(client), path, "work_proof")
    assert response["status"] == "NEEDS_REVIEW"
    assert all(finding["severity"] != "FAIL" for finding in response["findings"])
    assert saved["confidence"] <= .4
    assert saved["fields"]["양식판독상태"] == "불완전"


@pytest.mark.parametrize("partial", [False, True])
def test_joint_name_left_of_centered_header_reaches_correct_upload_verdict(client, tmp_path, monkeypatch, partial):
    cells, size = sample.business(noise=False, joint_count=0 if partial else 1)
    cells = [cell for cell in cells if cell[4] != "이합성"]
    cells.append(sample.cell(650, 1690, 730, 1735, "이합성", .99))
    use_own_words(monkeypatch, cells, size)
    path = image_pdf(tmp_path / "FAKE-left-joint-name.pdf", size)
    response, saved = upload(client, business_app(client), path, "work_proof")
    assert response["status"] == ("NEEDS_REVIEW" if partial else "PASS")
    if partial:
        assert all(finding["severity"] != "FAIL" for finding in response["findings"])
        assert saved["confidence"] <= .4
    else:
        assert response["findings"] == []
        assert saved["fields"]["공동사업자유무"] == "있음"


@pytest.mark.parametrize("left,right", [(500, 620), (1100, 1400)])
def test_joint_word_crossing_side_or_number_cell_stays_reviewed(client, tmp_path, monkeypatch, left, right):
    cells, size = sample.business(noise=False, joint_count=1)
    cells = [(left, cell[1], right, cell[3], cell[4], cell[5]) if cell[4] == "이합성" else cell for cell in cells]
    use_own_words(monkeypatch, cells, size)
    path = image_pdf(tmp_path / "FAKE-joint-cell-boundary.pdf", size)
    response, saved = upload(client, business_app(client), path, "work_proof")
    assert response["status"] == "NEEDS_REVIEW"
    assert all(finding["severity"] != "FAIL" for finding in response["findings"])
    assert saved["fields"]["양식판독상태"] == "불완전"

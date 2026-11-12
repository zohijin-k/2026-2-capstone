"""Exact word-shape regressions through the actual LocalOcr image entry point."""
import pytest

from demo.backend.rules.doc_types import DocType
from engine_v2.tests import p2_shape3_samples as sample


@pytest.mark.parametrize("kind,detected,failures", [
    ("payment", DocType.NHIS_PAYMENT,
     {"payment_group_headers", "payment_component_headers", "payment_columns", "paid_total_matches"}),
    ("qualification", DocType.NHIS_QUALIFICATION,
     {"nhis_issue_location_unique", "발급일_consistent", "발급일_required"}),
    ("acquisition", DocType.NHIS_ACQUISITION_LOSS,
     {"발급일_consistent", "nhis_issue_location_unique", "recent_five_years_covered", "발급일_required"}),
])
def test_exact_shape_with_inferred_footer_reproduces_observed_failures(monkeypatch, tmp_path, kind, detected, failures):
    result = sample.read_image(monkeypatch, tmp_path, kind)
    assert result.detected_doc_type == detected
    assert {value.strip() for value in result.fields.get("판독검증실패", "").split(",")} == failures
    assert result.fields["양식판독상태"] == "불완전"
    assert result.confidence == .4
    assert result.fields["성명"] == sample.NAME
    assert result.fields["생년월일"] == sample.BIRTH


@pytest.mark.parametrize("kind", ["payment", "qualification", "acquisition"])
def test_same_geometry_with_normal_labels_already_passes(monkeypatch, tmp_path, kind):
    cells, _ = sample.document(kind)
    cells = [(*cell[:4], cell[4].replace("고지금액", "가상안내").replace("국민건강보험공단", "가상시험안내문구"), cell[5])
             if cell[1] in {2298, 3070, 3016} else cell for cell in cells]
    result = sample.read_image(monkeypatch, tmp_path, kind, cells=cells)
    assert result.fields["양식판독상태"] == "완전"
    assert not result.fields.get("판독검증실패")
    assert result.fields["발급일"] == sample.ISSUE


@pytest.mark.parametrize("kind,count,digest", [
    ("payment", 126, "a4e8083b9f45a69478585e98d7f4a38bffbe4780a7693cab2666fef3083a4354"),
    ("qualification", 47, "57f7292165306a939876ae686e18698962f6c2b6965d22bdc0e654d2c6894582"),
    ("acquisition", 49, "4a35cbae81ab6509c4d5016cbf6d05089f739c350a983fa982b63826a7f40ab6"),
])
def test_authored_data_preserves_every_source_box_order_confidence_and_word_shape(kind, count, digest):
    import hashlib
    import json
    import re

    words = getattr(sample, kind.upper() + "_WORDS")
    projected = []
    for x0, y0, x1, y1, text, confidence in words:
        if not text.startswith("["):
            text = re.sub("[A-Za-z]", "A", re.sub("[0-9]", "9", re.sub("[가-힣]", "가", text)))
        projected.append((x0, y0, x1, y1, text, confidence))
    assert len(projected) == count
    encoded = json.dumps(projected, ensure_ascii=False, separators=(",", ":")).encode()
    assert hashlib.sha256(encoded).hexdigest() == digest

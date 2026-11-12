"""Exact word-shape regressions through the actual LocalOcr image entry point."""
import pytest

from demo.backend.rules.doc_types import DocType
from engine_v2.tests import p2_shape3_samples as sample


@pytest.mark.parametrize("kind,detected", [
    ("payment", DocType.NHIS_PAYMENT),
    ("qualification", DocType.NHIS_QUALIFICATION),
    ("acquisition", DocType.NHIS_ACQUISITION_LOSS),
])
def test_exact_shape_is_complete_with_required_issue_date(monkeypatch, tmp_path, kind, detected):
    from datetime import date

    result = sample.read_image(monkeypatch, tmp_path, kind)
    assert result.detected_doc_type == detected
    assert not result.fields.get("판독검증실패")
    assert not result.fields.get("판독경고")
    assert result.fields["양식판독상태"] == "완전"
    assert result.fields["발급일"] == sample.ISSUE
    assert result.issue_date == date.fromisoformat(sample.ISSUE)
    assert result.confidence == (.9 if kind == "acquisition" else .95)
    assert result.fields["성명"] == sample.NAME
    assert result.fields["생년월일"] == sample.BIRTH
    assert sample.verdict(result).status == "PASS"


@pytest.mark.parametrize("kind", ["payment", "qualification", "acquisition"])
def test_same_geometry_with_normal_labels_already_passes(monkeypatch, tmp_path, kind):
    cells, _ = sample.document(kind)
    cells = [(*cell[:4], cell[4].replace("납부금액", "가상금액").replace("국민건강보험공단", "가상시험안내문구"), cell[5])
             if cell[1] in {2340, 2426, 3070, 3016} else cell for cell in cells]
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


def test_exact_acquisition_five_year_check_depends_on_issue_date_with_existing_gap_meaning():
    import json
    from datetime import date
    from engine_v2.extractors import nhis_acquisition_loss as reader

    cells, size = sample.document("acquisition")
    result = reader.extract([sample.page(cells, size=size)])
    history = json.loads(result.fields["자격이력자료"].value)
    assert history["period"] is None
    assert [(row["acquired"], row["lost"]) for row in history["rows"]] == [
        ("2024-01-01", None), ("2020-01-01", "2023-01-01"), ("2016-01-01", "2019-01-01")]
    rows = [(row.acquired, row.lost) for row in result.history]
    assert rows[2][1] < date(2021, 3, 3)
    assert rows[2][1] < rows[1][0] and rows[1][1] < rows[0][0]
    assert reader.history_covers_recent_years(date.fromisoformat(sample.ISSUE), None, rows)
    assert next(check.passed for check in result.validations if check.name == "recent_five_years_covered")
    without_issue = [cell for cell in cells if cell[1] != 2585]
    missing = reader.extract([sample.page(without_issue, size=size)])
    assert not next(check.passed for check in missing.validations if check.name == "recent_five_years_covered")
    assert "발급일" not in missing.fields

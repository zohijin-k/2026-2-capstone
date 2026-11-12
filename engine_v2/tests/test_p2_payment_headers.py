"""Payment headers use bounded text comparisons and retain eight ordered columns."""
import json

import pytest

from engine_v2.tests import p2_shape3_samples as sample


def split_words(cells, labels, *, vertical=False):
    result = []
    for x0, y0, x1, y1, text, confidence in cells:
        if text not in labels:
            result.append((x0, y0, x1, y1, text, confidence))
            continue
        chunks = list(text) if not vertical else [text[:len(text) // 2], text[len(text) // 2:]]
        for index, chunk in enumerate(chunks):
            if vertical:
                step = (y1 - y0) / len(chunks)
                box = (x0, y0 + index * step, x1, y0 + (index + 1) * step - 1)
            else:
                step = (x1 - x0) / len(chunks)
                box = (x0 + index * step, y0, x0 + (index + 1) * step - 1, y1)
            result.append((*box, chunk, confidence))
    return result


@pytest.mark.parametrize("vertical", [False, True])
@pytest.mark.parametrize("labels", [
    {"고지금액", "납부금액"},
    {"건강", "장기요양", "보험료"},
    {"보수외", "소득월액"},
    {"고지금액", "납부금액", "건강", "장기요양", "보험료", "보수외", "소득월액"},
])
def test_split_group_and_component_headers_keep_all_eight_columns(monkeypatch, tmp_path, vertical, labels):
    cells, _ = sample.document("payment")
    result = sample.read_image(monkeypatch, tmp_path, "payment", cells=split_words(cells, labels, vertical=vertical))
    assert result.fields["양식판독상태"] == "완전"
    assert not result.fields.get("판독검증실패")
    assert result.fields["사업장명칭"] == ""
    rows = json.loads(result.fields["월별납부내역"])
    assert len(rows) == 12
    assert all(len(row["고지"]) == len(row["납부"]) == 4 for row in rows)
    assert json.loads(result.fields["월별고지금액"])["2025-10"] == "100000"
    assert result.fields["납부총액"] == "170000"
    assert json.loads(result.fields["숫자형식교정"])


@pytest.mark.parametrize("defect", ["missing-component", "swapped-components", "extra-component", "unknown-digit", "one-digit"])
def test_partial_misordered_or_inconsistent_payment_stays_in_review(monkeypatch, tmp_path, defect):
    cells, _ = sample.document("payment")
    if defect == "missing-component":
        cells = [cell for cell in cells if cell[:2] != (741, 857)]
    elif defect == "swapped-components":
        cells = [(*cell[:4], "(요양)" if cell[4] == "(건강)" else "(건강)" if cell[4] == "(요양)" else cell[4], cell[5])
                 for cell in cells]
    elif defect == "extra-component":
        cells.append((1940, 838, 2040, 934, "건강보험료", 1))
    else:
        cells = [(*cell[:4], "A00,000" if defect == "unknown-digit" else "100,001", cell[5])
                 if cell[:2] == (337, 1490) else cell for cell in cells]
    result = sample.read_image(monkeypatch, tmp_path, "payment", cells=cells)
    assert result.fields["양식판독상태"] == "불완전"
    assert result.confidence <= .4
    failed = result.fields["판독검증실패"]
    if defect in {"missing-component", "swapped-components", "extra-component"}:
        assert "payment_component_headers" in failed and "payment_columns" in failed
    else:
        assert "monthly_total_matches" in failed
        assert "payment_column_1_sum" in failed

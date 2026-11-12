"""Confirmation dates retain occurrence uniqueness across OCR word/line splits."""
import pytest

from engine_v2.tests import p2_shape3_samples as sample


def fragmented(cells, kind, style):
    x, y, right, bottom = ((1114, 2726, 1375, 2789) if kind == "qualification"
                            else (1103, 2585, 1361, 2637))
    remaining = [cell for cell in cells if cell[:2] != (x, y)]
    if style == "same-line":
        y = 2635 if kind == "qualification" else 2475
        remaining.append((1500, y, 1780, y + 54, "2026.03.03", 1))
    elif style == "sentence-token":
        remaining = [(*cell[:4], cell[4] + " 2026.03.03", cell[5])
                     if "확인합니다" in cell[4] else cell for cell in remaining]
    elif style == "two-lines":
        remaining.extend([(x, y, right, y + 24, "2026년03월", 1),
                          (x, y + 32, right, bottom, "03일", 1)])
    elif style == "three-lines":
        remaining.extend([(x, y, right, y + 17, "2026년", 1),
                          (x, y + 20, right, y + 37, "03월", 1),
                          (x, y + 40, right, y + 57, "03일", 1)])
    else:
        values = ("2026", "년", "03", "월", "03", "일")
        remaining.extend((x + index * 40, y, x + index * 40 + 35, bottom, value, 1)
                         for index, value in enumerate(values))
    return remaining


@pytest.mark.parametrize("kind", ["qualification", "acquisition"])
@pytest.mark.parametrize("style", ["same-line", "sentence-token", "two-lines", "three-lines", "unit-words"])
def test_fragmented_issuing_date_with_repeated_notice_organization_is_unique(monkeypatch, tmp_path, kind, style):
    cells, _ = sample.document(kind)
    result = sample.read_image(monkeypatch, tmp_path, kind, cells=fragmented(cells, kind, style))
    assert result.fields["양식판독상태"] == "완전"
    assert not result.fields.get("판독검증실패")
    assert result.fields["발급일"] == sample.ISSUE


@pytest.mark.parametrize("kind", ["qualification", "acquisition"])
@pytest.mark.parametrize("defect", ["none", "duplicate", "invalid-second", "output-only", "request-only", "validity-only"])
def test_missing_competing_or_labeled_nonissue_dates_remain_reviewed(monkeypatch, tmp_path, kind, defect):
    cells, _ = sample.document(kind)
    y = 2726 if kind == "qualification" else 2585
    if defect in {"none", "output-only", "request-only", "validity-only"}:
        cells = [cell for cell in cells if cell[1] != y]
    if defect not in {"none"}:
        value = {"duplicate": "2026.03.03", "invalid-second": "2026.99.99",
                 "output-only": "출력일시 2026.03.03", "request-only": "자격확인요청일 2026.03.03",
                 "validity-only": "2026.03.03 까지 유효합니다."}[defect]
        cells.append((1110, y + 65, 1550, y + 115, value, 1))
    result = sample.read_image(monkeypatch, tmp_path, kind, cells=cells)
    assert result.fields["양식판독상태"] == "불완전"
    assert "nhis_issue_location_unique" in result.fields["판독검증실패"]
    assert "발급일" not in result.fields
    assert result.confidence <= .4

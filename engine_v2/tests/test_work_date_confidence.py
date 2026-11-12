"""Serialize the actual bounded date-token confidence for continuity consumers."""
import json

from engine_v2.extractors import insurance_4, nhis_acquisition_loss
from engine_v2.tests.nhis_form_samples import coordinate_page, insurance_portal_cells
from engine_v2.tests import p2_form_samples as sample


def test_portal_row_serializes_acquisition_token_confidence():
    page,result=coordinate_page(insurance_portal_cells())
    for word in result.words:
        if word.text=="2020.01.01":word.confidence=.4
    extracted=insurance_4.extract([(page,result)])
    rows=json.loads(extracted.fields["가입내역"].value)
    assert rows and all(row["자격취득일신뢰도"]==.4 for row in rows)


def test_nhis_history_serializes_scoped_acquisition_and_loss_confidence():
    cells,size=sample.acquisition(noise=False)
    cells=[(*cell[:5],.4) if cell[0]==1652 and cell[1]==1115 else cell for cell in cells]
    extracted=nhis_acquisition_loss.extract([sample.page(cells,size=size)])
    rows=json.loads(extracted.fields["자격이력자료"].value)["rows"]
    assert rows[0]["acquired_confidence"]==.4
    assert rows[0]["lost_confidence"] is None
    assert rows[1]["acquired_confidence"]==1 and rows[1]["lost_confidence"]==1

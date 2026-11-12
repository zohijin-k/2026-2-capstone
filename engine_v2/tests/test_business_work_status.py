"""Explicit status is bounded metadata, never a word in footer instructions."""
from datetime import date

import pytest

from engine_v2.extractors import business_registration as reader
from engine_v2.tests import p2_business_samples as sample


@pytest.mark.parametrize("status",["휴업","폐업","계속사업자"])
def test_explicit_high_confidence_metadata_status_is_extracted(status):
    cells,size=sample.business(noise=False)
    cells += [sample.cell(1200,520,1380,550,"사업자상태",1),
              sample.cell(1450,520,1650,550,status,1)]
    result=reader.extract([sample.page(cells,size=size)],today=date(2026,3,4))
    assert result.structure_complete
    assert result.fields["사업자상태"].value==status
    assert result.fields["사업자상태_상태"].value=="확인"


@pytest.mark.parametrize("label,top,confidence",[("사업자상태",520,.4),("안내",520,1),("사업자상태",2600,1)])
def test_uncertain_or_out_of_metadata_status_cannot_establish_closure(label,top,confidence):
    cells,size=sample.business(noise=False)
    cells += [sample.cell(1200,top,1380,top+30,label,1),
              sample.cell(1450,top,1650,top+30,"폐업",confidence)]
    result=reader.extract([sample.page(cells,size=size)],today=date(2026,3,4))
    assert "사업자상태" not in result.fields
    if label=="사업자상태" and top==520:
        assert result.fields["사업자상태_상태"].value=="못 읽음"

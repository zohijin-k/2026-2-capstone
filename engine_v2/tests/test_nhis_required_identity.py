"""Font-free regressions for header-as-name false acceptance."""
import pytest

from engine_v2.extractors import nhis_acquisition_loss
from engine_v2.tests.nhis_form_samples import NAME, coordinate_page


def test_name_below_header_is_read_instead_of_neighboring_rrn_header():
    result = nhis_acquisition_loss.extract([coordinate_page()])
    assert result.fields["성명"].value == NAME
    assert next(v.passed for v in result.validations if v.name == "성명_consistent")


def test_header_without_name_is_not_a_successful_identity_read():
    result = nhis_acquisition_loss.extract([coordinate_page(name=None)])
    assert "성명" not in result.fields
    assert not next(v.passed for v in result.validations if v.name == "성명_consistent")


@pytest.mark.parametrize("label", ["성명:가짜이름", "성명(가짜이름)", "성 명: 가짜이름"])
def test_existing_inline_name_tokens_keep_their_value(label):
    from engine_v2.tests.nhis_form_samples import acquisition_cells
    cells = [cell for cell in acquisition_cells() if cell[2] not in {"성명", NAME}]
    cells.append((28, 18, label))
    result = nhis_acquisition_loss.extract([coordinate_page(cells)])
    assert result.fields["성명"].value == NAME

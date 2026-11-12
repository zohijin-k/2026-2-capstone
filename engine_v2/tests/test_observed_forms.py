"""Regression acceptance tests for redacted shape-derived word layouts."""
import pytest
from engine_v2.extractors import nhis_acquisition_loss, nhis_qualification, insurance_4
from engine_v2.tests import observed_form_samples as sample

CASES = [(sample.acquisition, nhis_acquisition_loss),
         (sample.qualification, nhis_qualification), (sample.portal, insurance_4)]


@pytest.mark.xfail(strict=True, reason="Shape-derived layouts reproduce current reader failures")
@pytest.mark.parametrize("build,reader", CASES, ids=["A", "B", "C"])
def test_observed_normal(build, reader):
    result = reader.extract([sample.page(build())])
    assert result.fields["성명"].value == sample.NAME
    assert result.fields["생년월일"].value == sample.BIRTH
    assert result.fields["발급일"].value == sample.ISSUE
    assert all(check.passed for check in result.validations)
    assert result.structure_complete is True

"""Regression acceptance tests for redacted shape-derived word layouts."""
import pytest
from engine_v2.extractors import nhis_acquisition_loss, nhis_qualification, insurance_4
from engine_v2.tests import observed_form_samples as sample

CASES = [(sample.acquisition, nhis_acquisition_loss),
         (sample.qualification, nhis_qualification),
         pytest.param(sample.portal, insurance_4, marks=pytest.mark.xfail(strict=True))]


@pytest.mark.parametrize("build,reader", CASES, ids=["A", "B", "C"])
def test_observed_normal(build, reader):
    result = reader.extract([sample.page(build())])
    assert result.fields["성명"].value == sample.NAME
    assert result.fields["생년월일"].value == sample.BIRTH
    assert result.fields["발급일"].value == sample.ISSUE
    assert all(check.passed for check in result.validations)
    assert result.structure_complete is True


@pytest.mark.parametrize('name', ['가상', '가상인', '가상인물'])
@pytest.mark.parametrize('jitter', [0, 2])
@pytest.mark.parametrize('count', [3, 6, 9])
@pytest.mark.parametrize('long', [False, True])
def test_acquisition_geometry_variants(name, jitter, count, long):
    result = nhis_acquisition_loss.extract([sample.page(sample.acquisition(
        name=name, count=count, long=long), jitter=jitter)])
    assert result.structure_complete
    assert result.fields['성명'].value == name
    assert result.fields['생년월일'].value == sample.BIRTH
    assert result.fields['발급일'].value == sample.ISSUE
    assert len(result.history) == count
    assert all(v.passed for v in result.validations)
    assert result.history[0].employer == '가상회사 센터'


@pytest.mark.parametrize('replacement', ['', '성명', '주 민 등 록 번 호'])
def test_acquisition_empty_or_header_only_name_is_incomplete(replacement):
    result = nhis_acquisition_loss.extract([sample.page(sample.acquisition(name=replacement))])
    assert not result.structure_complete
    assert '성명' not in result.fields


@pytest.mark.parametrize('name', ['가상', '가상인', '가상인물'])
@pytest.mark.parametrize('jitter', [0, 2])
@pytest.mark.parametrize('count', [1, 2, 4])
def test_qualification_geometry_variants(name, jitter, count):
    import json
    result = nhis_qualification.extract([sample.page(sample.qualification(
        name=name, count=count), jitter=jitter)])
    assert result.structure_complete
    assert all(v.passed for v in result.validations)
    assert result.fields['성명'].value == name
    assert result.fields['생년월일'].value == sample.BIRTH
    assert result.fields['발급일'].value == sample.ISSUE
    members = json.loads(result.fields['가구원목록'].value)
    assert len(members) == count
    assert members[0] == {'성명': name, '생년월일': sample.BIRTH,
                          '자격취득일': '2020-01-01', '자격상실일': ''}


@pytest.mark.parametrize('replacement', ['', '성명', '주 민 등 록 번 호'])
def test_qualification_empty_or_header_only_name_cannot_publish_members(replacement):
    result = nhis_qualification.extract([sample.page(sample.qualification(name=replacement))])
    assert not result.structure_complete
    assert '성명' not in result.fields
    assert '가구원목록' not in result.fields

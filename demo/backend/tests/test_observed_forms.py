"""Shape-derived A/B/C contracts reach final decisions with fictitious values."""
from datetime import date
import pytest

from engine_v2.tests import observed_form_samples as s
from engine_v2.extractors import nhis_acquisition_loss as a, nhis_qualification as b, insurance_4 as c
from engine_v2.schemas.models import DocType as V2DocType
from demo.backend.ocr import localocr
from demo.backend.rules.doc_types import DocType
from demo.backend.rules.doc_check import check_document
from demo.backend.rules.required_docs import DocRequirement
from demo.backend.rules.identity import Identity

CASES = [(s.acquisition, a, DocType.NHIS_ACQUISITION_LOSS),
         (s.qualification, b, DocType.NHIS_QUALIFICATION), (s.portal, c, DocType.INSURANCE_4)]


def convert(cells, reader, jitter=0):
    # Uniformly scale word boxes with raster resolution; quality is independent
    # of the relative layout acceptance tested here.
    pages = [s.page(cells, jitter=jitter, scale=4)]
    ex = reader.extract(pages)
    return (localocr._from_insurance4(ex, pages) if reader == c else
            localocr._from_nhis(ex, pages, V2DocType))


def requirement(kind):
    return DocRequirement(slot_key='synthetic', doc_type=kind, label='가상 서류',
                          min_issue_date=date(2026, 3, 3))


@pytest.mark.parametrize('build,reader,kind', CASES, ids=['A', 'B', 'C'])
@pytest.mark.parametrize('name', ['가상', '가상인', '가상인물'])
@pytest.mark.parametrize('jitter', [0, 2])
@pytest.mark.parametrize('variant', [0, 1, 2])
def test_observed_complete_forms_pass_without_warnings(build, reader, kind, name, jitter, variant):
    options = {'name': name}
    if reader == a:
        options.update(count=[3, 6, 9][variant], long=variant > 0)
    elif reader == b:
        options.update(count=[1, 2, 4][variant])
    else:
        options.update(long=variant > 0)
    result = convert(build(**options), reader, jitter)
    assert result.fields['성명'] == name
    assert result.fields['생년월일'] == s.BIRTH
    assert result.fields['발급일'] == s.ISSUE
    assert result.fields['양식판독상태'] == '완전'
    assert '판독검증실패' not in result.fields
    decision = check_document(requirement(kind), result, identity=Identity(name, date(1990, 1, 1)))
    assert decision.status == 'PASS'
    assert decision.findings == []


@pytest.mark.parametrize('build,reader,kind', CASES, ids=['A', 'B', 'C'])
@pytest.mark.parametrize('defect', ['blank-name', 'header-name', 'birth', 'table'])
def test_observed_incomplete_forms_cannot_reach_false_pass_or_fail(build, reader, kind, defect):
    cells = build(name='' if defect == 'blank-name' else ('성명' if defect == 'header-name' else s.NAME))
    if defect == 'birth':
        cells = [cell for cell in cells if cell[4] != '900101-1******']
    if defect == 'table':
        label = '사업장명칭' if reader in (a, c) else '자격취득일'
        cells = [cell for cell in cells if cell[4] != label]
    result = convert(cells, reader)
    assert result.fields['양식판독상태'] == '불완전'
    assert result.confidence <= .4
    if defect in ('blank-name', 'header-name'):
        assert '성명' not in result.fields
        assert '성명_required' in result.fields['판독검증실패']
    decision = check_document(requirement(kind), result, identity=Identity(s.NAME, date(1990, 1, 1)))
    assert decision.status == 'NEEDS_REVIEW'
    assert all(f.severity != 'FAIL' for f in decision.findings)


def test_observed_notification_preserves_subscriber_member_and_absent_applicant_rules():
    result = convert(s.qualification(), b)
    req = requirement(DocType.NHIS_QUALIFICATION)
    payment = (str(DocType.NHIS_PAYMENT), {'성명': s.NAME, '생년월일': s.BIRTH})
    qualification = (str(DocType.NHIS_QUALIFICATION), result.fields)
    member = Identity('가상원', date(2001, 1, 1))
    assert check_document(req, result, identity=member, related_nhis_docs=[qualification]).status == 'NEEDS_REVIEW'
    paired = check_document(req, result, identity=member, related_nhis_docs=[payment, qualification])
    assert paired.status == 'PASS'
    assert paired.codes == ['NHIS_DEPENDENT_INSURED_PERSON']
    absent = check_document(req, result, identity=Identity('가상외', date(2000, 1, 1)),
                            related_nhis_docs=[payment, qualification])
    assert absent.status == 'NEEDS_REVIEW'
    assert absent.codes == ['NHIS_SUBSCRIBER_IDENTITY_REVIEW']


@pytest.mark.parametrize('build,reader,kind', CASES, ids=['A', 'B', 'C'])
@pytest.mark.parametrize('jitter', [0, 2])
def test_observed_image_route_ignores_filename_and_expected_slot(tmp_path, monkeypatch, build, reader, kind, jitter):
    from dataclasses import replace
    from PIL import Image
    page, words = s.page(build(), jitter=jitter, scale=4, image=True)
    original = list(localocr._import_v2())
    original[3] = lambda *args: words
    original[5] = lambda *args: [replace(page, png=b'synthetic')]
    monkeypatch.setattr(localocr, '_import_v2', lambda: tuple(original))
    monkeypatch.setattr(localocr, '_merge_image_heuristics', lambda *args: None)
    monkeypatch.setenv('ENGINE_V2_OCR', 'fake')
    path = tmp_path / 'arbitrary.png'
    Image.new('RGB', (50, 50), 'white').save(path)
    result = localocr.LocalOcr().read(str(path), DocType.RESIDENT_ABSTRACT)
    assert result is not None
    assert result.detected_doc_type == kind
    assert result.fields['양식판독상태'] == '완전'
    assert check_document(requirement(kind), result, identity=Identity(s.NAME, date(1990, 1, 1))).status == 'PASS'

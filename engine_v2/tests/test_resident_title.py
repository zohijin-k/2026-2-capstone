"""Coordinate title fallback cannot promote lower or side combined notices."""
import pytest
from engine_v2.pipeline.resident_title import classify_resident_title
from engine_v2.extractors import resident_abstract as ra
from engine_v2.schemas.models import DocType
from engine_v2.tests import observed_form_samples as s


@pytest.mark.parametrize('kind,expected', [('초본', 'abstract'), ('등본', 'register')])
@pytest.mark.parametrize('opening', ['', '(', 'C', '9', '가'])
@pytest.mark.parametrize('jitter', [0, 3])
def test_split_large_title(kind, expected, opening, jitter):
    pages = [s.page(s.resident(kind=kind, opening=opening), size=(2065, 2923), jitter=jitter, image=True)]
    result, evidence = classify_resident_title(pages)
    assert result == expected
    assert '좌표 제목 규칙' in evidence
    ex = ra.extract(pages)
    assert ex.detected_type == (DocType.RESIDENT_ABSTRACT if kind == '초본' else DocType.RESIDENT_REGISTER)
    if opening != '(':
        assert '좌표 제목 규칙' in ex.classification_evidence


@pytest.mark.parametrize('options', [{'main': False}, {'subtitle': False}, {'combined': True}])
def test_missing_or_ambiguous_title_stays_unknown(options):
    pages = [s.page(s.resident(**options), size=(2065, 2923))]
    assert classify_resident_title(pages)[0] is None
    assert ra.extract(pages).detected_type == DocType.UNKNOWN


def test_prior_title_layout_keeps_abstract():
    pages = [s.page(s.resident(prior=True, opening='('), size=(2066, 2923))]
    assert ra.extract(pages).detected_type == DocType.RESIDENT_ABSTRACT


def test_small_title_or_title_in_lower_body_is_not_evidence():
    for change in ('small', 'lower'):
        cells = s.resident()
        if change == 'lower':
            cells = [(x, y + 1200, a, b + 1200, t) if y < 380 else (x, y, a, b, t)
                     for x, y, a, b, t in cells]
        else:
            cells = [(x, y, a, y + 30, t) if t in ('주 민 등 록 표', '초', '본') else (x, y, a, b, t)
                     for x, y, a, b, t in cells]
        assert classify_resident_title([s.page(cells, size=(2065, 2923))])[0] is None


def test_fragmented_main_and_right_hand_subtitle_use_coordinates():
    cells = s.resident(subtitle=False)
    cells = [c for c in cells if c[4] != '주 민 등 록 표']
    cells += s.spaced(292, 207, '주민등록표', size=75, step=110)
    cells.append(s.word(865, 210, 150, '초 본', 70))
    assert classify_resident_title([s.page(cells, size=(2065, 2923))])[0] == 'abstract'


def test_side_notice_and_footer_only_are_not_subtitle_evidence():
    cells = s.resident(subtitle=False)
    cells += [s.word(960, 300, 300, '초 본 등 본', 65)]
    assert classify_resident_title([s.page(cells, size=(2065, 2923))])[0] is None

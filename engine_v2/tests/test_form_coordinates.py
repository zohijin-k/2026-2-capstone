"""Word-only comparison and body-gap column contracts."""
from engine_v2.extractors import nhis_forms as forms, nhis_common as common
from engine_v2.tests import observed_form_samples as s


def test_spaced_labels_compare_without_modifying_words():
    page, ocr = s.page(s.spaced(10, 10, '주민등록번호'))
    lines = common.page_lines(page, ocr)
    before = [w.text for w in lines[0]]
    assert len(forms.label_hits(lines, ('주민등록번호',))) == 1
    assert [w.text for w in lines[0]] == before
    assert not forms.label_hits(common.page_lines(*s.page([
        s.word(10, 10, 10, '성'), s.word(130, 10, 10, '명')])), ('성명',))


def test_columns_follow_body_gaps_instead_of_header_starts():
    page, ocr = s.page(s.acquisition(long=True))
    lines = common.page_lines(page, ocr)
    header = next(row for row in lines if forms.label_hits([row], ('No',)))
    labels = ('No', '가입자구분', '사업장명칭', '자격취득일', '자격상실일')
    headers = [forms.label_hits([header], (label,))[0][1] for label in labels]
    body = [row for row in lines if 31 < row[0].cy < 67]
    bounds = forms.table_columns(headers, body)
    assert bounds is not None
    cells = forms.column_cells(body[0], bounds)
    assert common.line_text(cells[1]) == '직장가입자'
    assert common.line_text(cells[2]) == '가상회사 센터'


def test_ambiguous_body_corridors_do_not_guess_columns():
    page, ocr = s.page([s.word(10, 10, 10, '첫째'), s.word(90, 10, 10, '둘째'),
                        s.word(10, 30, 10, '가상'), s.word(50, 30, 10, '중간'),
                        s.word(90, 30, 10, '가상')])
    lines = common.page_lines(page, ocr)
    assert forms.table_columns([[lines[0][0]], [lines[0][1]]], [lines[1]]) is None

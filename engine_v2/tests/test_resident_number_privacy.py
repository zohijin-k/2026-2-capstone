"""Fictitious resident identifiers exercise ingestion and metadata boundaries."""
from dataclasses import asdict
from datetime import date
import json

import pytest

from engine_v2.engine import _load_pages
from engine_v2.extractors import job_common, nhis_acquisition_loss, nhis_common
from engine_v2.pipeline import ocr
from engine_v2.pipeline.privacy import mask_data, mask_markup_rrn, mask_rrn
from engine_v2.pipeline.preprocess import preprocess
from engine_v2.schemas.models import DocType, DocumentInput
from engine_v2.tests.nhis_form_samples import acquisition_cells, coordinate_page, text_pdf


FRONT = "900101"
SUFFIX = "654321"
RRN = f"{FRONT}-1{SUFFIX}"


@pytest.mark.parametrize("separator", ["", "-", "–", "—", "－", " ", " - ", "\n"])
@pytest.mark.parametrize("sex", [1, 2, 3, 4, 5, 6, 7, 8])
def test_date_and_sex_are_retained_with_each_supported_separator(separator, sex):
    source = f"주민등록번호 {FRONT}{separator}{sex}{SUFFIX}"
    masked = mask_rrn(source)
    assert masked == f"주민등록번호 {FRONT}{separator}{sex}******"
    assert mask_rrn(masked) == masked


@pytest.mark.parametrize("source", [
    "123-45-67890", "12345678901", "1234-567-8901-234",
    "1234-5678-9012-34567", "0-0000-20260303-000000", "G9001011654321000000",
    "G9001011654321 00000",
    "9001011654321000000", "991332-1654321", "000229-1654321", "900101-9654321",
])
def test_other_identifiers_and_invalid_resident_shapes_are_preserved(source):
    assert mask_rrn(source) == source


def test_split_words_are_masked_without_changing_geometry_confidence_or_order():
    words = [ocr.OcrWord("1654321", .68, (180, 100.5, 250, 121)),
             ocr.OcrWord("900101-", .99, (100, 100, 170, 120))]
    geometry = [(word.bbox_px, word.confidence) for word in words]
    result = ocr.OcrResult("own", words)
    assert [word.text for word in result.words] == ["1******", "900101-"]
    assert [(word.bbox_px, word.confidence) for word in words] == geometry
    assert SUFFIX not in repr(result)
    assert SUFFIX not in json.dumps(asdict(result))


def test_distant_columns_do_not_form_a_resident_number():
    words = [ocr.OcrWord(FRONT, .99, (0, 0, 60, 10)),
             ocr.OcrWord("1" + SUFFIX, .99, (900, 0, 970, 10))]
    result = ocr.OcrResult("own", words)
    assert [word.text for word in result.words] == [FRONT, "1" + SUFFIX]


def test_split_words_with_different_heights_and_tilt_are_masked():
    words = [ocr.OcrWord(FRONT + "-", .99, (0, 0, 70, 14)),
             ocr.OcrWord("1" + SUFFIX, .66, (73, 8, 143, 14))]
    result = ocr.OcrResult("own", words)
    assert SUFFIX not in repr(result)


@pytest.mark.parametrize("separator", ["", " ", "-", " – "])
def test_nhis_birth_uses_retained_prefix_for_each_separator(separator):
    assert nhis_common.birth_from_rrn(mask_rrn(FRONT + separator + "1" + SUFFIX)) == date(1990, 1, 1)


@pytest.mark.parametrize("markup", [
    "<p><span>900101-</span><span>1654321</span></p>",
    "<table><tr><td><span>900101-</span><span>1654321</span></td></tr></table>",
    "<p>900101-1&#54;&#53;&#52;&#51;&#50;&#49;</p>",
])
def test_markup_and_encoded_digits_cannot_reintroduce_suffixes(markup):
    from engine_v2.pipeline import jbai_ocr

    safe = mask_markup_rrn(markup)
    assert SUFFIX not in safe
    assert "******" in safe
    parsed = [*jbai_ocr._text_lines(safe),
              *(cell.text for table in jbai_ocr.parse_html_tables(safe)
                for row in table.rows for cell in row)]
    assert SUFFIX not in repr(parsed)


@pytest.mark.parametrize("markup", [
    "<table><tr><td>900101</td><td>1654321</td></tr></table>",
    "<p>900101</p><p>1654321</p>",
    "<fcel>900101<fcel>1654321<nl>",
])
def test_unrelated_block_or_table_numbers_are_preserved(markup):
    assert mask_markup_rrn(markup) == markup


@pytest.mark.parametrize("engine", ["own", "applevision", "easyocr", "paddle"])
def test_all_coordinate_engines_mask_split_words_and_errors(monkeypatch, engine):
    def output(*_):
        return [ocr.OcrWord(FRONT + "-", .99, (10, 10, 80, 30)),
                ocr.OcrWord("1" + SUFFIX, .99, (85, 11, 155, 31))]

    monkeypatch.setitem(ocr.ENGINES, engine, output)
    result = ocr.run_ocr(engine, b"FAKE-image", (200, 300))
    assert result.text == FRONT + "- 1******"
    assert SUFFIX not in repr(result)

    def fail(*_):
        raise ValueError(RRN)

    monkeypatch.setitem(ocr.ENGINES, engine, fail)
    assert SUFFIX not in ocr.run_ocr(engine, b"FAKE-image", (200, 300)).error


def test_text_layer_page_words_raw_text_and_birth_are_safe(tmp_path):
    cells = [(x, y, RRN if value == "900101-1******" else value)
             for x, y, value in acquisition_cells()]
    path = text_pdf(tmp_path / "FAKE-privacy.pdf", cells)
    raw_pages = preprocess(path)
    assert SUFFIX not in repr(raw_pages)
    pages = _load_pages(DocumentInput(doc_id="FAKE", declared_type=DocType.NHIS_ACQUISITION_LOSS,
                                    file_path=str(path)), "own")
    assert isinstance(pages, list)
    assert SUFFIX not in repr(pages)
    result = nhis_acquisition_loss.extract(pages, today=date(2026, 3, 4))
    assert result.fields["생년월일"].value == "1990-01-01"
    assert SUFFIX not in repr(result)


@pytest.mark.parametrize("split", [False, True])
def test_job_document_birth_fallback_survives_earlier_redaction(split):
    cells = [(10, 10, "900101-"), (16.5, 10, "1654321")] if split else [(10, 10, RRN)]
    page, result = coordinate_page(cells)
    lines, birth = job_common.page_lines([(page, result)])
    assert birth == date(1990, 1, 1)
    assert SUFFIX not in repr(lines)
    assert SUFFIX not in repr(result)


def test_nested_values_are_sanitized_without_changing_numeric_types():
    source = {"raw": RRN, "values": [{"evidence": RRN}], "count": 12, "date": date(2026, 3, 3)}
    safe = mask_data(source)
    assert safe["raw"] == FRONT + "-1******"
    assert safe["count"] == 12 and safe["date"] == date(2026, 3, 3)
    assert SUFFIX not in repr(safe)

"""Complete ingestion context preserves document IDs and removes resident suffixes."""
from dataclasses import asdict
from datetime import date
import json

import pytest

from engine_v2.extractors import resident_abstract
from engine_v2.engine import _load_pages
from engine_v2.schemas.models import DocType, DocumentInput
from engine_v2.tests.nhis_form_samples import acquisition_cells, text_pdf
from engine_v2.pipeline import ocr
from engine_v2.pipeline.jbai_ocr import parse_html_tables, parse_otsl_tables
from engine_v2.pipeline.privacy import mask_markup_rrn, mask_rrn
from engine_v2.tests.test_resident_abstract import build


SUFFIX = "654321"
RRN = "900101-1" + SUFFIX
G_NUMBER = "G9001011" + SUFFIX + "00000"


@pytest.mark.parametrize("prefix", ["RRN", "REG", "TAG", "ID"])
@pytest.mark.parametrize("separator", ["-", "", " "])
def test_merged_ascii_labels_do_not_exempt_resident_shapes(prefix, separator):
    text = prefix + "900101" + separator + "1" + SUFFIX
    expected = prefix + "900101" + separator + "1******"
    assert mask_rrn(text) == expected
    result = ocr.OcrResult("own", [ocr.OcrWord(text, .99, (10, 10, 200, 30))])
    assert result.words[0].text == expected
    assert SUFFIX not in json.dumps(asdict(result))


@pytest.mark.parametrize("parts", [[G_NUMBER], [G_NUMBER[:14], G_NUMBER[14:]],
                                  ["G", G_NUMBER[1:14], G_NUMBER[14:]],
                                  ["G", G_NUMBER[1:7], G_NUMBER[7:14], G_NUMBER[14:]]])
def test_complete_word_batch_preserves_every_split_of_g_plus_eighteen_digits(parts):
    text = " ".join(parts)
    assert mask_rrn(text) == text
    words = [ocr.OcrWord(part, .99, (index * 80, 10, index * 80 + 75, 30))
             for index, part in enumerate(parts)]
    result = ocr.OcrResult("own", words)
    assert [word.text for word in result.words] == parts


@pytest.mark.parametrize("engine", ["own", "applevision", "easyocr", "paddle"])
def test_public_coordinate_ingress_masks_ascii_rrn_and_preserves_split_g_number(monkeypatch, engine):
    parts = [G_NUMBER[:14], G_NUMBER[14:]]

    def recognize(*_):
        return [ocr.OcrWord(parts[0], .99, (0, 0, 140, 20)),
                ocr.OcrWord(parts[1], .99, (145, 0, 195, 20)),
                ocr.OcrWord("RRN" + RRN, .99, (0, 40, 200, 60))]

    monkeypatch.setitem(ocr.ENGINES, engine, recognize)
    result = ocr.run_ocr(engine, b"FAKE", (300, 400))
    assert [word.text for word in result.words[:2]] == parts
    assert result.words[2].text == "RRN900101-1******"
    assert G_NUMBER in "".join(word.text for word in result.words[:2])
    assert "RRN" + RRN not in repr(result)


def test_suffix_line_breaks_are_redacted_without_leaving_reconstructable_digits():
    source = "900101-16\n54\r\n321"
    masked = mask_rrn(source)
    assert "".join(character for character in masked if character.isdigit()) == "9001011"
    assert masked.count("*") == 6


@pytest.mark.parametrize("markup", [
    "<p><span>G9001011654321</span><span>00000</span></p>",
    "<table><tr><td><span>G9001011654321</span><span>00000</span></td></tr></table>",
    "<fcel>G9001011654321<lcel>00000<nl>",
])
def test_markup_keeps_full_g_identifier_context_across_inline_fragments(markup):
    assert mask_markup_rrn(markup) == markup


def test_markup_masks_attribute_values_as_well_as_visible_resident_text():
    markup = f'<p title="RRN{RRN}">RRN{RRN}</p>'
    assert SUFFIX not in mask_markup_rrn(markup)


@pytest.mark.parametrize("token", ["lcel", "xcel"])
def test_completed_otsl_cells_redact_resident_fragments_and_preserve_g_fragments(token):
    resident = f"<fcel>900101-<{token}>1654321<nl>"
    document = f"<fcel>{G_NUMBER[:14]}<{token}>{G_NUMBER[14:]}<nl>"
    for content in (resident, mask_markup_rrn(resident)):
        assert SUFFIX not in repr(parse_otsl_tables(content))
    for content in (document, mask_markup_rrn(document)):
        text = parse_otsl_tables(content)[0].rows[0][0].text
        assert text.replace(" ", "") == G_NUMBER


def test_completed_html_cell_has_the_same_resident_and_document_identifier_contract():
    resident = f"<table><tr><td><span>900101-</span><span>1654321</span></td></tr></table>"
    document = f"<table><tr><td><span>{G_NUMBER[:14]}</span><span>{G_NUMBER[14:]}</span></td></tr></table>"
    assert SUFFIX not in repr(parse_html_tables(resident))
    assert parse_html_tables(document)[0].rows[0][0].text == G_NUMBER


@pytest.mark.parametrize("separator", ["", " ", "-", "–"])
@pytest.mark.parametrize("sex", ["1", "3"])
def test_resident_birth_survives_compact_spaced_and_dashed_early_redaction(separator, sex):
    pages = []
    for page, old in build():
        words = [ocr.OcrWord("000101" + separator + sex + SUFFIX if word.text.startswith("990101") else word.text,
                             word.confidence, word.bbox_px) for word in old.words]
        pages.append((page, ocr.OcrResult("own", words)))
    result = resident_abstract.extract(pages)
    assert result.fields["birth_date"].value == date(2000 if sex == "3" else 1900, 1, 1)
    assert SUFFIX not in repr(pages)


@pytest.mark.parametrize("sex", ["0", "9"])
def test_resident_legacy_dashed_century_prefix_remains_supported(sex):
    assert resident_abstract._birth_from_rrn("000101", sex) == date(1800, 1, 1)
    assert resident_abstract.RRN.fullmatch("000101-" + sex)


def test_text_layer_ingress_preserves_g_identifier_split_after_thirteen_digits(tmp_path):
    cells = [cell for cell in acquisition_cells() if not cell[2].startswith("발급번호")]
    cells.extend([(10, 8, "발급번호 :"), (30, 8, G_NUMBER[:14]), (43, 8, G_NUMBER[14:])])
    path = text_pdf(tmp_path / "FAKE-split-document-number.pdf", cells)
    pages = _load_pages(DocumentInput(doc_id="FAKE", declared_type=DocType.NHIS_ACQUISITION_LOSS,
                                     file_path=str(path)), "own")
    assert isinstance(pages, list)
    from engine_v2.extractors import nhis_acquisition_loss

    assert nhis_acquisition_loss.extract(pages).document_number == G_NUMBER

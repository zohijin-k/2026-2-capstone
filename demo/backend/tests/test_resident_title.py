"""LocalOcr routes coordinate title fallback through the resident extractor."""
from dataclasses import replace

import pytest
from demo.backend.ocr import localocr, pdftext
from demo.backend.rules.doc_types import DocType
from demo.backend.rules.doc_check import check_document
from demo.backend.rules.required_docs import DocRequirement
from engine_v2.tests import observed_form_samples as s
from engine_v2.tests.nhis_form_samples import text_pdf


@pytest.mark.parametrize('kind,expected', [('초본', DocType.RESIDENT_ABSTRACT), ('등본', DocType.RESIDENT_CERTIFICATE)])
@pytest.mark.parametrize('text_layer', [False, True])
def test_coordinate_fallback_reaches_resident_extraction(tmp_path, monkeypatch, kind, expected, text_layer):
    page, words = s.page(s.resident(kind=kind), size=(2065, 2923), image=not text_layer)
    assert pdftext.classify(words.text) is None
    original = list(localocr._import_v2())
    if text_layer:
        path = text_pdf(tmp_path / 'arbitrary.pdf', [(10, 20, '가상자료 ' * 50)])
        original[8] = lambda *args: [(page, words)]
    else:
        from PIL import Image
        path = tmp_path / 'arbitrary.png'
        Image.new('RGB', (50, 50), 'white').save(path)
        original[3] = lambda *args: words
        original[5] = lambda *args: [replace(page, png=b'synthetic')]
    monkeypatch.setattr(localocr, '_import_v2', lambda: tuple(original))
    monkeypatch.setattr(localocr, '_merge_image_heuristics', lambda *args: None)
    monkeypatch.setenv('ENGINE_V2_OCR', 'fake')
    result = localocr.LocalOcr().read(str(path), DocType.INSURANCE_4)
    assert result is not None
    assert result.tier == 'localocr'
    assert result.detected_doc_type == expected
    assert '좌표 제목 규칙' in result.classification_evidence
    assert '판독검증실패' in result.fields
    requirement = DocRequirement(slot_key='resident', doc_type=expected, label='가상 서류')
    # Title classification does not promote missing fields/history to PASS.
    assert check_document(requirement, result).status == 'NEEDS_REVIEW'


def test_legacy_keywords_keep_priority_over_coordinate_fallback():
    page, words = s.page(s.resident(kind='등본'), size=(2065, 2923))
    from engine_v2.pipeline.ocr import OcrWord
    words.words.append(OcrWord('주민등록초본', .99, (100, 1000, 200, 1040)))
    detected, evidence = pdftext.classify_pages_with_evidence([(page, words)])
    assert detected == DocType.RESIDENT_ABSTRACT
    assert '좌표 제목 규칙' not in evidence

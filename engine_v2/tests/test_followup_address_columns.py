"""Fictitious positional blank dates, digit vetoes and normal-page regressions."""
from copy import deepcopy

import pytest

from engine_v2.extractors.address_dates import assess
from engine_v2.pipeline.ocr import OcrWord
from engine_v2.pipeline.preprocess import PageSource
from engine_v2.tests.followup_address_samples import sparse_dates
from engine_v2.tests import p2_resident_samples


@pytest.mark.parametrize("source", [PageSource.UPLOAD, PageSource.TEXT_LAYER])
@pytest.mark.parametrize("scale", [.6, 1, 2])
def test_blank_observed_columns_ignore_global_quality_and_coordinate_scale(source, scale):
    pages = sparse_dates()
    for page, result in pages:
        page.source = source
        page.pixel_size = tuple(round(n * scale) for n in page.pixel_size)
        for word in result.words:
            word.bbox_px = tuple(n * scale for n in word.bbox_px)
    data = assess(pages, type_confidence=.95)
    assert data["status"] == "MISSING"
    assert data["pages"][0]["basis"] == "positional_blank_date_columns"
    assert data["pages"][0]["rows"] == 3


@pytest.mark.parametrize("text,box", [
    ("0", (550, 475, 564, 495)),
    ("FAKE0", (700, 475, 720, 495)),
    ("????0", (520, 475, 535, 495)),
    ("0000-00-00", (735, 475, 900, 495)),
])
def test_any_digit_word_in_or_overlapping_either_date_column_vetoes_failure(text, box):
    pages = sparse_dates()
    pages[0][1].words.append(OcrWord(text, .01, box))
    assert assess(pages, type_confidence=.95)["status"] == "UNDETERMINED"


@pytest.mark.parametrize("defect", ["headers", "one-row", "title", "number", "duplicate-header"])
def test_missing_or_ambiguous_positional_proof_remains_unknown(defect):
    pages = sparse_dates(rows=1 if defect == "one-row" else 3, headers=defect != "headers")
    words = pages[0][1].words
    if defect == "title":
        for word in words:
            if word.text in {"주민등록표", "초", "본)"}:
                word.confidence = .1
    elif defect == "number":
        words[:] = [w for w in words if w.text != "번호"]
    elif defect == "duplicate-header":
        words.append(OcrWord("신고일", 1, (780,417,870,443)))
    assert assess(pages, type_confidence=.95)["status"] == "UNDETERMINED"


def test_one_address_with_multiple_continuation_lines_is_not_two_rows():
    pages = sparse_dates(rows=1)
    pages[0][1].words += [OcrWord("가짜 주소 이어지는 줄", .99, (124,510,380,530)),
                         OcrWord("가짜 주소 또 다른 줄", .99, (124,550,380,570))]
    assert assess(pages, type_confidence=.95)["status"] == "UNDETERMINED"


def test_unbounded_footer_notes_cannot_establish_address_rows():
    pages = sparse_dates()
    pages[0][1].words[:] = [w for w in pages[0][1].words if w.bbox_px[1] < 465]
    pages[0][1].words += [OcrWord("가짜 발급기관", .99, (700,900,880,925)),
                         OcrWord("1", 1, (80,1000,96,1020)),
                         OcrWord("가짜 안내 문장", 1, (124,1000,400,1020)),
                         OcrWord("2", 1, (80,1050,96,1070)),
                         OcrWord("다른 가짜 안내 문장", 1, (124,1050,400,1070))]
    assert assess(pages, type_confidence=.95)["status"] == "UNDETERMINED"


@pytest.mark.parametrize("second", ["digit", "unknown", "blank"])
def test_all_pages_must_independently_prove_blank_columns(second):
    pages = sparse_dates()
    other = sparse_dates(digit=second == "digit", headers=second != "unknown")
    other[0][0].page = 1
    pages += other
    data = assess(pages, type_confidence=.95)
    assert data["status"] == ("MISSING" if second == "blank" else "UNDETERMINED")


@pytest.mark.parametrize("source", [PageSource.UPLOAD, PageSource.TEXT_LAYER])
def test_normal_dated_multisheet_forms_never_acquire_omission(source):
    pages = deepcopy(p2_resident_samples.resident())
    for page, _ in pages:
        page.source = source
        page.dpi = 100
    assert assess(pages, type_confidence=.95)["status"] != "MISSING"

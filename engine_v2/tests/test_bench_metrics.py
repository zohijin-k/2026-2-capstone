"""Evaluation ordering is geometric and cannot repair recognized characters."""
import numpy as np

from engine_v2.pipeline.ocr import OcrWord
from engine_v2.tools.synth_bench import (
    calibration, cer, error_pairs, ordered_words,
)


def test_quantization_boundary_does_not_swap_same_line():
    words = [OcrWord("가", .9, (0, 23, 20, 43)),
             OcrWord("나", .8, (40, 22, 60, 42))]
    ordered = ordered_words(words)
    assert "".join(w.text for w in ordered) == "가나"
    assert calibration("가나", words)[-2]["accuracy"] == 1


def test_ordering_preserves_substitution_insertion_and_missing_text():
    words = [OcrWord("가X", .9, (0, 20, 30, 40)),
             OcrWord("라", .8, (40, 20, 60, 40))]
    text = "".join(w.text for w in ordered_words(words))
    assert text == "가X라"
    assert cer("가나다", text) == 2 / 3
    assert sum(p["count"] for p in error_pairs("가나다", text)) == 2
    assert cer("가나다", "가") == 2 / 3
    assert cer("가", "가X") == 1


def test_inverse_transform_ordering_and_confidences():
    transform = np.array([[1, 0, 10], [.2, 1, 20], [0, 0, 1]])
    words = [OcrWord("오른쪽", .8, (110, 60, 130, 84)),
             OcrWord("왼쪽", .9, (10, 40, 30, 64))]
    ordered = ordered_words(words, transform)
    assert [w.text for w in ordered] == ["왼쪽", "오른쪽"]
    assert [w.confidence for w in ordered] == [.9, .8]


def test_normalization_does_not_hide_punctuation_case_or_lookalikes():
    for reference, hypothesis in [("A", "a"), ("0", "O"), ("-", "~"), ("가.", "가")]:
        assert cer(reference, hypothesis) > 0
    assert error_pairs("가나", "가") == [{"reference": "나", "hypothesis": "", "count": 1}]


def test_calibration_composes_jamo_split_across_words():
    words = [OcrWord("ᄀ", .95, (0, 10, 10, 30)),
             OcrWord("ᅡ", .85, (11, 10, 20, 30))]
    bins = calibration("가", words)
    assert sum(b["count"] for b in bins) == 1
    assert bins[2]["accuracy"] == 1
    assert bins[2]["mean_confidence"] == .85


def test_authored_geometry_does_not_merge_tall_inverse_boxes_or_drop_background():
    words = [OcrWord("첫줄", .9, (0, 20, 500, 170)),
             OcrWord("둘째줄", .9, (0, 100, 500, 290)),
             OcrWord("오른열", .9, (600, 85, 650, 105)),
             OcrWord("가짜배경", .8, (0, 400, 500, 600))]
    ordered = ordered_words(words, np.eye(3), [110, 210])
    assert [w.text for w in ordered] == ["첫줄", "오른열", "둘째줄", "가짜배경"]
    assert cer("첫줄오른열둘째줄", "".join(w.text for w in ordered)) > 0

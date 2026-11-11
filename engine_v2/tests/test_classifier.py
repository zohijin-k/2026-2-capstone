"""Fast classifier contract tests; no OCR assets or rendering downloads needed."""
from __future__ import annotations

import json
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from engine_v2.classifier.model import DocumentClassifier, features, fit
from engine_v2.classifier import predict as predictor
from engine_v2.pipeline.ocr import OcrResult, OcrWord


def words(text):
    return [OcrWord(text, .97, (50, 30, 850, 80))]


def examples():
    classes = {"resident_abstract": "주민등록표 초본 주소변동 사항 전입일",
               "nhis_payment": "건강보험료 납부확인서 고지금액 납부금액",
               "other": "행사 안내문 행사 일정 장소 문의"}
    return [{"document_type": key, "words": words(text + f" 가상시험 {index}"),
             "pixel_size": [1000, 1400]} for key, text in classes.items() for index in range(4)]


@pytest.fixture(scope="module")
def model():
    return fit(examples())


def test_seed_reproducibility_and_safe_roundtrip(model, tmp_path):
    again = fit(examples(), seed=20261111)
    np.testing.assert_array_equal(model.coefficients, again.coefficients)
    np.testing.assert_array_equal(model.idf, again.idf)
    assert model.vocabulary == again.vocabulary
    model.save(tmp_path)
    restored = DocumentClassifier.load(tmp_path)
    sample = examples()[0]
    assert model.predict(sample["words"], sample["pixel_size"]) == restored.predict(sample["words"], sample["pixel_size"])
    assert sorted(p.name for p in tmp_path.iterdir()) == ["model.json", "weights.npz"]


def test_threshold_margin_and_applicant_allowlist(model):
    sample = examples()[0]
    accepted = model.predict(sample["words"], sample["pixel_size"], threshold=0, margin=0)
    assert accepted.document_type == "resident_abstract"
    assert not accepted.needs_review
    rejected = model.predict(sample["words"], sample["pixel_size"], threshold=1)
    assert rejected.needs_review and rejected.document_type is None
    assert rejected.applicant_view() == {"document_type": None, "message": "판별 불가 → 담당자 확인"}
    assert set(accepted.applicant_view()) == {"document_type", "message"}
    assert accepted.reviewer_view()["top_features"]
    assert model.predict(sample["words"], sample["pixel_size"], margin=1).needs_review
    with pytest.raises(ValueError):
        model.predict(sample["words"], sample["pixel_size"], threshold=-1)


def test_other_is_not_abstention_and_empty_or_unseen_abstains(model):
    sample = examples()[-1]
    predicted = model.predict(sample["words"], sample["pixel_size"], threshold=0, margin=0)
    assert predicted.document_type == "other" and not predicted.needs_review
    assert model.predict([], [1000, 1400], threshold=0, margin=0).needs_review
    assert model.predict(words("ZZZZZZZZ"), [1000, 1400], threshold=0, margin=0).needs_review


def test_position_features_resolution_independent():
    original = words("주민등록표 초본")
    scaled = [OcrWord(w.text, w.confidence, tuple(v*2 for v in w.bbox_px)) for w in original]
    assert features(original, [1000, 1400]) == features(scaled, [2000, 2800])


def test_filename_invariance_with_content_swapped_at_same_path(model, tmp_path, monkeypatch):
    # IO reads different bytes under the same misleading filename. OCR is stubbed
    # at its bytes boundary; classifier input never sees a path or declared slot.
    def raster(path):
        return [SimpleNamespace(png=Path(path).read_bytes(), pixel_size=[1000, 1400])]
    def ocr(engine, png, size):
        assert engine == "own"
        return OcrResult("own", words(png.decode()))
    monkeypatch.setattr(predictor, "raster_pages", raster)
    monkeypatch.setattr(predictor, "run_ocr", ocr)
    misleading = tmp_path / "건강보험료납부확인서.pdf"
    misleading.write_text("주민등록표 초본 주소변동 사항 전입일 가상시험 0")
    first = predictor.predict_file(misleading, model, threshold=0)[0]
    renamed = tmp_path / "전혀다른이름.png"
    renamed.write_bytes(misleading.read_bytes())
    assert predictor.predict_file(renamed, model, threshold=0)[0] == first
    misleading.write_text("건강보험료 납부확인서 고지금액 납부금액 가상시험 0")
    second = predictor.predict_file(misleading, model, threshold=0)[0]
    assert (first.document_type, second.document_type) == ("resident_abstract", "nhis_payment")


def test_pdf_text_layer_is_rasterized_for_own_ocr(model, tmp_path, monkeypatch):
    import pymupdf
    file = tmp_path / "unrelated.pdf"
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_text((50, 50), "This PDF contains a searchable text layer. " * 4)
        doc.save(file)
    called = []
    def ocr(engine, png, size):
        called.append(engine)
        assert png.startswith(b"\x89PNG") and size[0] > 1000
        return OcrResult("own", words("주민등록표 초본 주소변동 사항 전입일"))
    monkeypatch.setattr(predictor, "run_ocr", ocr)
    assert predictor.predict_file(file, model, threshold=0)[0].candidate_type == "resident_abstract"
    assert called == ["own"]


def test_missing_model_has_training_command(tmp_path):
    with pytest.raises(FileNotFoundError, match="python -m engine_v2.classifier.train --corpus"):
        DocumentClassifier.load(tmp_path / "missing")


def test_private_output_drops_text_paths_and_evidence(model, monkeypatch, capfd):
    # A catalog stub keeps this unit test independent of the integration catalog.
    monkeypatch.setitem(sys.modules, "engine_v2.classifier.catalog", SimpleNamespace(CLASS_LABELS={k: k for k in model.classes}))
    result = model.predict(examples()[0]["words"], [1000, 1400], threshold=0)
    rows = predictor.private_rows([result], "resident_abstract")
    assert set(rows[0]) == {"document_type", "probability", "correct"}
    assert rows[0]["correct"] is True
    def exploding(*args, **kwargs):
        print("secret fictional value")
        raise ValueError("secret fictional value")
    monkeypatch.setattr(predictor.DocumentClassifier, "load", exploding)
    assert predictor.main(["sensitive_filename.pdf"]) == 1
    captured = capfd.readouterr()
    assert "secret" not in captured.out + captured.err
    assert "sensitive_filename" not in captured.out + captured.err
    assert "분류 실패" in captured.out


def test_train_rejects_test_fonts_layouts_and_non_synthetic(monkeypatch):
    from engine_v2.classifier.train import validate_training_corpus
    monkeypatch.setitem(sys.modules, "engine_v2.classifier.catalog", SimpleNamespace(CLASS_LABELS={"other": "기타"}))
    sample = {**examples()[-1], "font": "nanumgothiccoding", "template_id": "other:stacked_header_v1", "synthetic": True, "split": "train"}
    corpus = {"synthetic": True, "split": "train", "samples": [sample]}
    assert validate_training_corpus(corpus) == [sample]
    for patch in ({"synthetic": False}, {"split": "test"}):
        with pytest.raises(ValueError):
            validate_training_corpus({**corpus, **patch})
    for patch in ({"font": "nanumgothic"}, {"template_id": "other:inline_header_v1"}, {"split": "test"}, {"synthetic": None}, {"split": None}):
        with pytest.raises(ValueError):
            validate_training_corpus({**corpus, "samples": [{**sample, **patch}]})

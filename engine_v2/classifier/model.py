"""Explainable CPU classifier using OCR characters and normalized page position.

The API accepts OCR words and raster dimensions only. Paths, document IDs,
expected slots and reference text cannot enter the feature representation.
Artifacts are JSON and numeric NumPy arrays, never executable pickle objects.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
import unicodedata
from typing import Iterable, Mapping

import numpy as np
from sklearn.feature_extraction import DictVectorizer
from sklearn.feature_extraction.text import TfidfTransformer
from sklearn.linear_model import LogisticRegression

from ..pipeline.ocr import OcrWord

SEED = 20261111
THRESHOLD = .65
MARGIN = .15
MODEL_DIR = Path(__file__).resolve().parents[1] / "models" / "classifier"
TRAIN_COMMAND = ".venv/bin/python -m engine_v2.classifier.train --corpus engine_v2/data/synth_eval/classifier/train/corpus.json"
FORMAT_VERSION = 1


def ocr_words(words: Iterable[OcrWord | Mapping]) -> list[OcrWord]:
    """Convert the serialized OCR contract without importing sample metadata."""
    return [word if isinstance(word, OcrWord) else OcrWord(
        str(word["text"]), float(word["confidence"]), tuple(word["bbox_px"]))
        for word in words]


def _normalized(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFC", text) if not c.isspace()).lower()


def features(words: Iterable[OcrWord | Mapping], pixel_size) -> dict[str, float]:
    """Character counts plus coarse top-page text and normalized geometry.

    OCR detector boxes may span words or lines. Joining by geometry and removing
    whitespace makes content grams insensitive to those segmentation choices.
    Top-page grams use the center of each box, not fixed pixels or GT geometry.
    """
    width, height = map(float, pixel_size)
    if not np.isfinite([width, height]).all() or min(width, height) <= 0:
        raise ValueError("Positive finite raster dimensions are required")
    rows = ocr_words(words)
    if any(not np.isfinite(w.bbox_px).all() or len(w.bbox_px) != 4 for w in rows):
        raise ValueError("Finite four-coordinate OCR boxes are required")
    rows.sort(key=lambda w: (round(((w.bbox_px[1]+w.bbox_px[3])/2)/height, 2), w.bbox_px[0]))
    text = _normalized("".join(w.text for w in rows))
    header = _normalized("".join(w.text for w in rows if (w.bbox_px[1]+w.bbox_px[3])/2/height < .30))
    result: Counter = Counter()
    for prefix, stream in (("text:", text), ("top30:", header)):
        for length in (2, 3, 4):
            result.update(prefix + stream[i:i+length] for i in range(len(stream)-length+1))
    # Small non-negative, resolution-independent features. No expected layout.
    if rows:
        boxes = np.asarray([w.bbox_px for w in rows], dtype=float)
        cx = np.clip((boxes[:, 0]+boxes[:, 2])/2/width, 0, 1)
        cy = np.clip((boxes[:, 1]+boxes[:, 3])/2/height, 0, 1)
        result["position:mean_x"] = 1.0 + float(cx.mean())
        result["position:mean_y"] = 1.0 + float(cy.mean())
        result["position:width"] = 1.0 + float(np.clip((boxes[:, 2]-boxes[:, 0])/width, 0, 1).mean())
        result["position:height"] = 1.0 + float(np.clip((boxes[:, 3]-boxes[:, 1])/height, 0, 1).mean())
        for index in range(3):
            result[f"position:row_band_{index}"] = 1.0 + float(np.mean((cy >= index/3) & (cy < (index+1)/3)))
    return dict(result)


@dataclass(frozen=True)
class Prediction:
    document_type: str | None
    candidate_type: str
    probability: float
    margin: float
    needs_review: bool
    top_features: tuple[dict, ...]
    probabilities: dict[str, float]

    def applicant_view(self) -> dict:
        """Allowlist: applicant never receives probabilities or OCR evidence."""
        return {"document_type": self.document_type,
                "message": "판별 불가 → 담당자 확인" if self.needs_review else "서류 종류를 확인했습니다."}

    def reviewer_view(self) -> dict:
        return {**self.applicant_view(), "candidate_type": self.candidate_type,
                "probability": self.probability, "margin": self.margin,
                "needs_review": self.needs_review, "probabilities": self.probabilities,
                "top_features": list(self.top_features)}


class DocumentClassifier:
    def __init__(self, vocabulary, idf, classes, coefficients, intercept, *, seed=SEED,
                 threshold=THRESHOLD, margin=MARGIN, training_metadata=None):
        self.vocabulary = dict(vocabulary)
        self.feature_names = np.asarray(sorted(vocabulary, key=vocabulary.get), dtype=str)
        self.idf = np.asarray(idf, dtype=float)
        self.classes = np.asarray(classes, dtype=str)
        self.coefficients = np.asarray(coefficients, dtype=float)
        self.intercept = np.asarray(intercept, dtype=float)
        self.seed = int(seed)
        self.training_metadata = dict(training_metadata or {})
        self.threshold, self.margin = float(threshold), float(margin)
        self._vectorizer = DictVectorizer(sparse=True)
        self._vectorizer.vocabulary_ = self.vocabulary
        self._vectorizer.feature_names_ = self.feature_names.tolist()
        self._validate()

    def _validate(self):
        n, k = len(self.vocabulary), len(self.classes)
        if (k < 2 or len(set(self.classes)) != k or set(self.vocabulary.values()) != set(range(n))
                or self.idf.shape != (n,) or self.coefficients.shape != (k, n)
                or self.intercept.shape != (k,)):
            raise ValueError("Invalid classifier artifact shapes")
        if any(not np.isfinite(a).all() for a in (self.idf, self.coefficients, self.intercept)):
            raise ValueError("Invalid classifier artifact numbers")
        if (self.idf <= 0).any() or not 0 <= self.threshold <= 1 or not 0 <= self.margin <= 1:
            raise ValueError("Invalid classifier settings")

    def _vector(self, words, pixel_size):
        matrix = self._vectorizer.transform([features(words, pixel_size)])
        matrix.data = np.log(matrix.data) + 1
        matrix = matrix.multiply(self.idf).tocsr()
        length = float(np.sqrt(matrix.multiply(matrix).sum()))
        return matrix/length if length else matrix

    def predict_proba(self, words, pixel_size) -> dict[str, float]:
        vector = self._vector(words, pixel_size)
        logits = np.asarray(vector @ self.coefficients.T).ravel() + self.intercept
        exponent = np.exp(logits - logits.max())
        probabilities = exponent/exponent.sum()
        return dict(zip(self.classes.tolist(), probabilities.tolist()))

    def predict(self, words, pixel_size, *, threshold=None, margin=None, top_k=5) -> Prediction:
        threshold = self.threshold if threshold is None else float(threshold)
        margin = self.margin if margin is None else float(margin)
        if not 0 <= threshold <= 1 or not 0 <= margin <= 1:
            raise ValueError("Threshold and margin must be between zero and one")
        vector = self._vector(words, pixel_size)
        logits = np.asarray(vector @ self.coefficients.T).ravel() + self.intercept
        exponent = np.exp(logits - logits.max())
        probabilities = exponent/exponent.sum()
        order = np.argsort(-probabilities, kind="stable")
        winner, runner = int(order[0]), int(order[1])
        confidence = float(probabilities[winner])
        gap = float(probabilities[winner] - probabilities[runner])
        # An empty/unseen OCR page must not be accepted from an intercept prior.
        text_indices = [i for i in vector.indices if not self.feature_names[i].startswith("position:")]
        review = confidence < threshold or gap < margin or not text_indices
        contributions = vector.data * (self.coefficients[winner, vector.indices] - self.coefficients[runner, vector.indices])
        ranked = np.argsort(-contributions, kind="stable")
        evidence = tuple({"feature": str(self.feature_names[vector.indices[i]]),
                          "contribution_vs_runner_up": float(contributions[i])}
                         for i in ranked[:max(0, top_k)] if contributions[i] > 0)
        candidate = str(self.classes[winner])
        return Prediction(None if review else candidate, candidate, confidence, gap, review,
                          evidence, dict(zip(self.classes.tolist(), probabilities.tolist())))

    def save(self, directory=MODEL_DIR):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        metadata = {"format_version": FORMAT_VERSION, "seed": self.seed,
                    "training_metadata": self.training_metadata,
                    "threshold": self.threshold, "margin": self.margin,
                    "classes": self.classes.tolist(), "vocabulary": self.vocabulary,
                    "feature_policy": "NFC no whitespace char2-4; top30%; normalized geometry; sublinear TF-IDF L2",
                    "training_policy": "synthetic training split only; sklearn LogisticRegression C=8 lbfgs"}
        # Metadata is installed last: a partially written first artifact fails closed.
        np.savez_compressed(directory / "weights.npz", idf=self.idf,
                            coefficients=self.coefficients, intercept=self.intercept)
        (directory / "model.json").write_text(json.dumps(metadata, ensure_ascii=False, sort_keys=True)+"\n", encoding="utf-8")

    @classmethod
    def load(cls, directory=MODEL_DIR):
        directory = Path(directory)
        if not all((directory/name).is_file() for name in ("model.json", "weights.npz")):
            raise FileNotFoundError(f"분류 모델이 없습니다. 먼저 학습하세요: {TRAIN_COMMAND}")
        metadata = json.loads((directory / "model.json").read_text(encoding="utf-8"))
        if metadata.get("format_version") != FORMAT_VERSION:
            raise ValueError("Unsupported classifier model version; retrain")
        with np.load(directory / "weights.npz", allow_pickle=False) as weights:
            return cls(metadata["vocabulary"], weights["idf"], metadata["classes"],
                       weights["coefficients"], weights["intercept"], seed=metadata["seed"],
                       threshold=metadata["threshold"], margin=metadata["margin"],
                       training_metadata=metadata.get("training_metadata", {}))


def fit(samples, seed=SEED) -> DocumentClassifier:
    """Fit only supplied training examples. No reference text or metadata features."""
    samples = list(samples)
    if not samples or len({s["document_type"] for s in samples}) < 2:
        raise ValueError("Training requires at least two document classes")
    vectorizer = DictVectorizer(sparse=True)
    counts = vectorizer.fit_transform([features(s["words"], s["pixel_size"]) for s in samples])
    transformer = TfidfTransformer(sublinear_tf=True, norm="l2")
    matrix = transformer.fit_transform(counts)
    classifier = LogisticRegression(C=8.0, solver="lbfgs", max_iter=1000, tol=1e-7, random_state=seed)
    classifier.fit(matrix, [s["document_type"] for s in samples])
    coefficients, intercept = classifier.coef_, classifier.intercept_
    if len(classifier.classes_) == 2:
        # sklearn binary sigmoid corresponds to these two symmetric softmax logits.
        coefficients = np.vstack((-coefficients[0]/2, coefficients[0]/2))
        intercept = np.array([-intercept[0]/2, intercept[0]/2])
    return DocumentClassifier(vectorizer.vocabulary_, transformer.idf_, classifier.classes_,
                              coefficients, intercept, seed=seed)

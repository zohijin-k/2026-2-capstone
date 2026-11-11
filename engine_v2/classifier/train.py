"""Train the first local classifier from synthetic own-OCR training records.

Run data generation first, then:
  python -m engine_v2.classifier.train --corpus PATH/train/corpus.json
No test examples, filenames, authored reference strings or field truth are fit.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path

from .model import MODEL_DIR, SEED, fit
from ..tools.make_synth_eval import SPLITS


def validate_training_corpus(corpus):
    from .catalog import CLASS_LABELS
    if corpus.get("synthetic") is not True or corpus.get("split") != "train":
        raise ValueError("Only the synthetic train split may be used for fitting")
    samples = corpus.get("samples", [])
    if not samples:
        raise ValueError("Training corpus is empty")
    for sample in samples:
        if sample.get("split") != "train" or sample.get("synthetic") is not True:
            raise ValueError("Mixed or non-synthetic training records are forbidden")
        if sample.get("font") not in SPLITS["train"]["fonts"]:
            raise ValueError("Training records contain a held-out or unknown font")
        if not sample.get("template_id", "").endswith(SPLITS["train"]["template"]):
            raise ValueError("Training records contain a held-out or unknown layout")
        if sample.get("document_type") not in CLASS_LABELS:
            raise ValueError("Training records contain an unsupported document type")
    if {s["document_type"] for s in samples} != set(CLASS_LABELS):
        raise ValueError("Training corpus must include every catalog class")
    return samples


def train(corpus_path, output=MODEL_DIR, *, seed=SEED):
    raw = Path(corpus_path).read_bytes()
    corpus = json.loads(raw)
    samples = validate_training_corpus(corpus)
    model = fit(samples, seed=seed)
    model.training_metadata = {
        "corpus_sha256": hashlib.sha256(raw).hexdigest(), "samples": len(samples),
        "versions": {name: importlib.metadata.version(name) for name in ("numpy", "scipy", "scikit-learn")},
        "parameters": {"C": 8.0, "solver": "lbfgs", "max_iter": 1000, "tol": 1e-7,
                       "seed": seed, "threshold": model.threshold, "margin": model.margin},
    }
    model.save(output)
    return model


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=MODEL_DIR)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args(argv)
    model = train(args.corpus, args.output, seed=args.seed)
    print(json.dumps({"trained": True, "classes": len(model.classes),
                      "features": len(model.vocabulary), "seed": args.seed}, ensure_ascii=False))


if __name__ == "__main__":
    main()

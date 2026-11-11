"""Classify raster/image/PDF pages using own OCR, without filename features.

The CLI is also the real-document benchmark mode: output is strictly limited
 to category, probability and correctness. It never prints paths, OCR text,
feature contributions, reference labels, model metadata or exception strings.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .model import DocumentClassifier, MODEL_DIR, TRAIN_COMMAND
from ..pipeline.ocr import run_ocr
from ..tools.private_bench import quiet_dependencies, raster_pages


def predict_file(path, model: DocumentClassifier, *, threshold=None):
    """Paths are used only to load/rasterize bytes; every page uses own OCR."""
    predictions = []
    for page in raster_pages(Path(path)):
        result = run_ocr("own", page.png, page.pixel_size)
        if result.error or result.engine != "own":
            raise RuntimeError("Own OCR failed")
        predictions.append(model.predict(result.words, page.pixel_size, threshold=threshold))
    if not predictions:
        raise ValueError("Input has no pages")
    return predictions


def private_rows(predictions, expected=None):
    from .catalog import CLASS_LABELS
    allowed = set(CLASS_LABELS)
    if expected is not None and expected not in allowed:
        raise ValueError("Unsupported reference category")
    if any(p.candidate_type not in allowed or (p.document_type is not None and p.document_type not in allowed)
           for p in predictions):
        raise ValueError("Unsupported model category")
    return [{"document_type": p.document_type or "판별 불가 → 담당자 확인",
             "probability": round(p.probability, 6),
             "correct": None if expected is None else p.document_type == expected}
            for p in predictions]


def main(argv=None):
    # Argument parsing is inside suppression too: invalid arguments can contain
    # filenames or sensitive values, which argparse would otherwise echo.
    failed, missing, rows = False, False, None
    with quiet_dependencies():
        try:
            parser = argparse.ArgumentParser(description=__doc__, add_help=False)
            parser.add_argument("file", type=Path)
            parser.add_argument("--model", type=Path, default=MODEL_DIR)
            parser.add_argument("--expected")
            parser.add_argument("--threshold", type=float)
            args = parser.parse_args(argv)
            model = DocumentClassifier.load(args.model)
            rows = private_rows(predict_file(args.file, model, threshold=args.threshold), args.expected)
        except FileNotFoundError:
            # A missing input must not be confused with missing model weights.
            missing = not all((args.model/name).is_file() for name in ("model.json", "weights.npz")) if "args" in locals() else False
            failed = True
        except (Exception, SystemExit):
            failed = True
    if failed:
        print("분류 모델이 없습니다. 학습 명령: " + TRAIN_COMMAND if missing else "분류 실패: 입력·모델·의존성을 확인하세요.")
        return 1
    print(json.dumps(rows, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Synthetic OCR metrics. NFC + remove all Unicode whitespace; case retained.

CER is Levenshtein edits / reference characters (may exceed 1). Confidence
calibration aligns the entire character stream, counts substitutions/insertions
as incorrect, and assigns each emitted character its parent OCR word score.
Deletions affect CER but have no emitted confidence and cannot enter bins.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import unicodedata
import io
import time
from collections import Counter
from datetime import date
from pathlib import Path

from ..extractors import resident_abstract, nhis_payment, nhis_acquisition_loss
from ..pipeline.ocr import run_ocr
from ..pipeline.preprocess import PageImage, PageSource
from .privacy import mask_text

EXTRACTORS = {"resident_abstract": resident_abstract.extract,
              "nhis_payment": nhis_payment.extract,
              "nhis_acquisition_loss": nhis_acquisition_loss.extract}


def normalize_text(text):
    return "".join(c for c in unicodedata.normalize("NFC", text) if not c.isspace())


def _alignment(reference, hypothesis):
    """Minimum-edit alignment; returns distance and correctness per hypothesis char."""
    ref, hyp = normalize_text(reference), normalize_text(hypothesis)
    # Compact traceback avoids Python-int quadratic memory for full-page OCR.
    from array import array
    trace = [bytearray(len(hyp)+1) for _ in range(len(ref)+1)]
    previous = array('I', range(len(hyp)+1))
    trace[0][:] = bytes([2]) * (len(hyp)+1)
    for i, r in enumerate(ref, 1):
        current = array('I', [i])
        trace[i][0] = 1
        for j, h in enumerate(hyp, 1):
            options = (previous[j-1]+(r != h), previous[j]+1, current[j-1]+1)
            best = min(options)
            trace[i][j] = options.index(best)
            current.append(best)
        previous = current
    correct = [False]*len(hyp)
    pairs = []
    i, j = len(ref), len(hyp)
    while i or j:
        direction = trace[i][j]
        if direction == 0:
            correct[j-1] = ref[i-1] == hyp[j-1]
            if not correct[j-1]:
                pairs.append((ref[i-1], hyp[j-1]))
            i, j = i-1, j-1
        elif direction == 1:
            pairs.append((ref[i-1], ""))
            i -= 1
        else:
            pairs.append(("", hyp[j-1]))
            j -= 1
    return previous[-1], correct, pairs


def alignment(reference, hypothesis):
    """Minimum-edit distance and correctness in emitted-character order."""
    distance, correct, _ = _alignment(reference, hypothesis)
    return distance, correct


def error_pairs(reference, hypothesis):
    """Synthetic diagnostics only; empty string denotes insertion/deletion."""
    counts = Counter(_alignment(reference, hypothesis)[2])
    return [{"reference": r, "hypothesis": h, "count": n}
            for (r, h), n in counts.most_common()]


def cer(reference, hypothesis):
    edits, _ = alignment(reference, hypothesis)
    return edits / max(len(normalize_text(reference)), 1)


def ordered_words(words, page_transform=None, line_baselines=None):
    """Geometry-only order; never match/reorder by reference text.

    Synthetic homography removes camera geometry for metric ordering only.
    Extractors still receive the original engine words and pixel coordinates.
    """
    import numpy as np
    from ..pipeline.ocr import OcrWord
    from ..pipeline.layout import normalize, group_lines
    matrix = np.linalg.inv(np.asarray(page_transform, dtype=float)) if page_transform is not None else np.eye(3)
    mapped = []
    for word in words:
        x0, y0, x1, y1 = word.bbox_px
        corners = np.array([[x0,y0,1], [x1,y0,1], [x1,y1,1], [x0,y1,1]]) @ matrix.T
        xy = corners[:, :2] / corners[:, 2:3]
        bounds = (*xy.min(axis=0), *xy.max(axis=0))
        mapped.append(OcrWord(word.text, word.confidence, bounds))
    if line_baselines:
        # Inverse axis-aligned boxes grow with line length under strong skew.
        # Match centers to authored row geometry, never to authored text. Keep
        # distant/background detections in their own geometric position.
        baselines = sorted(line_baselines)
        def key(word):
            x0, y0, x1, y1 = word.bbox_px
            cy = (y0+y1)/2
            nearest = min(range(len(baselines)), key=lambda i: abs(cy-baselines[i]))
            gaps = [abs(baselines[nearest]-baselines[i])
                    for i in (nearest-1, nearest+1) if 0 <= i < len(baselines)]
            tolerance = min(gaps)*.45 if gaps else float("inf")
            row = baselines[nearest] if abs(cy-baselines[nearest]) <= tolerance else cy
            return row, x0
        return sorted(mapped, key=key)
    # normalize to an arbitrary common canvas: ratios cancel in grouping.
    lines = group_lines(normalize(mapped, 0, (100, 100)), tol=.6)
    return [OcrWord(w.text, w.conf, w.px) for line in lines for w in line]


def calibration(reference, words, *, ordered=False):
    ordered = words if ordered else ordered_words(words)
    # Compose across word boundaries too (e.g. split Hangul Jamo). Keep one
    # score per resulting codepoint; merged/reordered suffix uses the minimum
    # contributing score rather than inventing extra confidence observations.
    text, scores = "", []
    for word in ordered:
        for char in normalize_text(word.text):
            composed = normalize_text(text + char)
            prefix = 0
            while prefix < min(len(text), len(composed)) and text[prefix] == composed[prefix]:
                prefix += 1
            score = min(scores[prefix:] + [word.confidence])
            scores[prefix:] = [score] * (len(composed) - prefix)
            text = composed
    _, correct = alignment(reference, text)
    bins = []
    for low, high in ((0, .5), (.5, .8), (.8, .9), (.9, 1.0)):
        indices = [i for i, score in enumerate(scores) if low <= score and (score < high or high == 1 and score <= 1)]
        n = len(indices)
        bins.append({"low": low, "high": high, "count": n,
                     "accuracy": sum(correct[i] for i in indices)/n if n else None,
                     "mean_confidence": sum(scores[i] for i in indices)/n if n else None})
    return bins


def available(engine):
    if engine == "applevision" and sys.platform != "darwin":
        return "macOS 전용"
    if engine == "jbai":
        return None if os.environ.get("JBAI_API_KEY", "").strip() else "JBAI_API_KEY 미설정"
    if engine == "own":
        from .fetch_own_models import verify_models
        try:
            verify_models()
        except (FileNotFoundError, ValueError):
            return "모델 없음/해시 불일치: .venv/bin/python engine_v2/tools/fetch_own_models.py"
    package = {"easyocr": "easyocr", "applevision": "ocrmac", "own": "onnxruntime"}.get(engine)
    if package is None:
        return "지원하지 않는 평가 엔진"
    if importlib.util.find_spec(package) is None:
        return f"{package} 미설치"
    return None


def field_matches(extracted, truth):
    # Dates and numeric values are compared in their serialized form, no fuzzy match.
    actual = {key: field.model_dump(mode="json")["value"] for key, field in extracted.fields.items()}
    return {key: actual.get(key) == expected for key, expected in truth.items()}


def run_suite(manifest_path, engines, output, *, unmasked=False, rectify_phone=False):
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("synthetic") is not True or any(s.get("synthetic") is not True for s in manifest["samples"]):
        raise ValueError("합성 평가 manifest만 허용됩니다")
    today = date.fromisoformat(manifest["today"])
    rows, skipped = [], []
    samples = []
    for sample in manifest["samples"]:
        samples.append((sample, False))
        if rectify_phone and sample["degradation"].startswith("phone"):
            samples.append((sample, True))
    print("engine | document | degradation | font | CER | fields | sec/page | confidence")
    for engine in engines:
        reason = available(engine)
        if reason:
            skipped.append({"engine": engine, "reason": reason})
            print(f"{engine} | SKIP | {reason}")
            continue
        for sample, rectify in samples:
            image_path = (manifest_path.parent / sample["image"]).resolve()
            if image_path.parent != manifest_path.parent.resolve():
                raise ValueError("이미지는 manifest와 같은 디렉터리에 있어야 합니다")
            raw = image_path.read_bytes()
            from PIL import Image
            with Image.open(io.BytesIO(raw)) as im:
                size = im.size
            transform = sample.get("page_transform")
            correction_sec, correction_applied = 0.0, False
            if rectify:
                import numpy as np
                from ..pipeline.perspective import rectify_document
                started = time.perf_counter()
                with Image.open(io.BytesIO(raw)) as im:
                    corrected = rectify_document(im.convert("RGB"))
                correction_sec = time.perf_counter() - started
                correction_applied = corrected.applied
                buf = io.BytesIO()
                corrected.image.save(buf, format="PNG")
                raw, size = buf.getvalue(), corrected.image.size
                if corrected.applied:
                    transform = (np.asarray(corrected.matrix) @ np.asarray(transform if transform is not None else np.eye(3))).tolist()
            page = PageImage(0, PageSource.UPLOAD, tuple(sample["page_size_pt"]), png=raw, pixel_size=size, dpi=300)
            row = {"engine": engine, "sample": sample["id"], "document": sample["document_type"], "degradation": sample["degradation"] + ("+rectified" if rectify else ""),
                   "font": sample.get("font", "bundled-cjk"), "split": sample.get("split", "legacy"),
                   "rectification_requested": rectify, "rectification_applied": correction_applied,
                   "rectification_seconds": correction_sec}
            try:
                if engine == "jbai":
                    from ..pipeline.jbai_ocr import run_jbai_image_pair, JBAIDocumentResult
                    from ..extractors.jbai_text import extract
                    from ..schemas.models import DocType
                    captured = run_jbai_image_pair(raw, size)
                    text = "\n".join(captured.text_lines)
                    extracted = extract(JBAIDocumentResult(pages=[captured], elapsed_sec=captured.elapsed_sec), DocType(sample["document_type"]), today=today)
                    elapsed, confidence, bins = captured.elapsed_sec + correction_sec, None, []
                else:
                    result = run_ocr(engine, raw, size)
                    if result.error:
                        # Error text may contain remote details: never serialize it verbatim.
                        row.update(status="error", reason="OCR 실행 실패; 모델/의존성 설치를 확인하세요")
                        rows.append(row)
                        print(f"{engine} | {row['document']} | {row['degradation']} | ERROR")
                        continue
                    words = ordered_words(result.words, transform, sample.get("line_baselines_px"))
                    text, elapsed = " ".join(w.text for w in words), result.elapsed_sec + correction_sec
                    row["raw_stream_cer"] = cer("\n".join(sample["text_lines"]), result.text)
                    confidence = sum(w.confidence for w in result.words)/len(result.words) if result.words else 0.0
                    bins = calibration("\n".join(sample["text_lines"]), words, ordered=True)
                    extracted = EXTRACTORS[sample["document_type"]]([(page, result)], today=today)
                matches = field_matches(extracted, sample["fields"])
                row.update(status="ok", cer=cer("\n".join(sample["text_lines"]), text),
                           field_accuracy=sum(matches.values())/len(matches), field_matches=matches,
                           seconds_per_page=elapsed, mean_confidence=confidence,
                           confidence_bins=bins, recognized_text=text if unmasked else mask_text(text),
                           detected_type=extracted.detected_type.value)
                if unmasked:
                    row["error_pairs"] = error_pairs("\n".join(sample["text_lines"]), text)
                    if engine != "jbai":
                        row["raw_stream_error_pairs"] = error_pairs("\n".join(sample["text_lines"]), result.text)
                conf_display = f"{confidence:.3f}" if confidence is not None else "N/A"
                print(f"{engine} | {row['document']} | {row['degradation']} | {row['font']} | {row['cer']:.4f} | {sum(matches.values())}/{len(matches)} | {elapsed:.3f} | {conf_display}")
            except Exception as error:
                row.update(status="error", reason=type(error).__name__)
                print(f"{engine} | {row['document']} | {row['degradation']} | ERROR {type(error).__name__}")
            rows.append(row)
    report = {"schema_version": 2, "synthetic": True, "seed": manifest["seed"], "masked": not unmasked,
              "cer_policy": "NFC; remove all Unicode whitespace; case-sensitive; geometry-only nearest authored baseline within 0.45*adjacent row gap; unmatched detections retained; legacy manifests use center tolerance 0.6*height; left-to-right; inverse synthetic homography for ordering only; global character Levenshtein, no text-based line matching; edits/max(reference length,1)",
              "timing_policy": "OCR wall time including first-call model initialization plus rectification function time; excludes file IO/PNG encoding/extraction; one pass, no warm-up",
              "confidence_policy": "character alignment; emitted characters inherit word confidence; deletions excluded from bins",
              "rows": rows, "skipped": skipped}
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(f"JSON: {output}")
    return report

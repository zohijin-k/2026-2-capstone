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


def alignment(reference, hypothesis):
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
    i, j = len(ref), len(hyp)
    while i or j:
        direction = trace[i][j]
        if direction == 0:
            correct[j-1] = ref[i-1] == hyp[j-1]
            i, j = i-1, j-1
        elif direction == 1:
            i -= 1
        else:
            j -= 1
    return previous[-1], correct


def cer(reference, hypothesis):
    edits, _ = alignment(reference, hypothesis)
    return edits / max(len(normalize_text(reference)), 1)


def calibration(reference, words):
    ordered = sorted(words, key=lambda w: (round(w.bbox_px[1]/15), w.bbox_px[0]))
    text = "".join(normalize_text(w.text) for w in ordered)
    scores = [w.confidence for w in ordered for _ in normalize_text(w.text)]
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


def run_suite(manifest_path, engines, output, *, unmasked=False):
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("synthetic") is not True or any(s.get("synthetic") is not True for s in manifest["samples"]):
        raise ValueError("합성 평가 manifest만 허용됩니다")
    today = date.fromisoformat(manifest["today"])
    rows, skipped = [], []
    print("engine | document | degradation | CER | fields | sec/page | confidence")
    for engine in engines:
        reason = available(engine)
        if reason:
            skipped.append({"engine": engine, "reason": reason})
            print(f"{engine} | SKIP | {reason}")
            continue
        for sample in manifest["samples"]:
            image_path = (manifest_path.parent / sample["image"]).resolve()
            if image_path.parent != manifest_path.parent.resolve():
                raise ValueError("이미지는 manifest와 같은 디렉터리에 있어야 합니다")
            raw = image_path.read_bytes()
            from PIL import Image
            import io
            with Image.open(io.BytesIO(raw)) as im:
                size = im.size
            page = PageImage(0, PageSource.UPLOAD, tuple(sample["page_size_pt"]), png=raw, pixel_size=size, dpi=300)
            row = {"engine": engine, "sample": sample["id"], "document": sample["document_type"], "degradation": sample["degradation"]}
            try:
                if engine == "jbai":
                    from ..pipeline.jbai_ocr import run_jbai_image_pair, JBAIDocumentResult
                    from ..extractors.jbai_text import extract
                    from ..schemas.models import DocType
                    captured = run_jbai_image_pair(raw, size)
                    text = "\n".join(captured.text_lines)
                    extracted = extract(JBAIDocumentResult(pages=[captured], elapsed_sec=captured.elapsed_sec), DocType(sample["document_type"]), today=today)
                    elapsed, confidence, bins = captured.elapsed_sec, None, []
                else:
                    result = run_ocr(engine, raw, size)
                    if result.error:
                        # Error text may contain remote details: never serialize it verbatim.
                        row.update(status="error", reason="OCR 실행 실패; 모델/의존성 설치를 확인하세요")
                        rows.append(row)
                        print(f"{engine} | {row['document']} | {row['degradation']} | ERROR")
                        continue
                    text, elapsed = result.text, result.elapsed_sec
                    confidence = sum(w.confidence for w in result.words)/len(result.words) if result.words else 0.0
                    bins = calibration("\n".join(sample["text_lines"]), result.words)
                    extracted = EXTRACTORS[sample["document_type"]]([(page, result)], today=today)
                matches = field_matches(extracted, sample["fields"])
                row.update(status="ok", cer=cer("\n".join(sample["text_lines"]), text),
                           field_accuracy=sum(matches.values())/len(matches), field_matches=matches,
                           seconds_per_page=elapsed, mean_confidence=confidence,
                           confidence_bins=bins, recognized_text=text if unmasked else mask_text(text),
                           detected_type=extracted.detected_type.value)
                conf_display = f"{confidence:.3f}" if confidence is not None else "N/A"
                print(f"{engine} | {row['document']} | {row['degradation']} | {row['cer']:.4f} | {sum(matches.values())}/{len(matches)} | {elapsed:.3f} | {conf_display}")
            except Exception as error:
                row.update(status="error", reason=type(error).__name__)
                print(f"{engine} | {row['document']} | {row['degradation']} | ERROR {type(error).__name__}")
            rows.append(row)
    report = {"schema_version": 1, "synthetic": True, "seed": manifest["seed"], "masked": not unmasked,
              "cer_policy": "NFC; remove all Unicode whitespace; case-sensitive; edits/max(reference length,1)",
              "timing_policy": "wall time including first-call model initialization; one pass, no warm-up",
              "confidence_policy": "character alignment; emitted characters inherit word confidence; deletions excluded from bins",
              "rows": rows, "skipped": skipped}
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(f"JSON: {output}")
    return report

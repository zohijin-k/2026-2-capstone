"""Value-free OCR benchmark. Never serialize input strings or exception details.

Output is an allowlist of engine names, generic field names, numbers and O/X.
Native dependency output is discarded as well as Python stdout/stderr. This
process-global suppression is for the single-threaded command-line tool only.
"""
from __future__ import annotations

from contextlib import contextmanager, redirect_stderr, redirect_stdout
from datetime import date
import json
import os
from pathlib import Path
import sys
import time

ENGINES = ("own", "applevision", "jbai")
DOCS = ("resident_abstract", "nhis_payment", "nhis_acquisition_loss")
KEYS = {
    "resident_abstract": ("name", "birth_date", "issue_date", "address_contains", "move_in_dates"),
    "nhis_payment": ("name", "birth_date", "issue_date", "insurance_type", "billed_by_month", "long_term_care_by_month"),
    "nhis_acquisition_loss": ("name", "birth_date", "issue_date", "query_period", "history", "recent_five_years"),
}


@contextmanager
def quiet_dependencies():
    """Discard Python and native fd output without retaining document contents."""
    with open(os.devnull, "w") as sink:
        sys.stdout.flush()
        sys.stderr.flush()
        saved = [os.dup(fd) for fd in (1, 2)]
        try:
            for fd in (1, 2):
                os.dup2(sink.fileno(), fd)
            with redirect_stdout(sink), redirect_stderr(sink):
                yield
        finally:
            # Flush buffered native output on success AND exception paths.
            import ctypes
            ctypes.CDLL(None).fflush(None)
            sink.flush()
            for fd, original in zip((1, 2), saved):
                os.dup2(original, fd)
                os.close(original)


def unavailable(engine):
    """Fixed reason codes: 1 platform, 2 installation, 3 credential, 4 opt-in."""
    if engine == "applevision" and sys.platform != "darwin":
        return 1
    if engine == "jbai":
        if not os.environ.get("JBAI_API_KEY", "").strip():
            return 3
        if os.environ.get("JBAI_ALLOW_REAL_DOCS", "").strip().lower() not in {"1", "true", "yes", "on"}:
            return 4
        return 0
    from .synth_bench import available
    return 2 if available(engine) else 0


def raster_pages(path):
    """Benchmark all PDF pages as images, including PDFs with text layers."""
    import pymupdf
    from ..pipeline.preprocess import PageImage, PageSource, preprocess
    if path.suffix.lower() != ".pdf":
        return preprocess(path)
    pages = []
    with pymupdf.open(path) as document:
        if document.needs_pass:
            raise ValueError("encrypted")
        for index, page in enumerate(document):
            pix = page.get_pixmap(dpi=300, colorspace=pymupdf.csRGB, alpha=False)
            pages.append(PageImage(index, PageSource.RENDER, (page.rect.width, page.rect.height),
                                   png=pix.tobytes("png"), pixel_size=(pix.width, pix.height), dpi=300))
    return pages


def _value_text(key, value):
    """Value-only CER streams: no fixed JSON keys or serialization punctuation."""
    if value is None:
        return ""
    def scalar(item):
        if item is None:
            return "␀"  # Explicit empty cell, distinct from absent whole field.
        if isinstance(item, bool):
            return "true" if item else "false"
        return str(item)
    if key == "history":
        return "\n".join(scalar(row.get(column)) for row in value for column in ("category", "acquired", "lost"))
    if key == "query_period":
        return "\n".join(scalar(item) for item in value)
    if key in {"billed_by_month", "long_term_care_by_month"}:
        return "\n".join(month + "\n" + scalar(amount) for month, amount in sorted(value.items()))
    return scalar(value)


def _substring_edits(reference, text):
    """Minimum distance to a contiguous substring; for contains-only GT fields."""
    from .synth_bench import normalize_text
    ref, hyp = normalize_text(reference), normalize_text(text)
    previous = [0] * (len(hyp) + 1)
    for i, char in enumerate(ref, 1):
        current = [i]
        for j, other in enumerate(hyp, 1):
            current.append(min(previous[j - 1] + (char != other), previous[j] + 1, current[j - 1] + 1))
        previous = current
    return min(previous)


def field_metrics(doc, truth, extracted):
    """Compare make_gt contracts; keys in output always come from KEYS, never GT."""
    from .synth_bench import cer, normalize_text
    actual = {key: value.model_dump(mode="json")["value"] for key, value in extracted.fields.items()}
    aliases = {"name": "성명", "birth_date": "생년월일", "issue_date": "발급일", "insurance_type": "가입구분",
               "billed_by_month": "월별고지금액", "long_term_care_by_month": "월별장기요양보험료"}
    metrics = {}
    for key in KEYS[doc]:
        if key not in truth:
            continue
        expected = truth[key]
        if key == "address_contains":
            address = actual.get("current_address", "")
            edits = sum(_substring_edits(part, address) for part in expected)
            denominator = sum(len(normalize_text(part)) for part in expected)
            metrics[key] = {"match": "O" if edits == 0 else "X", "cer": edits / max(denominator, 1)}
            continue
        if key == "move_in_dates":
            found = {value.isoformat() for row in extracted.history for value in (row.occurred, row.reported) if value}
            # make_gt specifies dates to find, not a complete history inventory.
            distances = [min((cer(value, candidate) for candidate in found), default=1.0) for value in expected]
            metrics[key] = {"match": "O" if all(value in found for value in expected) else "X",
                            "cer": sum(distances) / max(len(distances), 1)}
            continue
        if key in {"query_period", "history"}:
            data = json.loads(actual.get("자격이력자료", "{}"))
            observed = data.get("period" if key == "query_period" else "rows")
        elif key == "recent_five_years":
            observed = {"최근 5년 포함": True, "최근 5년 미포함": False}.get(actual.get("변동내역"))
        else:
            observed = actual.get(key if doc == "resident_abstract" else aliases[key])
            if key in {"billed_by_month", "long_term_care_by_month"} and observed is not None:
                observed = json.loads(observed)
        metrics[key] = {"match": "O" if observed == expected else "X", "cer": cer(_value_text(key, expected), _value_text(key, observed))}
    return metrics


def run_engine(engine, path, pages, doc, truth, today):
    from .synth_bench import EXTRACTORS
    started = time.perf_counter()
    if engine == "jbai":
        from ..pipeline.jbai_ocr import run_jbai_file_pair
        from ..extractors.jbai_text import extract
        from ..schemas.models import DocType
        captured = run_jbai_file_pair(path)
        result = extract(captured, DocType(doc), today=today)
        count = len(captured.pages)
        confidence = -1.0  # Remote model does not return calibrated confidence.
    else:
        from ..pipeline.ocr import run_ocr
        pairs, scores = [], []
        for page in pages:
            ocr = run_ocr(engine, page.png, page.pixel_size)
            if ocr.error or ocr.engine != engine:
                return {"failed": "O", "fallback": "O" if ocr.engine != engine else "X"}
            scores.extend(word.confidence for word in ocr.words)
            pairs.append((page, ocr))
        result = EXTRACTORS[doc](pairs, today=today)
        count = len(pairs)
        confidence = sum(scores) / len(scores) if scores else 0.0
    elapsed = time.perf_counter() - started
    return {"failed": "X", "fallback": "X", "pages": count,
            "seconds_per_page": round(elapsed / max(count, 1), 6), "mean_confidence": confidence,
            "confidence_available": "O" if engine != "jbai" else "X",
            "fields": field_metrics(doc, truth, result)}


def run_private(file, gt, engines=ENGINES, *, doc="resident_abstract", out=None, today=None):
    """Read explicit inputs only; write nothing unless out is explicitly provided."""
    report = {"schema_version": 1, "input_failed": "X", "output_failed": "X", "rows": []}
    try:
        with quiet_dependencies():
            if doc not in DOCS or not engines or any(engine not in ENGINES for engine in engines):
                raise ValueError("unsupported")
            path = Path(file)
            truth = json.loads(Path(gt).read_text(encoding="utf-8"))
            if not isinstance(truth, dict) or not truth or any(key not in KEYS[doc] for key in truth):
                raise ValueError("invalid ground truth")
            pages = raster_pages(path)
            if not pages:
                raise ValueError("empty input")
        for engine in engines:
            row = {"engine": engine, "skipped": "X", "failed": "X", "fallback": "X", "reason_code": 0}
            try:
                with quiet_dependencies():
                    reason = unavailable(engine)
                    if reason:
                        row.update(skipped="O", reason_code=reason)
                    else:
                        row.update(run_engine(engine, path, pages, doc, truth, today or date.today()))
            except Exception:
                row.update(failed="O", reason_code=5)
            report["rows"].append(row)
    except Exception:
        report["input_failed"] = "O"
    if out is not None:
        try:
            with quiet_dependencies():
                destination = Path(out)
                if destination.resolve() in {Path(file).resolve(), Path(gt).resolve()}:
                    raise ValueError("input overwrite")
                # Deliberately do not create parent directories or default paths.
                destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except Exception:
            report["output_failed"] = "O"
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report

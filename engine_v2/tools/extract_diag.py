"""Read-only extractor traces; default output contains no field or OCR values.

--synthetic-suite regenerates known fictitious make_synth_eval pages in memory.
Only that mode accepts --unmasked-synthetic. A supplied file is always masked.
No extractor, OCR, rectification or decision behavior is modified.
"""
from __future__ import annotations

import argparse
from datetime import date
import io
import json
from pathlib import Path

from ..extractors import nhis_acquisition_loss, nhis_common, nhis_payment, resident_abstract
from ..pipeline.layout import group_lines, normalize
from ..pipeline.ocr import run_ocr
from ..pipeline.preprocess import PageImage, PageSource
from .private_bench import quiet_dependencies, raster_pages
from .synth_bench import EXTRACTORS

DOCS = tuple(EXTRACTORS)
FIELDS = {
    "resident_abstract": ("name", "birth_date", "issue_date", "address_history_count"),
    "nhis_payment": ("성명", "생년월일", "발급일", "가입구분", "건강보험료", "고지월"),
    "nhis_acquisition_loss": ("성명", "생년월일", "발급일", "가입구분", "취득일", "변동내역"),
}
MASKED = "[masked]"


class _SafeParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse normally interpolates invalid input values and filenames.
        super().error("Invalid diagnostic arguments; consult --help")


def _display(value, unmasked):
    if value is None:
        return None
    if not unmasked:
        return MASKED
    if isinstance(value, date):
        return value.isoformat()
    return value


def _word(word, unmasked):
    return {"text": _display(word.text, unmasked), "confidence": word.conf,
            "bbox_percent": [word.x0, word.y0, word.x1, word.y1]}


def diagnose(pages, doc, *, truth=None, synthetic=False, unmasked=False):
    """Pure trace projection. Never serialize unknown GT keys or exception text.

    synthetic=True is reserved for the internal, authored synthetic generator.
    Programmatic callers must not claim arbitrary user input is synthetic.
    """
    if unmasked and not synthetic:
        raise ValueError("Unmasking requires internally generated synthetic pages")
    if doc not in DOCS:
        raise ValueError("Unsupported document type")
    truth = truth or {}
    extracted = EXTRACTORS[doc](pages, today=date(2026, 11, 11))
    fields = {}
    for key in FIELDS[doc]:
        value = extracted.fields.get(key)
        actual = value.model_dump(mode="json")["value"] if value else None
        fields[key] = {"expected": _display(truth.get(key), unmasked),
                       "actual": _display(actual, unmasked),
                       "present": value is not None,
                       "match": actual == truth[key] if key in truth else None}
    traces = []
    for page, result in pages:
        lines = group_lines(normalize(result.words, page.page, page.pixel_size))
        trace = {"page": page.page, "pixel_size": page.pixel_size,
                 "word_count": len(result.words), "line_count": len(lines),
                 "lines": [[_word(w, unmasked) for w in line] for line in lines]}
        if doc == "resident_abstract":
            header = resident_abstract._parse_header(lines)
            trace["header"] = {k: _display(header[k], unmasked) for k in ("name", "birth", "issue")}
            trace["table_bounds_percent"] = resident_abstract._table_bounds(lines)
            trace["rrn_ascii_pattern_matched"] = any(resident_abstract.RRN.search(w.text) for w in result.words)
        else:
            header = nhis_common.header_for_page(page, result)
            trace["header"] = {k: _display(getattr(header, k), unmasked) for k in ("name", "birth", "issue")}
            if doc == "nhis_payment":
                trace["month_header_line_indices"] = nhis_payment._month_header(lines)
                trace["charge_column_centers"] = nhis_payment._header_x([(page, result)], ("고지금액", "고지보험료"))
                trace["paid_column_centers"] = nhis_payment._header_x([(page, result)], ("납부금액", "납부보험료", "실납부"))
                trace["months_per_line"] = [len(nhis_payment.MONTH_RE.findall(" ".join(w.text for w in line))) for line in lines]
                trace["amounts_per_line"] = [len(nhis_payment._money_words(line)) for line in lines]
            else:
                trace["history_header_centers"] = nhis_acquisition_loss._header_positions([(page, result)])
                rows = nhis_acquisition_loss._parse_history([(page, result)])
                trace["history_rows"] = [{"category": _display(r.category, unmasked),
                                          "acquired": _display(r.acquired, unmasked),
                                          "lost": _display(r.lost, unmasked)} for r in rows]
                period, _ = nhis_acquisition_loss._query_period([(page, result)])
                trace["query_period"] = [_display(v, unmasked) for v in period] if period else None
        traces.append(trace)
    return {"document": doc, "masked": not unmasked, "fields": fields, "pages": traces}


def synthetic_cases(seed=20261111, *, include_legacy=False):
    """Exactly reproduce 004e45a's 28 requested revised cases (no arbitrary input)."""
    import numpy as np
    from .fetch_synth_fonts import font_path
    from .make_synth_eval import STAGES, degrade, degrade_with_geometry, documents, render, split_documents
    from ..pipeline.perspective import rectify_document
    for font_index, font in enumerate(("nanumgothic", "nanummyeongjo")):
        for doc_index, (doc, cells, truth) in enumerate(split_documents("test")):
            stages = ["phone_weak", "phone_strong"]
            if font == "nanummyeongjo" and doc == "resident_abstract":
                stages = ["clean", "scan300", "blur", "rotate"] + stages
            base = render(cells, font_path(font))
            for stage in stages:
                stage_index = STAGES.index(stage)
                rng = np.random.default_rng(np.random.SeedSequence([seed, font_index, doc_index, stage_index]))
                image, _, _ = degrade_with_geometry(base, stage, rng)
                for rectified in (False, True) if stage.startswith("phone") else (False,):
                    corrected = rectify_document(image) if rectified else None
                    yield {"document": doc, "font": font, "degradation": stage,
                           "rectification_requested": rectified,
                           "rectification_applied": corrected.applied if corrected else False,
                           "truth": truth, "image": corrected.image if corrected else image}
    if include_legacy:
        # Legacy 906ec68 phone degradation is deterministic; it ignores RNG.
        for doc, cells, truth in documents():
            yield {"document": doc, "font": "bundled-cjk", "degradation": "legacy_phone",
                   "rectification_requested": False, "rectification_applied": False,
                   "truth": truth, "image": degrade(render(cells), "phone", np.random.default_rng(seed))}


def run_synthetic(*, seed=20261111, unmasked=False, include_legacy=False):
    rows = []
    for case in synthetic_cases(seed, include_legacy=include_legacy):
        image, truth = case.pop("image"), case.pop("truth")
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        page = PageImage(0, PageSource.UPLOAD, (595, 842), png=buf.getvalue(), pixel_size=image.size, dpi=300)
        result = run_ocr("own", page.png, page.pixel_size)
        if result.error:
            raise RuntimeError("Own OCR failed; verify local model installation")
        row = diagnose([(page, result)], case["document"], truth=truth, synthetic=True, unmasked=unmasked)
        row.update(case)
        rows.append(row)
    return {"schema_version": 1, "synthetic": True, "seed": seed, "masked": not unmasked, "rows": rows}


def run_file(path, doc, *, gt=None, engine="own"):
    """Explicit real input, always masked; no implicit files or directories."""
    pages = raster_pages(Path(path))
    pairs = []
    for page in pages:
        result = run_ocr(engine, page.png, page.pixel_size)
        if result.error:
            raise RuntimeError("OCR failed")
        pairs.append((page, result))
    truth = json.loads(Path(gt).read_text(encoding="utf-8")) if gt else None
    return {"schema_version": 1, "synthetic": False, "masked": True,
            "rows": [diagnose(pairs, doc, truth=truth)]}


def main(argv=None):
    parser = _SafeParser(description=__doc__)
    parser.add_argument("file", nargs="?", type=Path)
    parser.add_argument("--doc", choices=DOCS, default="resident_abstract")
    parser.add_argument("--engine", choices=("own", "applevision"), default="own")
    parser.add_argument("--gt", type=Path, help="Optional flat extractor-field truth JSON; values never printed")
    parser.add_argument("--synthetic-suite", action="store_true")
    parser.add_argument("--include-legacy", action="store_true")
    parser.add_argument("--unmasked-synthetic", action="store_true")
    parser.add_argument("--seed", type=int, default=20261111)
    parser.add_argument("--output", type=Path, help="Explicit JSON destination; parent must already exist")
    args = parser.parse_args(argv)
    if args.synthetic_suite == (args.file is not None):
        parser.error("Choose either a file or --synthetic-suite")
    if args.unmasked_synthetic and not args.synthetic_suite:
        parser.error("--unmasked-synthetic requires --synthetic-suite")
    if args.synthetic_suite and (args.gt or args.engine != "own"):
        parser.error("Synthetic suite uses authored truth and own OCR")
    try:
        with quiet_dependencies():
            report = run_synthetic(seed=args.seed, unmasked=args.unmasked_synthetic,
                                   include_legacy=args.include_legacy) if args.synthetic_suite else run_file(args.file, args.doc, gt=args.gt, engine=args.engine)
        serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            args.output.write_text(serialized, encoding="utf-8")
            print(json.dumps({"ok": True, "rows": len(report["rows"]), "masked": report["masked"]}))
        else:
            print(serialized, end="")
        return 0
    except Exception:
        print(json.dumps({"ok": False, "reason": "diagnostic_input_or_execution_failed"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

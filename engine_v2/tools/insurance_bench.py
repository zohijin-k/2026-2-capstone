"""Benchmark-only insurance_4 contracts and JBAI logical table adapter.

Logical coordinates encode table order, never document geometry. Only the
existing insurance_4 extractor supplies fields; no eligibility rules run here.
"""
from __future__ import annotations

import json
import re

ROW_KEYS = ("insurance", "name", "subscriber_category", "management_number",
            "workplace_name", "acquired", "received", "status")
ROW_LABELS = ("보험", "성명", "가입자종별", "사업장관리번호", "사업장명칭",
              "자격취득일", "신고접수일", "상태")


def field_metrics(truth, actual):
    from .extract_check import _expected
    from .private_bench import _value_text
    from .synth_bench import cer
    expected = _expected("insurance_4", truth)
    labels = {"name": "성명", "birth_date": "생년월일", "issue_date": "발급일",
              "document_number": "문서확인번호", "rows": "가입내역"}
    metrics = {}
    for key, label in labels.items():
        if key not in truth:
            continue
        wanted, observed = expected.get(label), actual.get(label)
        if key == "rows":
            def rows(value):
                if value is None:
                    return None
                return [{key: row.get(label, "") for key, label in zip(ROW_KEYS, ROW_LABELS)}
                        for row in json.loads(value)]
            wanted = rows(wanted) if wanted is not None else []
            observed = rows(observed)
        metrics[key] = {"match": "O" if wanted == observed else "X",
                        "cer": cer(_value_text(key, wanted), _value_text(key, observed))}
    return metrics


def extract_jbai(document, *, today):
    """Place recognized header labels and six-column tables on a logical grid.

    Missing/unsupported tables remain missing. Never synthesize text, identifiers
    or a resident-number tail to satisfy the coordinate extractor.
    """
    from ..extractors import insurance_4
    from ..pipeline.ocr import OcrResult, OcrWord
    from ..pipeline.preprocess import PageImage, PageSource
    from ..schemas.models import ExtractedField, FieldSource
    pages, births = [], []
    for page in document.pages:
        words = []
        def put(text, x, y):
            if text.strip():
                words.append(OcrWord(text.strip(), .85, (x * 10, y * 14, (x + 7) * 10, (y + .8) * 14)))
        for line in page.text_lines:
            flat = re.sub(r"\s+", "", line)
            for label, x, y in (("문서확인번호", 12, 3), ("발급번호", 10, 21),
                                ("발급일시", 58, 21), ("성명", 60, 25)):
                match = re.search(re.escape(label) + r"\s*[:：]?\s*(.*?)(?=발급번호|발급일시|성명|주민|외국인|$)", line)
                if match:
                    put(label, x, y)
                    put(match.group(1), x + (20 if label == "성명" else 16), y)
            if "4대사회보험" in flat or "가입자가입내역확인서" in flat:
                put(line, 14, 13 if "4대사회보험" in flat else 16)
            rrn = re.search(r"(?<!\d)(\d{6})\s*[-‐‑‒–—―]\s*([0-8])(?:[\d*＊●Xx·•]\s*){6}(?!\d)", line)
            if rrn:
                birth = insurance_4._birth_from_rrn(rrn.group(1), rrn.group(2))
                if birth:
                    births.append(birth)
        row_index = 0
        for table in page.tables:
            header = "".join(cell.text for row in table.rows for cell in row)
            if not all(token in re.sub(r"\s+", "", header) for token in ("가입자종별", "자격취득일", "신고접수일")):
                continue
            header_seen = False
            for cells in table.rows:
                text = "".join(cell.text for cell in cells)
                if "자격취득일" in re.sub(r"\s+", "", text):
                    header_seen = True
                    for cell, x in zip(cells, (9, 23, 34, 48, 65, 82)):
                        put(cell.text, x, 31)
                    continue
                if not header_seen or not cells:
                    continue
                if not any(name in re.sub(r"\s+", "", cells[0].text) for name in insurance_4.INSURANCE_NAMES):
                    continue
                expanded = [cell.text for cell in cells for _ in range(cell.colspan)]
                if len(expanded) != 6:
                    continue
                y = 36 + row_index * 4
                row_index += 1
                for index, (text, x) in enumerate(zip(expanded, (9, 23, 34, 48, 65, 82))):
                    if index == 5:
                        parts = re.split(r"(?=[(（])", text, maxsplit=1)
                        for offset, part in enumerate(parts):
                            put(part.replace("（", "(").replace("）", ")"), x, y + offset)
                    else:
                        put(text, x, y)
        image = PageImage(page.page, PageSource.RENDER, (595, 842), pixel_size=(1000, 1400))
        pages.append((image, OcrResult("jbai", words)))
    result = insurance_4.extract(pages, today=today)
    if births and len(set(births)) == 1:
        result.fields["생년월일"] = ExtractedField(value=births[0], raw_text="", confidence=.85, source=FieldSource.VLM)
    for field in result.fields.values():
        field.source = FieldSource.VLM
        field.bbox = None
    return result

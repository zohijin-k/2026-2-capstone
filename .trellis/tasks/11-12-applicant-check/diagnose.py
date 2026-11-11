"""Synthetic, read-only diagnoses of short PDF routing and uncertain decisions."""
import copy
import json
import os
import sys
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
TASK = Path(__file__).resolve().parent
os.environ.pop("ENGINE_V2_OCR", None)
os.environ.pop("JBAI_API_KEY", None)
os.environ.pop("JBAI_ALLOW_REAL_DOCS", None)

from demo.backend.tests.run_p16_job_docs_scenarios import make_text_pdf, slots, IDENTITY
from demo.backend.rules.doc_check import check_document
from demo.backend.rules.required_docs import DocRequirement
from demo.backend.rules.doc_types import DocType
from demo.backend.rules.criteria import default_criteria, issue_bounds
from demo.backend.ocr import read_document
from demo.backend.ocr.pdftext import _read_pdf, extract_issue_date
from demo.backend.ocr.base import OcrResult
from engine_v2 import engine as v2engine
from engine_v2.pipeline.preprocess import preprocess, TEXT_LAYER_MIN_CHARS

def emit(label, value):
    print(label, json.dumps(value, ensure_ascii=False), flush=True)

def outcome(req, ocr, identity=None):
    result = check_document(req, ocr, identity=identity)
    return {"status": result.status, "findings": [f.as_dict() for f in result.findings]}

with tempfile.TemporaryDirectory(prefix="diagnose-", dir=TASK) as directory:
    path = make_text_pdf(Path(directory) / "short-exam.pdf", ["응 시 확 인 서", "성명 김가상", "종목명 정보처리기능사", "발급일자 2026. 4. 30."])
    import pymupdf
    with pymupdf.open(path) as doc:
        text = doc[0].get_text().strip()
    calls = []
    run = v2engine.run_ocr
    def capture(*args, **kwargs):
        result = run(*args, **kwargs)
        calls.append({"requested": args[0], "actual": result.engine, "error": result.error})
        return result
    with patch.object(v2engine, "run_ocr", side_effect=capture):
        actual = read_document(str(path), DocType.EXAM_CONFIRMATION)
    tier2 = _read_pdf(path)
    emit("SHORT_PDF", {"characters": len(text), "threshold": TEXT_LAYER_MIN_CHARS,
        "source": preprocess(path)[0].source.value, "calls": calls,
        "returned": {"tier": actual.tier, "engine": actual.engine, "confidence": actual.confidence},
        "actual_decision": outcome(slots()["certificate_1_exam"], actual, IDENTITY),
        "direct_pdftext_confidence": tier2.confidence,
        "direct_pdftext_decision": outcome(slots()["certificate_1_exam"], tier2, IDENTITY)})
    generic_path = make_text_pdf(Path(directory) / "generic-no-owner.pdf", ["사업자등록증명", "발급일자 2026. 11. 10."])
    generic_read = read_document(str(generic_path), DocType.BIZ_REG_PROOF)
    generic_slot = DocRequirement(slot_key="work_proof", doc_type=DocType.BIZ_REG_PROOF,
        label="사업자등록증명", min_issue_date=date(2026, 3, 3))
    emit("REAL_TEXT_PDF_NO_OWNER", {"confidence": generic_read.confidence,
        "fields": generic_read.fields, "decision": outcome(generic_slot, generic_read, IDENTITY)})

req = DocRequirement(slot_key="resident_abstract", doc_type=DocType.RESIDENT_ABSTRACT,
    label="주민등록초본", min_issue_date=date(2026, 3, 3))
resident = OcrResult(detected_doc_type=DocType.RESIDENT_ABSTRACT, confidence=.5, image_quality=.9,
    tier="localocr", engine="own", fields={"발급일": "2026-11-10", "성명": IDENTITY.name,
    "생년월일": "1999-01-01", "초본신청인성명": "이가상", "초본신청인생년월일": "1999-01-01"})
emit("UNCERTAIN_APPLICANT_MISMATCH", outcome(req, resident, IDENTITY))
old = copy.deepcopy(resident)
old.fields.update({"초본신청인성명": IDENTITY.name, "발급일": "2025-11-10"})
emit("UNCERTAIN_OLD_ISSUE", outcome(req, old, IDENTITY))
generic_req = DocRequirement(slot_key="work_proof", doc_type=DocType.BIZ_REG_PROOF,
    label="사업자등록증명", min_issue_date=date(2026, 3, 3))
missing = OcrResult(detected_doc_type=DocType.BIZ_REG_PROOF, confidence=.95,
    image_quality=1, tier="pdftext", engine="pdftext", fields={})
emit("MISSING_ALL_IDENTITY_AND_DATE", outcome(generic_req, missing, IDENTITY))
history_req = DocRequirement(slot_key="nhis_acquisition_loss", doc_type=DocType.NHIS_ACQUISITION_LOSS,
    label="건강보험 자격득실확인서", recent_years=5)
history = OcrResult(detected_doc_type=DocType.NHIS_ACQUISITION_LOSS, confidence=.5,
    image_quality=1, tier="localocr", engine="own",
    fields={"발급일": "2026-11-10", "자격이력자료": "not-json"})
emit("HISTORY_UNREADABLE", outcome(history_req, history))
image = copy.deepcopy(resident)
image.fields["초본신청인성명"] = IDENTITY.name
image.image_quality = .55
emit("LOW_IMAGE_QUALITY", outcome(req, image, IDENTITY))
emit("UNLABELED_ISSUE_DATE", str(extract_issue_date("거래일 2026-04-12\n생년월일 1999-01-01")))
criteria = default_criteria("double_savings")
for mode in ({"mode": "after_notice"}, {"mode": "after_date", "date": "2026-04-01"},
    {"mode": "within_days", "days": 30}, {"mode": "none"}):
    criteria["document_issue_rules"]["resident_abstract"] = mode
    emit("DATE_MODE", {"rule": mode, "bounds": [str(d) if d else None for d in issue_bounds(criteria, "resident_abstract", date(2026, 11, 12))]})

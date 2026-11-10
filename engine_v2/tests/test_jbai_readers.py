from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from ..extractors.jbai_text import extract
from ..pipeline.jbai_ocr import JBAIDocumentResult, JBAIPageResult, parse_otsl_tables
from ..schemas.models import DocType

FIXTURES = Path(__file__).parent / "fixtures" / "jbai_synthetic"


def _replay(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    pages = [JBAIPageResult(
        page=item["page"], text_lines=item["ocr_content"].splitlines(),
        tables=parse_otsl_tables(item["table_content"]), elapsed_sec=0.0,
        raw_content=item["ocr_content"], table_content=item["table_content"],
    ) for item in data["pages"]]
    return data["expected"], extract(
        JBAIDocumentResult(pages=pages, elapsed_sec=0.0), DocType(data["doc_type"]),
        today=date(2026, 11, 10),
    )


def test_synthetic_resident_reader_replay():
    expected, result = _replay(FIXTURES / "resident_abstract.json")
    checks = {
        "name": result.fields["name"].value == expected["name"],
        "birth_date": result.fields["birth_date"].value.isoformat() == expected["birth_date"],
        "issue_date": result.fields["issue_date"].value.isoformat() == expected["issue_date"],
        "applicant_name": result.fields["applicant_name"].value == expected["applicant_name"],
        "applicant_birth_date": result.fields["applicant_birth_date"].value.isoformat() == expected["applicant_birth_date"],
        "history_count": len(result.history) == expected["history_count"],
    }
    assert checks == {key: True for key in checks}
    assert sum(checks.values()) == 6


def test_synthetic_payment_reader_replay():
    expected, result = _replay(FIXTURES / "nhis_payment.json")
    billed = json.loads(result.fields["월별고지금액"].value)
    care = json.loads(result.fields["월별장기요양보험료"].value)
    checks = {
        "name": result.fields["성명"].value == expected["name"],
        "birth_date": str(result.fields["생년월일"].value) == expected["birth_date"],
        "issue_date": str(result.fields["발급일"].value) == expected["issue_date"],
        "insurance_type": result.fields["가입구분"].value == expected["insurance_type"],
        "billed_months": billed == {key: str(value) for key, value in expected["billed_by_month"].items()},
        "care_months": care == {key: str(value) for key, value in expected["long_term_care_by_month"].items()},
        "average": result.fields["건강보험료"].value == "6633",
        "care_average": result.fields["장기요양보험료"].value == "810",
    }
    assert checks == {key: True for key in checks}
    assert sum(checks.values()) == 8


def test_synthetic_acquisition_loss_reader_replay():
    expected, result = _replay(FIXTURES / "nhis_acquisition_loss.json")
    history = json.loads(result.fields["자격이력자료"].value)["rows"]
    checks = {
        "name": result.fields["성명"].value == expected["name"],
        "birth_date": str(result.fields["생년월일"].value) == expected["birth_date"],
        "issue_date": str(result.fields["발급일"].value) == expected["issue_date"],
        "history": history == expected["history"],
        "recent_five_years": result.fields["변동내역"].value == "최근 5년 포함",
        "latest_acquisition": str(result.fields["취득일"].value) == "2023-06-01",
    }
    assert checks == {key: True for key in checks}
    assert sum(checks.values()) == 6

"""취업지원패키지 서류를 팀 평가 도구(make_synth_eval·synth_bench·ocr_bench/private_bench·extract_diag)에
붙인 것의 시험. 모든 값은 가상이며, OCR 모델·글꼴 없이 완전 OCR 단어로 돈다."""
from datetime import date
import json

from PIL import Image
import pytest

from engine_v2.extractors import job_common as job
from engine_v2.pipeline.layout import normalize
from engine_v2.pipeline.ocr import OcrResult, OcrWord
from engine_v2.pipeline.preprocess import PageImage, PageSource
from engine_v2.schemas.models import ExtractedField, FieldSource
from engine_v2.tools import extract_diag
from engine_v2.tools import private_bench as bench
from engine_v2.tools.make_synth_eval import SPLITS, documents, job_documents, split_documents
from engine_v2.tools.synth_bench import EXTRACTORS, field_matches

JOB_KINDS = ["receipt", "exam_admission", "exam_score", "interview_confirm"]
CORE_KINDS = ["resident_abstract", "nhis_payment", "nhis_acquisition_loss"]


def perfect_page(cells):
    """test_synth_eval과 같은 완전 OCR 단어 (A4 300dpi, 글자 하나 너비 1.3%)."""
    words = [OcrWord(t, 1, (x*24.8, (y-1)*35.08, (x+len(t)*1.3)*24.8, y*35.08)) for x, y, t in cells]
    return PageImage(0, PageSource.UPLOAD, (595, 842), pixel_size=(2480, 3508)), OcrResult("perfect", words)


def field(value):
    return ExtractedField(value=value, raw_text="가짜", confidence=.9, source=FieldSource.OCR)


@pytest.mark.parametrize("split", sorted(SPLITS))
def test_job_suite_fields_match_on_perfect_ocr(split):
    """test 배치(값이 라벨 옆)와 train 배치(머리 칸 값이 라벨 아래) 모두 정답과 같아야 한다."""
    kinds = []
    for kind, cells, truth in split_documents(split, suite="job_package"):
        kinds.append(kind)
        result = EXTRACTORS[kind]([perfect_page(cells)], today=date(2026, 11, 11))
        matches = field_matches(result, truth)
        assert all(matches.values()), (split, kind, matches, {k: v.value for k, v in result.fields.items()})
        assert all(item.passed for item in result.validations), (split, kind, result.validations)
    assert kinds == JOB_KINDS


def test_core_suite_is_unchanged_by_default():
    """기본 세트(기준선 결과·진단 재현 사례 수)는 패키지 세트를 넣어도 그대로다."""
    assert [kind for kind, _, _ in documents()] == CORE_KINDS
    assert [kind for kind, _, _ in split_documents("test")] == CORE_KINDS
    assert [kind for kind, _, _ in job_documents()] == JOB_KINDS


def test_package_docs_are_registered_in_team_tools():
    assert set(JOB_KINDS) <= set(EXTRACTORS)
    assert set(JOB_KINDS) <= set(extract_diag.DOCS) and set(JOB_KINDS) <= set(extract_diag.FIELDS)
    assert set(JOB_KINDS) <= set(bench.DOCS) and set(JOB_KINDS) <= set(bench.KEYS)


def test_private_bench_compares_make_gt_contracts_for_package_docs():
    truth = {"amount": "45000", "payment_date": "2026-03-15", "store": "한빛정장대여",
             "brn": "123-45-67891", "payment_method": "카드"}
    fields = {"결제금액": field("45000"), "결제일": field("2026-03-15"), "상호": field("한빛정장대여"),
              "사업자등록번호": field("123-45-67891"), "결제수단": field("카드")}
    measured = bench.field_metrics("receipt", truth, type("R", (), {"fields": fields})())
    assert set(measured) == set(truth)
    assert all(row == {"match": "O", "cer": 0} for row in measured.values())

    truth = {"name": "가상시험", "exam_name": "정보처리기능사", "exam_date": "2026-03-22"}
    fields = {"성명": field("가상시험"), "시험명": field("정보처리기능사"), "응시일": field("2026-03-21")}
    measured = bench.field_metrics("exam_admission", truth, type("R", (), {"fields": fields})())
    assert measured["exam_date"]["match"] == "X" and measured["name"]["match"] == "O"


def test_private_bench_skips_jbai_for_package_docs(tmp_path, monkeypatch, capfd):
    image = tmp_path / "receipt.png"
    Image.new("RGB", (300, 400), "white").save(image)
    gt = tmp_path / "truth.json"
    gt.write_text(json.dumps({"amount": "45000"}), encoding="utf-8")
    monkeypatch.setattr(bench, "unavailable", lambda engine: 0)
    monkeypatch.setattr(bench, "run_engine", lambda *args, **kwargs: {"pages": 1})
    report = bench.run_private(image, gt, ("own", "jbai"), doc="receipt")
    rows = {row["engine"]: row for row in report["rows"]}
    assert (rows["jbai"]["skipped"], rows["jbai"]["reason_code"]) == ("O", 6)
    assert (rows["own"]["skipped"], rows["own"]["pages"]) == ("X", 1)
    capfd.readouterr()


def test_diag_trace_for_package_doc_is_value_free():
    _, cells, truth = next(item for item in job_documents() if item[0] == "receipt")
    report = extract_diag.diagnose([perfect_page(cells)], "receipt", truth=truth)
    dumped = json.dumps(report, ensure_ascii=False)
    for value in ("70,000", "70000", "가상정장대여", "123-45-67891", "2026.04.01", "2026-04-01"):
        assert value not in dumped
    assert report["detected_type"] == "receipt"
    assert report["validations"]["amount_found"] is True
    assert {"합계금액", "가맹점명", "결제일시"} <= set(report["pages"][0]["labels_found"])
    assert all(row["match"] for row in report["fields"].values())


def test_dash_variants_are_normalized_only_for_parsing():
    assert job.parse_brn("123－45－67891") == "123-45-67891"   # 전각 하이픈
    assert job.parse_date("2026−03−15") == date(2026, 3, 15)    # 빼기 기호
    original = OcrWord("990101−1234567", .99, (0, 0, 100, 10))  # 빼기 기호로 읽힌 주민번호
    words = normalize([original], 0, (1000, 1400))
    assert job.scrub_rrn(words, [original]) == date(1999, 1, 1)
    assert original.text == "990101−1******"  # 원문 대시 모양은 그대로, 뒷자리만 지움

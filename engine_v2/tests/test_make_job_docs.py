"""합성기 ↔ 판독기 왕복 시험. 글자층 PDF는 OCR 없이 읽히므로 정답과 그대로 맞아야 한다 (가상 값만)."""
from ..engine import EXTRACTORS, _load_pages
from ..schemas.models import DocType, DocumentInput
from ..tools import make_job_docs
from ..tools.extract_check import JOB_DOCS, _differs, _expected


def test_engine_registers_package_extractors():
    for doc_type in (DocType.RECEIPT, DocType.EXAM_ADMISSION, DocType.EXAM_SCORE, DocType.INTERVIEW_CONFIRM):
        assert doc_type in EXTRACTORS


def test_generated_text_pdfs_read_back_exactly(tmp_path):
    manifest = make_job_docs.generate(tmp_path, n=1, seed=11, conditions=("text",))
    assert len(manifest["files"]) == len(make_job_docs.LAYOUTS)
    for entry in manifest["files"]:
        doc_type, extractor = JOB_DOCS[entry["doc"]]
        document = DocumentInput(doc_id=entry["file"], declared_type=doc_type,
                                 file_path=str(tmp_path / entry["file"]))
        pages = _load_pages(document, "off")  # 글자층이라 OCR 엔진을 부르지 않는다
        assert not isinstance(pages, str), pages
        result = extractor(pages)
        assert result.detected_type.value == entry["expect_type"], entry["file"]
        failed = {item.name for item in result.validations if not item.passed}
        assert set(entry["expect_failed"]) <= failed, (entry["file"], failed)
        for label, wanted in _expected(entry["doc"], entry["gt"]).items():
            assert label in result.fields, (entry["file"], label)
            assert not _differs(entry["doc"], result.fields[label].value, wanted), (entry["file"], label)
        if entry["expect_type"] != "unknown":
            assert failed == set(entry["expect_failed"]), (entry["file"], failed)

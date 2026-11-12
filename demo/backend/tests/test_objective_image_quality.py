"""Authored files separate original resolution from recognition confidence."""
from copy import deepcopy
from io import BytesIO
from types import SimpleNamespace

from PIL import Image
import pymupdf
import pytest

from demo.backend import ocr as chain
from demo.backend.ocr.base import OcrResult
from demo.backend.ocr.file_evidence import objective_image_quality, original_image_sizes
from demo.backend.rules.doc_check import check_document
from demo.backend.rules.doc_types import DocType
from demo.backend.rules.required_docs import DocRequirement
from demo.backend.upload_assessment import assess_nhis_identity


NORMAL_SIZES = [(1654, 2338), (2065, 2923), (2480, 3505),
                (3024, 4032), (4032, 3024), (1080, 1920)]


def image_file(path, size):
    with Image.new("RGB", size, "white") as image:
        image.save(path)
    return path


def bitmap(size):
    buffer = BytesIO()
    with Image.new("RGB", size, "white") as image:
        image.save(buffer, format="PNG")
    return buffer.getvalue()


def text_page(document, *, decoration=False):
    page = document.new_page(width=595, height=842)
    page.insert_textbox(pymupdf.Rect(30, 30, 560, 150),
                        "FAKE synthetic scalable text. No real document or identity. " * 3)
    if decoration:
        page.insert_image(pymupdf.Rect(30, 180, 50, 200), stream=bitmap((10, 10)))
    return page


def scan_page(document, size, *, width=595, height=842):
    page = document.new_page(width=width, height=height)
    page.insert_image(page.rect, stream=bitmap(size), keep_proportion=False)
    return page


def adapter_result(monkeypatch, *, confidence=.99, quality=0.0, tier="localocr", encrypted=False):
    result = OcrResult(detected_doc_type=DocType.ADMIN_INFO_CONSENT,
                       confidence=confidence, image_quality=quality,
                       tier=tier, is_encrypted=encrypted)
    monkeypatch.setattr(chain, "CHAIN", [SimpleNamespace(read=lambda *_: deepcopy(result))])


def requirement():
    return DocRequirement(slot_key="FAKE-quality", doc_type=DocType.ADMIN_INFO_CONSENT,
                          label="가짜 합성서류")


@pytest.mark.parametrize("suffix", ["png", "jpg"])
@pytest.mark.parametrize("size", NORMAL_SIZES)
def test_normal_original_images_have_no_quality_warning(tmp_path, monkeypatch, suffix, size):
    path = image_file(tmp_path / f"FAKE.{suffix}", size)
    adapter_result(monkeypatch)
    read = chain.read_document(str(path))
    assert read.image_quality == (.9 if min(size) >= 1400 else .75)
    assert "LOW_IMAGE_QUALITY" not in check_document(requirement(), read, file_format=suffix).codes
    assert set(read.fields) == {"원본이미지크기"}


@pytest.mark.parametrize("short,expected", [(699, .35), (700, .55), (999, .55),
                                            (1000, .75), (1399, .75), (1400, .9)])
def test_raw_original_short_side_bands_are_preserved(tmp_path, short, expected):
    path = image_file(tmp_path / "FAKE.png", (short, 1800))
    assert objective_image_quality(str(path)) == expected


@pytest.mark.parametrize("size", NORMAL_SIZES[:3])
def test_normal_original_embedded_a4_images_have_no_quality_warning(tmp_path, monkeypatch, size):
    path = tmp_path / "FAKE-scan.pdf"
    with pymupdf.open() as document:
        scan_page(document, size)
        document.save(path)
    adapter_result(monkeypatch)
    read = chain.read_document(str(path))
    assert read.image_quality == .9
    assert "LOW_IMAGE_QUALITY" not in check_document(requirement(), read).codes
    assert original_image_sizes(str(path)) == [{"page": 0, "width": size[0], "height": size[1]}]


@pytest.mark.parametrize("dpi,expected", [(149, .5), (150, .7), (199, .7), (200, .9)])
def test_original_embedded_pdf_dpi_bands_are_preserved(tmp_path, dpi, expected):
    path = tmp_path / "FAKE-scan.pdf"
    with pymupdf.open() as document:
        scan_page(document, (dpi * 10, dpi * 12), width=720, height=864)
        document.save(path)
    assert objective_image_quality(str(path)) == expected


@pytest.mark.parametrize("decoration", [False, True])
def test_scalable_text_pdf_has_quality_one_despite_tiny_decoration(tmp_path, monkeypatch, decoration):
    path = tmp_path / "FAKE-text.pdf"
    with pymupdf.open() as document:
        text_page(document, decoration=decoration)
        document.save(path)
    adapter_result(monkeypatch, confidence=.1, quality=.01)
    read = chain.read_document(str(path))
    assert read.image_quality == 1.0
    assert original_image_sizes(str(path)) == []
    checked = check_document(requirement(), read)
    assert "LOW_IMAGE_QUALITY" not in checked.codes
    assert "LOW_OCR_CONFIDENCE" in checked.codes


def test_mixed_pdf_keeps_original_scan_quality(tmp_path, monkeypatch):
    path = tmp_path / "FAKE-mixed.pdf"
    with pymupdf.open() as document:
        text_page(document, decoration=True)
        scan_page(document, (1000, 1400))
        document.save(path)
    adapter_result(monkeypatch)
    read = chain.read_document(str(path))
    assert read.image_quality == .5
    assert original_image_sizes(str(path)) == [{"page": 1, "width": 1000, "height": 1400}]
    assert "LOW_IMAGE_QUALITY" in check_document(requirement(), read).codes


@pytest.mark.parametrize("kind", ["vector", "small-bitmap", "unsupported", "missing", "corrupt"])
def test_unmeasured_original_quality_is_neutral(tmp_path, monkeypatch, kind):
    path = tmp_path / "FAKE.pdf"
    if kind in {"vector", "small-bitmap"}:
        with pymupdf.open() as document:
            page = document.new_page()
            page.draw_rect(pymupdf.Rect(30, 30, 300, 300))
            if kind == "small-bitmap":
                page.insert_image(pymupdf.Rect(30, 350, 300, 500), stream=bitmap((200, 100)))
            document.save(path)
    elif kind == "unsupported":
        path = tmp_path / "FAKE.txt"
        path.write_text("FAKE synthetic unmeasured source")
    elif kind == "corrupt":
        path.write_bytes(b"FAKE synthetic corrupt PDF")
    adapter_result(monkeypatch, confidence=.1, quality=.1)
    read = chain.read_document(str(path))
    assert read.image_quality == 1.0
    assert original_image_sizes(str(path)) == []
    assert "LOW_IMAGE_QUALITY" not in check_document(requirement(), read).codes


@pytest.mark.parametrize("confidence", [0.0, .1, .99])
def test_good_original_quality_is_independent_of_adapter_confidence(tmp_path, monkeypatch, confidence):
    path = image_file(tmp_path / "FAKE.png", NORMAL_SIZES[0])
    adapter_result(monkeypatch, confidence=confidence, quality=.01)
    read = chain.read_document(str(path))
    assert read.image_quality == .9
    assert "LOW_IMAGE_QUALITY" not in check_document(requirement(), read).codes


@pytest.mark.parametrize("size,expected", [(NORMAL_SIZES[0], .9), ((970, 1282), .55)])
def test_no_recognition_still_uses_original_image_measurement(tmp_path, monkeypatch, size, expected):
    path = image_file(tmp_path / "FAKE.png", size)
    monkeypatch.setattr(chain, "CHAIN", [])
    read = chain.read_document(str(path))
    assert read.confidence == 0.0
    assert read.tier == "none"
    assert read.image_quality == expected


def test_no_recognition_and_no_original_measurement_stays_neutral(tmp_path, monkeypatch):
    monkeypatch.setattr(chain, "CHAIN", [])
    read = chain.read_document(str(tmp_path / "FAKE-missing.pdf"))
    assert read.confidence == 0.0
    assert read.image_quality == 1.0


@pytest.mark.parametrize("tier,encrypted", [("fixture", False), ("pdftext", True)])
def test_explicit_fixture_or_unreadable_quality_is_preserved(tmp_path, monkeypatch, tier, encrypted):
    path = image_file(tmp_path / "FAKE.png", NORMAL_SIZES[0])
    adapter_result(monkeypatch, quality=.2, tier=tier, encrypted=encrypted)
    read = chain.read_document(str(path))
    assert read.image_quality == .2


@pytest.mark.parametrize("quality,expected", [("missing", 1.0), (None, 1.0), (0.0, 0.0), (.5, .5), (.9, .9)])
def test_nhis_rehydration_defaults_only_absent_quality_to_neutral(monkeypatch, quality, expected):
    from demo.backend import upload_assessment
    from demo.backend.rules.doc_check import CheckResult
    raw = {} if quality == "missing" else {"image_quality": quality}
    row = SimpleNamespace(doc_type=str(DocType.NHIS_PAYMENT), slot_key="nhis_payment",
                          ocr_json=raw, declared_issue_date=None, file_format="pdf")
    req = DocRequirement(slot_key="nhis_payment", doc_type=DocType.NHIS_PAYMENT, label="가짜 납부서류")
    observed = []

    def capture(_, read, *args, **kwargs):
        observed.append(read.image_quality)
        return CheckResult("NEEDS_REVIEW", [])

    monkeypatch.setattr(upload_assessment, "check_document", capture)
    assess_nhis_identity(None, [req], [row])
    assert observed == [expected]
    assert raw == ({} if quality == "missing" else {"image_quality": quality})


def test_certified_dissimilar_attachment_does_not_lower_bounded_main_form_quality(tmp_path, monkeypatch):
    import json
    from demo.backend.ocr.localocr import LocalOcr
    from demo.backend.ocr.pdftext import PdfTextOcr
    from engine_v2.tests.nhis_form_samples import insurance_portal_cells, text_pdf

    first = text_pdf(tmp_path / "FAKE-main.pdf", insurance_portal_cells())
    path = tmp_path / "FAKE-with-attachment.pdf"
    with pymupdf.open(first) as source, pymupdf.open() as document:
        document.insert_pdf(source)
        scan_page(document, (100, 140))
        document.save(path)
    monkeypatch.setenv("ENGINE_V2_OCR", "off")
    monkeypatch.setattr(chain, "CHAIN", [LocalOcr(), PdfTextOcr()])
    read = chain.read_document(str(path), DocType.NHIS_PAYMENT)
    assert read.detected_doc_type == DocType.INSURANCE_4
    assert read.fields["양식판독상태"] == "완전"
    assert json.loads(read.fields["추가첨부쪽"]) == [2]
    assert read.page_count == 2
    assert objective_image_quality(str(path)) == .5
    assert read.image_quality == 1.0
    req = DocRequirement(slot_key="work_proof", doc_type=DocType.INSURANCE_4, label="가짜 근로서류")
    assert "LOW_IMAGE_QUALITY" not in check_document(req, read).codes


@pytest.mark.parametrize("excluded", ["FAKE", "[1, 2]", "[2, 2]", "[true]", '["2"]', "[3]"])
def test_malformed_attachment_scope_cannot_hide_low_original_quality(tmp_path, monkeypatch, excluded):
    path = tmp_path / "FAKE-scope.pdf"
    with pymupdf.open() as document:
        text_page(document)
        scan_page(document, (1000, 1400))
        document.save(path)
    result = OcrResult(detected_doc_type=DocType.INSURANCE_4, confidence=.99,
                       fields={"추가첨부쪽": excluded}, page_count=2, tier="localocr")
    monkeypatch.setattr(chain, "CHAIN", [SimpleNamespace(read=lambda *_: deepcopy(result))])
    assert chain.read_document(str(path)).image_quality == .5


@pytest.mark.parametrize("rotation", [90, 270])
@pytest.mark.parametrize("size", NORMAL_SIZES[:5])
def test_rotated_normal_original_scans_keep_pixel_axis_dpi(tmp_path, monkeypatch, rotation, size):
    path = tmp_path / "FAKE-rotated.pdf"
    # Preserve the original image aspect ratio on a rotated physical page.
    width, height = (842, 595) if size[0] < size[1] else (595, 842)
    with pymupdf.open() as document:
        page = document.new_page(width=width, height=height)
        page.insert_image(page.rect, stream=bitmap(size), rotate=rotation, keep_proportion=False)
        document.save(path)
    adapter_result(monkeypatch)
    read = chain.read_document(str(path))
    assert read.image_quality == .9
    assert "LOW_IMAGE_QUALITY" not in check_document(requirement(), read).codes

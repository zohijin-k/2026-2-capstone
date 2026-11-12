"""Original source dimensions, conservative boundary, and independent folios."""
import json
import pytest
from PIL import Image
from demo.backend.ocr.base import OcrResult
from demo.backend.ocr.file_evidence import attach_file_evidence, independent_page_markers, resolution_defect
from demo.backend.rules.doc_types import DocType
from engine_v2.tests.fail_case_samples import tiny_unknown


@pytest.mark.parametrize("size,defect", [((586,709),True),((709,586),True),((970,1282),False),
                                        ((600,799),False),((599,800),False),((649,899),False),((650,900),False),((1654,2338),False),
                                        ((2065,2923),False),((2480,3505),False)])
def test_only_narrow_original_pixel_boundary_rejects_unknown(tmp_path,size,defect):
    path=tmp_path/"FAKE.png"
    Image.new("RGB",size,"white").save(path)
    read=attach_file_evidence(OcrResult(),str(path))
    assert bool(resolution_defect(read)) is defect
    assert json.loads(read.fields["원본이미지크기"])[0]["width"] == size[0]


def test_readable_tiny_document_does_not_fail_pixels_alone(tmp_path):
    path=tmp_path/"FAKE.png"
    Image.new("RGB",(586,709),"white").save(path)
    read=attach_file_evidence(OcrResult(detected_doc_type=DocType.INSURANCE_4,
        fields={"성명":"가짜이름","생년월일":"1990-01-01","발급일":"2026-03-03"}),str(path))
    assert resolution_defect(read) is None


def test_tiny_damaged_title_retains_folio_independent_of_type():
    evidence=independent_page_markers(tiny_unknown())
    assert evidence == {"markers":[[1,2]],"confidence":1}
    pages=tiny_unknown()
    next(w for w in pages[0][1].words if w.text=="1/2").confidence=.3
    assert independent_page_markers(pages)["confidence"] == .3

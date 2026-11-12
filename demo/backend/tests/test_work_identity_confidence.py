"""Fresh work facts require reliable source identity, beyond matching strings."""
from datetime import date

import pytest

from demo.backend.ocr.localocr import _from_insurance4, _from_nhis, _from_business_proof
from demo.backend.rules.doc_types import DocType
from demo.backend.rules.programs import PROGRAMS, DOUBLE_SAVINGS
from demo.backend.rules.required_docs import WorkCategory
from demo.backend.rules.work_continuity import assess_work
from engine_v2.extractors import insurance_4, nhis_acquisition_loss, business_registration
from engine_v2.pipeline.ocr import OcrWord
from engine_v2.schemas.models import DocType as V2DocType
from engine_v2.tests import nhis_form_samples, p2_form_samples, p2_business_samples


NOTICE=date(2026,3,3)


def fixture(kind):
    if kind=="insurance":
        cells=[(x,y,"2026.01.01" if text=="2020.01.01" else text)
               for x,y,text in nhis_form_samples.insurance_portal_cells()]
        pages=[nhis_form_samples.coordinate_page(cells)]
        extractor=insurance_4.extract
        converter=lambda ex:_from_insurance4(ex,pages)
        category=WorkCategory.EMPLOYEE
        identity={"name":nhis_form_samples.NAME,"birth":nhis_form_samples.BIRTH}
    elif kind=="history":
        cells,size=p2_form_samples.acquisition(noise=False)
        cells=[(*cell[:4],"직장가입자",cell[5]) if cell[4]=="지역세대주" else
               (*cell[:4],"2026.01.01",cell[5]) if cell[0]==1652 and cell[1]==1115 else cell for cell in cells]
        pages=[p2_form_samples.page(cells,size=size)]
        extractor=nhis_acquisition_loss.extract
        converter=lambda ex:_from_nhis(ex,pages,V2DocType)
        category=WorkCategory.EMPLOYEE
        identity={"name":p2_form_samples.NAME,"birth":p2_form_samples.BIRTH}
    else:
        cells,size=p2_business_samples.business(noise=False)
        cells=[(*cell[:4],"2026년 01월 02일",1) if cell[4]=="2018년 01월 02일" else cell for cell in cells]
        pages=[p2_business_samples.page(cells,size=size)]
        extractor=lambda pages:business_registration.extract(pages,today=date(2026,3,4))
        converter=lambda ex:_from_business_proof(ex,pages)
        category=WorkCategory.BUSINESS
        identity={"name":p2_business_samples.NAME,"birth":"1990-01-01"}
    return pages,extractor,converter,category,identity


def assessment(converted,category,identity):
    doc={"doc_type":str(converted.detected_doc_type),"confidence":converted.confidence,"image_quality":.95,
         "fields":converted.fields,"issue_date":converted.issue_date,"status":"PASS"}
    return assess_work(PROGRAMS[DOUBLE_SAVINGS],NOTICE,category,[doc],identity)


@pytest.mark.parametrize("kind",["insurance","history","business"])
@pytest.mark.parametrize("field",["name","birth"])
def test_low_confidence_matching_source_identity_cannot_establish_work_failure(kind,field):
    pages,extractor,converter,category,identity=fixture(kind)
    baseline=converter(extractor(pages))
    assert baseline.confidence>=.85 and assessment(baseline,category,identity).status=="NOT_MET"
    # The portal reader deliberately erases source RRN token text after reading.
    # Each independent recognition receives a fresh authored word batch.
    pages,extractor,converter,category,identity=fixture(kind)
    for _,result in pages:
        for word in result.words:
            if (field=="name" and word.text==identity["name"]) or (field=="birth" and "900101" in word.text):
                word.confidence=.1
    converted=converter(extractor(pages))
    assert converted.fields["성명"]==identity["name"]
    assert converted.fields["생년월일"]==identity["birth"]
    assert converted.confidence==.1
    assert assessment(converted,category,identity).status=="UNDETERMINED"


@pytest.mark.parametrize("kind",["insurance","history","business"])
def test_present_identity_without_source_box_requires_review(kind):
    pages,extractor,converter,category,identity=fixture(kind)
    ex=extractor(pages)
    ex.fields["성명"].bbox=None
    converted=converter(ex)
    assert converted.confidence<=.4
    assert assessment(converted,category,identity).status=="UNDETERMINED"


@pytest.mark.parametrize("kind",["insurance","history","business"])
def test_distant_low_confidence_notice_does_not_reduce_identity_confidence(kind):
    pages,extractor,converter,category,identity=fixture(kind)
    baseline=converter(extractor(pages))
    pages,extractor,converter,category,identity=fixture(kind)
    pages[0][1].words.append(OcrWord("FAKE",.1,(5,5,20,20)))
    converted=converter(extractor(pages))
    assert converted.confidence==baseline.confidence
    assert assessment(converted,category,identity).status=="NOT_MET"


@pytest.mark.parametrize("kind",["insurance","history","business"])
def test_low_confidence_issue_date_cannot_prove_work_at_notice(kind):
    pages,extractor,converter,category,identity=fixture(kind)
    box=extractor(pages).fields["발급일"].bbox
    pages,extractor,converter,category,identity=fixture(kind)
    touched=0
    for page,result in pages:
        for word in result.words:
            x0,y0,x1,y1=word.bbox_px
            x,y=page.px_to_pt((x0+x1)/2,(y0+y1)/2)
            if box.page==page.page and box.x0-.1<=x<=box.x1+.1 and box.y0-.1<=y<=box.y1+.1:
                word.confidence=.1
                touched+=1
    assert touched
    converted=converter(extractor(pages))
    assert converted.confidence==.1
    assert assessment(converted,category,identity).status=="UNDETERMINED"


def test_noncoordinate_reader_keeps_document_compatibility_but_not_new_work_certainty():
    pages,extractor,converter,category,identity=fixture("history")
    ex=extractor(pages)
    for field in ex.fields.values():
        field.bbox=None
    for _,result in pages:
        result.engine="jbai"
    converted=converter(ex)
    assert converted.confidence>=.85
    assert converted.fields["근로근거신뢰도"]=="0.4"
    assert assessment(converted,category,identity).status=="UNDETERMINED"

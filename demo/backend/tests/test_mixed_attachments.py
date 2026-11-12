"""Actual text-form plus unreadable image attachments preserves isolated form checks."""
import io
import json
from PIL import Image
import pymupdf
from demo.backend.ocr import read_document
from demo.backend.rules.doc_types import DocType
from demo.backend.tests.test_portal_uploads import client,new_app,upload
from engine_v2.tests.nhis_form_samples import insurance_portal_cells,text_pdf


def mixed_pdf(tmp_path,*,damage=False):
    cells=insurance_portal_cells()
    if damage:
        cells=[cell for cell in cells if cell[2]!="사업장명칭"]
    first=text_pdf(tmp_path/"FAKE-form.pdf",cells)
    path=tmp_path/"FAKE-mixed.pdf"
    content=io.BytesIO()
    Image.new("RGB",(2480,3508),"white").save(content,format="PNG")
    with pymupdf.open(first) as source,pymupdf.open() as doc:
        doc.insert_pdf(source)
        for _ in range(2):
            p=doc.new_page()
            p.insert_image(p.rect,stream=content.getvalue())
        doc.save(path)
    return path


def test_main_form_is_complete_with_unreadable_attachment_pages(client,tmp_path):
    path=mixed_pdf(tmp_path)
    read=read_document(str(path),DocType.NHIS_PAYMENT)
    assert read.detected_doc_type==DocType.INSURANCE_4
    assert read.confidence>=.9 and read.engine=="pdftext"
    assert read.page_count==3
    assert read.fields["양식판독상태"]=="완전"
    assert json.loads(read.fields["추가첨부쪽"])==[2,3]
    data,stored=upload(client,new_app(client),path,"work_proof")
    assert data["status"]=="PASS"
    assert stored["fields"]["추가첨부쪽"]==read.fields["추가첨부쪽"]


def test_incomplete_main_form_remains_review(client,tmp_path):
    data,stored=upload(client,new_app(client),mixed_pdf(tmp_path,damage=True),"work_proof")
    assert data["status"]=="NEEDS_REVIEW"
    assert stored["fields"]["양식판독상태"]=="불완전"

"""Fictitious daily-work PDFs exercise final reader and upload serialization."""
from datetime import date
import json

import pymupdf
import pytest

from demo.backend.ocr import read_document
from demo.backend.rules.doc_types import DocType
from demo.backend.tests.test_portal_uploads import client, new_app, upload
from demo.backend.tests.test_p2_resident_uploads import image_pdf, use_own_words
from engine_v2.pipeline.preprocess import PageSource
from engine_v2.tests import fail_case_samples as sample


def text_pdf(path,pages):
    with pymupdf.open() as document:
        font=pymupdf.Font("cjk")
        for index,(_,recognized) in enumerate(pages):
            page=document.new_page(width=595,height=842)
            if index%2:
                notice="합성시험용 가짜 안내 문장입니다. 실제 서류나 실제 인물의 정보가 아닙니다."
                writer=pymupdf.TextWriter(page.rect)
                writer.append((55,60),notice,font=font,fontsize=8)
                writer.write_text(page)
            for word in recognized.words:
                x0,y0,x1,y1=word.bbox_px
                text=word.text.replace("[√]","[X]")
                size=min((y1-y0)*.9,(x1-x0)/font.text_length(text,fontsize=1))
                writer=pymupdf.TextWriter(page.rect)
                writer.append((x0,y1-2),text,font=font,fontsize=size)
                writer.write_text(page)
        document.save(path)
    return path


def shaped(*,two_digit=False,checkbox=True,defect=None,image=False):
    pages=sample.daily()
    for page,result in pages:
        for word in list(result.words):
            if two_digit and word.text=="1990년01월01일":
                word.text="90년01월01일"
            if not checkbox and word.text.startswith("[√]"):
                word.text="산재보험 고용보험"
            if defect=="period" and word.text=="2025년09월~":
                result.words.remove(word)
            if defect=="duplicate" and page.page==2 and word.text=="가짜사업장":
                word.text="다른가짜사업장"
        if image:
            width,height=page.pixel_size
            for word in result.words:
                x0,y0,x1,y1=word.bbox_px
                word.bbox_px=(x0*2480/width,y0*3508/height,x1*2480/width,y1*3508/height)
            page.pixel_size=(2480,3508)
            page.source=PageSource.EMBEDDED
            result.engine="own"
    return pages


def new_daily_app(client,**kwargs):
    aid=new_app(client,name=sample.NAME,birth=kwargs.get("birth",sample.BIRTH.isoformat()))
    response=client.put(f"/api/applications/{aid}/doc-context",json={"work_category":"지역가입자·피부양자"})
    assert response.status_code==200
    return aid


def assert_complete_fields(fields,two_digit=False):
    assert fields["양식판독상태"]=="완전"
    assert fields["성명"]==sample.NAME
    assert fields["발급일"]=="2026-03-03"
    assert fields["발급번호"]=="0000-0000-000000000"
    assert json.loads(fields["조회기간"])==["2025-09","2026-03"]
    record=json.loads(fields["일용근로내역자료"])
    assert record["copies_consistent"] is True
    assert len(record["rows"])==3
    assert record["rows"][0]["work_dates"]==[1,2,3,4,5]
    assert record["rows"][0]["days"]==5
    assert record["rows"][0]["wage"]==500000
    assert record["rows"][0]["remuneration"]==500000
    if two_digit:
        assert "생년월일" not in fields
        assert fields["생년월일표기"]=="90-01-01"
        assert json.loads(fields["생년월일후보"])==["1990-01-01","2090-01-01"]
    else:
        assert fields["생년월일"]==sample.BIRTH.isoformat()


@pytest.mark.parametrize("two_digit",[False,True])
def test_four_page_text_pdf_renaming_and_wrong_expected_preserve_daily_results(client,tmp_path,two_digit):
    path=text_pdf(tmp_path/"FAKE-arbitrary.pdf",shaped(two_digit=two_digit))
    direct=read_document(str(path),DocType.NHIS_PAYMENT)
    alternate=read_document(str(path),DocType.RESIDENT_ABSTRACT)
    assert direct.detected_doc_type==alternate.detected_doc_type==DocType.DAILY_WORK_RECORD
    assert direct.fields==alternate.fields
    assert direct.confidence>=.9
    assert direct.page_count==4
    assert direct.issue_date==date(2026,3,3)
    assert_complete_fields(direct.fields,two_digit)
    aid=new_daily_app(client)
    for filename in ("FAKE-opaque.pdf","FAKE-other-document-name.pdf"):
        response,stored=upload(client,aid,path,"work_proof",filename=filename)
        assert response["detected_doc_type"]==str(DocType.DAILY_WORK_RECORD)
        assert response["status"]=="PASS"
        assert all(finding["severity"]!="FAIL" for finding in response["findings"])
        assert stored["fields"]==direct.fields
        assert stored["engine"]=="pdftext"
        assert_complete_fields(stored["fields"],two_digit)


@pytest.mark.parametrize("two_digit",[False,True])
def test_four_page_image_pdf_uses_mocked_own_words_through_upload(client,tmp_path,monkeypatch,two_digit):
    path=image_pdf(tmp_path/"FAKE-image.pdf",shaped(two_digit=two_digit,image=True))
    use_own_words(monkeypatch,shaped(two_digit=two_digit,image=True))
    direct=read_document(str(path),DocType.BIZ_REG_PROOF)
    assert direct.detected_doc_type==DocType.DAILY_WORK_RECORD
    assert direct.engine=="own"
    assert direct.confidence>=.9
    assert_complete_fields(direct.fields,two_digit)
    use_own_words(monkeypatch,shaped(two_digit=two_digit,image=True))
    response,stored=upload(client,new_daily_app(client),path,"work_proof")
    assert response["status"]=="PASS"
    assert stored["fields"]==direct.fields
    assert stored["engine"]=="own"
    assert_complete_fields(stored["fields"],two_digit)


def test_graphic_checkbox_unknown_is_recorded_without_inventing_insurance_copy(client,tmp_path):
    path=text_pdf(tmp_path/"FAKE-no-text-check.pdf",shaped(checkbox=False))
    direct=read_document(str(path))
    assert direct.detected_doc_type==DocType.DAILY_WORK_RECORD
    assert_complete_fields(direct.fields)
    assert json.loads(direct.fields["보험구분"])==["미확인"]
    assert json.loads(direct.fields["일용근로내역자료"])["insurance_types"]==[]
    assert "체크 표시" in direct.fields["판독경고"]
    response,stored=upload(client,new_daily_app(client),path,"work_proof")
    assert all(finding["severity"]!="FAIL" for finding in response["findings"])
    assert stored["fields"]==direct.fields


@pytest.mark.parametrize("defect",["period","duplicate"])
@pytest.mark.parametrize("image",[False,True])
def test_incomplete_period_or_disagreeing_copies_remain_upload_review(client,tmp_path,monkeypatch,defect,image):
    pages=shaped(defect=defect,image=image)
    path=(image_pdf if image else text_pdf)(tmp_path/"FAKE-incomplete.pdf",pages)
    if image:
        use_own_words(monkeypatch,shaped(defect=defect,image=True))
    response,stored=upload(client,new_daily_app(client),path,"work_proof")
    assert response["detected_doc_type"]==str(DocType.DAILY_WORK_RECORD)
    assert response["status"]=="NEEDS_REVIEW"
    assert all(finding["severity"]!="FAIL" for finding in response["findings"])
    assert stored["confidence"]<=.4
    assert stored["fields"]["양식판독상태"]=="불완전"
    assert stored["fields"]["판독검증실패"]
    if defect=="duplicate":
        assert json.loads(stored["fields"]["일용근로내역자료"])["copies_consistent"] is False


def test_split_title_written_out_of_order_uses_coordinate_daily_fallback(tmp_path,monkeypatch):
    from engine_v2.pipeline.ocr import OcrWord
    monkeypatch.setenv("ENGINE_V2_OCR","off")
    pages=shaped()
    for _,recognized in pages:
        for word in list(recognized.words):
            if word.text.startswith("일용근로·"):
                recognized.words.remove(word)
                # File insertion order is reversed; only coordinates restore the title.
                recognized.words.extend([
                    OcrWord("노무제공내역서(근로자/노무제공자)",1,(214,75,485,96)),
                    OcrWord("일용근로·",1,(112,75,210,96)),
                ])
    path=text_pdf(tmp_path/"FAKE-coordinate-title.pdf",pages)
    direct=read_document(str(path),DocType.NHIS_PAYMENT)
    assert direct.detected_doc_type==DocType.DAILY_WORK_RECORD
    assert direct.confidence>=.9
    assert_complete_fields(direct.fields)


@pytest.mark.parametrize("birth",["1991-01-01","1990-02-01"])
def test_two_digit_birth_not_matching_verified_identity_stays_review(client,tmp_path,birth):
    path=text_pdf(tmp_path/"FAKE-two-digit-other.pdf",shaped(two_digit=True))
    response,stored=upload(client,new_daily_app(client,birth=birth),path,"work_proof")
    assert response["status"]=="NEEDS_REVIEW"
    assert "IDENTITY_UNCERTAIN" in {finding["code"] for finding in response["findings"]}
    assert all(finding["severity"]!="FAIL" for finding in response["findings"])
    assert "생년월일" not in stored["fields"]
    assert json.loads(stored["fields"]["생년월일후보"])==["1990-01-01","2090-01-01"]

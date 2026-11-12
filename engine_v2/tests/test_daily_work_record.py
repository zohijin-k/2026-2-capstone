"""Fictitious text/OCR coordinates prove daily-work structure and uncertainty."""
from dataclasses import replace
from datetime import date
import json

import pytest

from engine_v2.engine import EXTRACTORS
from engine_v2.extractors import daily_work_record as reader
from engine_v2.pipeline.ocr import OcrWord
from engine_v2.pipeline.preprocess import PageSource
from engine_v2.schemas.models import DocType, FieldSource
from engine_v2.tests import fail_case_samples as sample


def data(result):
    return json.loads(result.fields["일용근로내역자료"].value)


def mutate(pages, predicate, value=None, remove=False):
    for page,result in pages:
        for word in list(result.words):
            if predicate(page,word):
                if remove:
                    result.words.remove(word)
                else:
                    word.text=value
    return pages


@pytest.mark.parametrize("source",[PageSource.TEXT_LAYER,PageSource.EMBEDDED])
@pytest.mark.parametrize("scale",[.6,1,1.8])
def test_split_headers_wrapped_days_and_duplicate_copies(source,scale):
    pages=sample.daily()
    for page,result in pages:
        page.source=source
        page.pixel_size=tuple(round(value*scale) for value in page.pixel_size)
        result.engine="text_layer" if source==PageSource.TEXT_LAYER else "own"
        for word in result.words:
            word.bbox_px=tuple(value*scale for value in word.bbox_px)
    result=reader.extract(pages,today=date(2026,3,3))
    assert result.detected_type==DocType.DAILY_WORK_RECORD
    assert result.form_kind=="comwel_daily_work"
    assert result.structure_complete is True
    assert all(validation.passed for validation in result.validations)
    assert result.fields["성명"].value==sample.NAME
    assert result.fields["생년월일"].value==sample.BIRTH
    assert result.fields["발급일"].value==date(2026,3,3)
    assert result.fields["발급번호"].value=="0000-0000-000000000"
    assert json.loads(result.fields["조회기간"].value)==["2025-09","2026-03"]
    assert json.loads(result.fields["보험구분"].value)==["산재","고용"]
    assert len(data(result)["rows"])==3
    assert data(result)["copies_consistent"] is True
    assert data(result)["rows"][0]=={
        "month":"2025-10","workplace":"가짜사업장","work_dates":[1,2,3,4,5],
        "days":5,"wage":500000,"remuneration":500000,"worker_category":"근로자"}
    expected=FieldSource.TEXT_LAYER if source==PageSource.TEXT_LAYER else FieldSource.OCR
    assert result.fields["일용근로내역자료"].source==expected
    assert result.fields["일용근로내역자료"].bbox.page==0
    assert min(field.confidence for field in result.fields.values())>=.9
    assert EXTRACTORS[DocType.DAILY_WORK_RECORD] is reader.extract


def test_single_copy_and_two_digit_birth_do_not_invent_a_century():
    pages=sample.daily(copies=False)
    mutate(pages,lambda p,w:w.text=="1990년01월01일","90년01월01일")
    result=reader.extract(pages)
    assert result.structure_complete is True
    assert "생년월일" not in result.fields
    assert result.fields["생년월일표기"].value=="90-01-01"
    assert json.loads(result.fields["생년월일후보"].value)==["1990-01-01","2090-01-01"]
    assert len(data(result)["rows"])==3


def test_unreadable_graphic_checkbox_preserves_only_observed_monthly_certainty():
    pages=sample.daily()
    mutate(pages,lambda p,w:w.text.startswith("[√]"),"산재보험 고용보험")
    result=reader.extract(pages)
    assert result.structure_complete is True
    assert json.loads(result.fields["보험구분"].value)==["미확인"]
    assert data(result)["insurance_types"]==[]
    assert data(result)["copies_consistent"] is True
    assert result.warnings and "체크 표시" in result.warnings[0]


@pytest.mark.parametrize("defect",[
    "header","period","day-count","day-duplicate","day-invalid","money",
    "ordinal","confirmation","footer-date","identity","period-conflict",
    "duplicate-workplace","duplicate-amount","duplicate-day","duplicate-identity",
    "same-checkbox","unassigned-page","column-crossing","low-confidence",
])
def test_incomplete_or_conflicting_printed_evidence_stays_low_confidence(defect):
    pages=sample.daily()
    if defect=="header":
        mutate(pages,lambda p,w:w.text=="임금총액",remove=True)
    elif defect=="period":
        mutate(pages,lambda p,w:w.text=="2025년09월~",remove=True)
    elif defect=="day-count":
        mutate(pages,lambda p,w:w.bbox_px[0]==323 and w.text=="5","4")
    elif defect=="day-duplicate":
        mutate(pages,lambda p,w:w.text=="4,5","3,5")
    elif defect=="day-invalid":
        mutate(pages,lambda p,w:w.text=="4,5","0,32")
    elif defect=="money":
        mutate(pages,lambda p,w:w.bbox_px[0]==358 and w.text=="500,000","5O0,000")
    elif defect=="ordinal":
        mutate(pages,lambda p,w:w.bbox_px[0]==55 and w.text=="2","4")
    elif defect=="confirmation":
        mutate(pages,lambda p,w:w.text=="근로복지공단이사장",remove=True)
    elif defect=="footer-date":
        mutate(pages,lambda p,w:p.page==1 and w.text=="2026년03월03일","2026년03월04일")
    elif defect=="identity":
        mutate(pages,lambda p,w:w.text==sample.NAME,remove=True)
    elif defect=="period-conflict":
        pages[0][1].words.append(OcrWord("2025년08월~2026년03월",1,(264,180,440,192)))
    elif defect=="duplicate-workplace":
        mutate(pages,lambda p,w:p.page==2 and w.text=="가짜사업장","다른가짜사업장")
    elif defect=="duplicate-amount":
        mutate(pages,lambda p,w:p.page==2 and w.bbox_px[0]==358 and w.text=="500,000","600,000")
    elif defect=="duplicate-day":
        mutate(pages,lambda p,w:p.page==2 and w.text=="4,5","4,6")
    elif defect=="duplicate-identity":
        mutate(pages,lambda p,w:p.page==2 and w.text==sample.NAME,"가짜다름")
    elif defect=="same-checkbox":
        mutate(pages,lambda p,w:w.text=="[√]고용보험","[√]산재보험")
    elif defect=="unassigned-page":
        page,result=sample.tiny_unknown()[0]
        pages.append((replace(page,page=4),result))
    elif defect=="column-crossing":
        word=next(w for w in pages[0][1].words if w.text=="가짜사업장")
        word.bbox_px=(128,246,300,258)
    else:
        word=next(w for w in pages[0][1].words if w.text=="2025년09월~")
        word.confidence=.4
    result=reader.extract(pages)
    assert result.structure_complete is False
    assert any(not validation.passed for validation in result.validations)
    assert result.warnings
    assert all(field.confidence<=.4 for field in result.fields.values())


def test_arbitrary_table_keywords_and_notice_do_not_establish_a_daily_form():
    pages=sample.daily(copies=False)[1:]
    page,result=pages[0]
    result.words.append(OcrWord("※ 일용근로 내역서에 관한 가짜 안내",1,(55,58,445,70)))
    assert reader.recognizes(pages) is False
    result=reader.extract(pages)
    assert result.detected_type==DocType.UNKNOWN
    assert result.structure_complete is False


def test_multiple_rows_in_same_month_are_preserved_before_copy_deduplication():
    pages=sample.daily(months=("2025-10","2025-10","2025-12"))
    mutate(pages,lambda p,w:w.bbox_px[1]==275 and w.text=="가짜사업장","다른가짜사업장")
    result=reader.extract(pages)
    assert result.structure_complete is True
    assert [row["month"] for row in data(result)["rows"]]==["2025-10","2025-10","2025-12"]
    assert data(result)["rows"][1]["workplace"]=="다른가짜사업장"


def test_real_text_layer_pages_use_the_same_reader_without_ocr(tmp_path):
    import pymupdf
    from engine_v2.engine import _load_pages
    from engine_v2.schemas.models import DocumentInput

    path=tmp_path/"FAKE-arbitrary.pdf"
    pages=sample.daily()
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
    loaded=_load_pages(DocumentInput(doc_id="FAKE",declared_type=DocType.RESIDENT_ABSTRACT,file_path=str(path)),"off")
    assert isinstance(loaded,list)
    assert all(page.source==PageSource.TEXT_LAYER for page,_ in loaded)
    result=reader.extract(loaded)
    assert result.structure_complete is True, [v.name for v in result.validations if not v.passed]
    assert data(result)["copies_consistent"] is True
    assert len(data(result)["rows"])==3


@pytest.mark.parametrize("kind",["identity-matching","identity-conflicting","issue-matching","issue-conflicting"])
def test_unexpected_continuation_metadata_cannot_be_silently_ignored(kind):
    pages=sample.daily()
    if kind.startswith("identity"):
        name="가짜다름" if kind.endswith("conflicting") else sample.NAME
        birth="1991년01월01일" if kind.endswith("conflicting") else "1990년01월01일"
        words=[OcrWord("성명",1,(122,134,143,146)),OcrWord(name,1,(224,134,270,146)),
               OcrWord("생년월일",1,(331,134,380,146)),OcrWord(birth,1,(432,134,520,146))]
    else:
        number="0000-0000-000000001" if kind.endswith("conflicting") else "0000-0000-000000000"
        words=[OcrWord("발급번호",1,(55,105,93,117)),OcrWord(number,1,(111,105,222,117)),
               OcrWord("발급일자",1,(234,105,280,117)),OcrWord("2026년03월03일",1,(292,105,380,117))]
    pages[1][1].words.extend(words)
    result=reader.extract(pages)
    assert result.structure_complete is False
    assert not next(v.passed for v in result.validations if v.name=="daily_0_continuation")
    assert all(field.confidence<=.4 for field in result.fields.values())

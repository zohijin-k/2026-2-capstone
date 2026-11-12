"""One-page form certainty survives unrelated attachments; same-family pages remain strict."""
import json
from dataclasses import replace
import pytest
from engine_v2.extractors import insurance_4
from engine_v2.extractors.attached_pages import extract_form
from engine_v2.tests.fail_case_samples import mixed_portal


def test_single_page_portal_excludes_sparse_attachments_from_validation():
    pages=mixed_portal()
    result,scoped=extract_form(insurance_4.extract,pages)
    assert result.structure_complete is True
    assert len(scoped)==1
    assert json.loads(result.fields["추가첨부쪽"].value)==[2,3]
    assert all(v.passed for v in result.validations)


@pytest.mark.parametrize("defect",["duplicate","marker","identity","table","continuation"])
def test_own_structure_and_same_family_pages_never_relaxed(defect):
    pages=mixed_portal()
    if defect=="duplicate":
        p,r=pages[0]
        pages.append((replace(p,page=3),r))
    elif defect=="marker":
        next(w for w in pages[0][1].words if w.text=="1 / 1").text="1 / 2"
    elif defect in {"identity","table"}:
        target="가짜이름" if defect=="identity" else "사업장명칭"
        pages[0][1].words[:]=[w for w in pages[0][1].words if w.text!=target]
    else:
        from engine_v2.tests.fail_case_samples import shaped_page
        pages[1]=shaped_page([(100,100,250,120,"가입자종별",1),(400,100,550,120,"자격취득일",1)],index=1)
    result,_=extract_form(insurance_4.extract,pages)
    assert result.structure_complete is False

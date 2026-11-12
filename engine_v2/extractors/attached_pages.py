"""Bound a proven one-page form without weakening its own structural validation."""
import json
import re
from . import nhis_common as common
from ..pipeline.layout import line_text, squash
from ..schemas.models import ExtractedField, FieldSource


def _family(page, result):
    text = squash("".join(line_text(row) for row in common.page_lines(page,result) if row[0].cy < 45))
    if "4대사회보험" in text and "가입내역확인서" in text and "확인용" in text:
        return "insurance_portal"
    if "건강보험자격득실확인서" in text and "확인청구자" in text:
        return "acquisition"
    if "건강보험자격확인(통보)서" in text or "건강보험자격확인통보서" in text:
        return "qualification"
    if "납부확인서" in text and "가입자성명" in text:
        return "payment"
    return None


def _single_marker(page,result):
    markers=[]
    for row in common.page_lines(page,result):
        selected=[w for w in row if (w.x0>75 and w.cy<40) or (w.x1<25 and w.cy<8)]
        text=squash("".join(w.text for w in selected))
        if re.fullmatch(r"[0-9]{1,2}[/／][0-9]{1,2}",text):
            markers.append((text,min(w.conf for w in selected)))
    return len(markers)==1 and markers[0][0].replace("／","/")=="1/1" and markers[0][1]>=.85


def partition(pages):
    if len(pages)<2:
        return pages,[]
    families=[_family(p,r) for p,r in pages]
    candidates=[i for i,(p,r) in enumerate(pages) if families[i] and _single_marker(p,r)]
    if len(candidates)!=1:
        return pages,[]
    index=candidates[0]
    family=families[index]
    if families.count(family)!=1:
        return pages,[]
    for i,(p,r) in enumerate(pages):
        if i==index or families[i]:
            continue
        text=squash("".join(line_text(row) for row in common.page_lines(p,r)))
        same_table=(family=="insurance_portal" and "가입자종별" in text and "자격취득일" in text or
                    family=="acquisition" and "자격취득일" in text and "자격상실일" in text or
                    family=="payment" and "고지금액" in text and "납부금액" in text or
                    family=="qualification" and "급여정지" in text and "자격취득일" in text)
        if same_table:
            return pages,[]
    return [pages[index]],[p.page+1 for i,(p,_) in enumerate(pages) if i!=index]


def extract_form(extractor,pages,today=None):
    scoped,additional=partition(pages)
    result=extractor(scoped,today=today)
    if additional:
        result.fields["추가첨부쪽"] = ExtractedField(value=json.dumps(additional),
            raw_text="추가 첨부 쪽",confidence=1,source=FieldSource.TEXT_LAYER)
    return result,scoped

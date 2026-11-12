"""Coordinate reader for COMWEL daily-work / labor-provision records.

A copy can span a table page and a dated confirmation page. Printed monthly
rows, rather than the first/last employment date, are authoritative evidence.
"""
from __future__ import annotations

import calendar
import json
import re
from dataclasses import dataclass, field, replace
from datetime import date
from statistics import median

from . import nhis_common as common, nhis_forms as forms
from .format_text import normalize_format_text
from .resident_abstract import kst_today
from ..pipeline.layout import group_lines, line_text, squash
from ..schemas.models import DocType, ExtractedField

FORM_KIND = "comwel_daily_work"
HEADERS = (("번호",), ("근로년월", "근로연월"), ("사업장명", "사업장명칭"),
           ("근로일자",), ("근로일수",), ("임금총액",), ("보수총액",), ("근로자구분",))
MONTH = re.compile(r"(20\d{2})[./년-](0?[1-9]|1[0-2])월?\.?")
PERIOD = re.compile(r"(20\d{2})[./년-](0?[1-9]|1[0-2])월?[~～∼](20\d{2})[./년-](0?[1-9]|1[0-2])월?\.?")
ISSUE_NUMBER = re.compile(r"\d{4}-\d{4}-\d{9}")
MONEY = re.compile(r"(?:0|[1-9]\d*|[1-9]\d{0,2}(?:,\d{3})+)원?")
CHECK = r"(?:\[\s*[√✓✔xXvV]\s*\]|[☑√✓✔■])"
SELECTION = re.compile(r"\(조회기간총([0-9]+)개이력중([0-9]+)개이력선택발급요청\)")


@dataclass
class DailyWorkResult:
    detected_type: DocType
    type_confidence: float
    fields: dict[str, ExtractedField]
    validations: list[common.Validation]
    warnings: list[str] = field(default_factory=list)
    form_kind: str = FORM_KIND
    structure_complete: bool = False


def _text(words):
    return " ".join(line_text(row) for row in group_lines(words)).strip()


def _compact(words):
    return squash(normalize_format_text(_text(words)))


def _unique(lines, aliases, *, exact=False):
    hits = forms.label_hits(lines, aliases)
    # This form deliberately stacks 근로/년월, 근로/일자 and 근로자/구분.
    # The common matcher preserves those separate source tokens.
    for alias,words in common.label_hits(lines,aliases):
        height=max((word.y1-word.y0 for word in words),default=0)
        if words and max(word.y1 for word in words)-min(word.y0 for word in words)<=3*height:
            hits.append((alias,words))
    unique = {}
    for _, words in hits:
        if exact and _compact(words).strip(":：") not in aliases:
            continue
        unique[tuple(id(word) for word in words)] = words
    selected = []
    for words in sorted(unique.values(), key=len, reverse=True):
        if not any(all(any(word is other for other in old) for word in words) for old in selected):
            selected.append(words)
    return selected[0] if len(selected) == 1 else []


def _title(lines):
    heights = [word.y1-word.y0 for row in lines for word in row if re.search("[가-힣]",word.text)]
    ordinary = median(heights) if heights else 0
    for row in lines:
        if min(word.cy for word in row) > 18:
            continue
        text = squash(line_text(row))
        if ("내역서" in text and ("일용근로" in text or "노무제공" in text)
                and min(word.x0 for word in row)>=15
                and max(word.y1-word.y0 for word in row)>=1.2*ordinary):
            return row
    return []


def recognizes(pages) -> bool:
    """Only body titles select the family; filename and expected type are absent."""
    return any(_title(common.page_lines(page, result)) for page, result in pages)


def _labeled_cells(lines, labels):
    anchors = [_unique(lines, aliases) for aliases in labels]
    if any(not words for words in anchors):
        return None
    centers = [sum(word.cy for word in words) / len(words) for words in anchors]
    height = max(word.y1 - word.y0 for words in anchors for word in words)
    if max(centers) - min(centers) > 1.5 * height:
        return None
    if any(max(word.x1 for word in a) >= min(word.x0 for word in b)
           for a, b in zip(anchors, anchors[1:])):
        return None
    top, bottom = min(centers) - height, max(centers) + height
    label_ids = {id(word) for words in anchors for word in words}
    cells = []
    for i, words in enumerate(anchors):
        left = max(word.x1 for word in words)
        right = min(word.x0 for word in anchors[i + 1]) if i + 1 < len(anchors) else 100
        candidates = [word for row in lines for word in row if top <= word.cy <= bottom and
                      id(word) not in label_ids and left <= word.x0 and word.x1 <= right]
        crossing = any(word.x0 < right < word.x1 or word.x0 < left < word.x1
                       for row in lines for word in row if top <= word.cy <= bottom and id(word) not in label_ids)
        cells.append([] if crossing else candidates)
    return cells


def _date(words):
    text = _compact(words).removesuffix(".")
    return common.parse_date(text) if common.DATE_RE.fullmatch(text) else None


def _birth(words):
    text = _compact(words).removesuffix(".")
    full = _date(words)
    if full is not None:
        return full, full.isoformat(), [full.isoformat()]
    match = re.fullmatch(r"(\d{2})[./년-](\d{1,2})[./월-](\d{1,2})일?", text)
    if not match:
        return None, None, []
    yy, mm, dd = (int(part) for part in match.groups())
    candidates = []
    for century in (1900, 2000):
        try:
            candidates.append(date(century + yy, mm, dd).isoformat())
        except ValueError:
            pass
    return None, f"{yy:02}-{mm:02}-{dd:02}" if candidates else None, candidates


def _query_words(lines, headers):
    # The query label is in the left metadata cell. A split note token can
    # contain exactly the same word, but is outside this observed label cell.
    left_cell = [[word for word in row if word.x1 < 20] for row in lines]
    label = _unique(left_cell, ("조회기간", "조회대상기간"), exact=True)
    if not label or not headers:
        return []
    cy = sum(word.cy for word in label) / len(label)
    height = max(word.y1 - word.y0 for word in label)
    top = cy - 1.75 * height
    bottom = min(word.y0 for words in headers for word in words)
    # The range may sit one line above its left-side label.
    return [word for row in lines for word in row if top <= word.cy < bottom and word.x0 > max(w.x1 for w in label)]


def _selection_note(row):
    text = _compact(row)
    # Damaged punctuation/label text must not turn an observed selection note
    # into legacy absence and accidentally establish complete work history.
    return "이력" in text and ("조회기간" in text or "선택" in text)


def _query_period(lines, headers):
    words = _query_words(lines, headers)
    matches = []
    for row in group_lines(words):
        if _selection_note(row):
            continue  # The bounded selection note is assessed independently.
        text = _compact(row)
        match = PERIOD.fullmatch(text)
        if match:
            start, end = f"{match[1]}-{int(match[2]):02}", f"{match[3]}-{int(match[4]):02}"
            if start <= end:
                matches.append(((start, end), row))
        elif re.search(r"\d{4}|[~～∼]", text):
            return None, words
    return (matches[0][0], matches[0][1]) if len(matches) == 1 else (None, words)


def _selection(lines, headers):
    notes = [row for row in group_lines(_query_words(lines, headers)) if _selection_note(row)]
    if not notes:
        return {"status": "ABSENT"}
    if len(notes) != 1:
        return {"status": "UNREADABLE"}
    match = SELECTION.fullmatch(_compact(notes[0]))
    confidence = min(w.conf for w in notes[0])
    if not match or confidence < .85:
        return {"status": "UNREADABLE"}
    total, selected = map(int, match.groups())
    if selected > total:
        return {"status": "UNREADABLE"}
    return {"status": "READABLE", "total": total, "selected": selected,
            "confidence": confidence}


def _selection_summary(copies):
    if copies and all(copy.get("status") == "ABSENT" for copy in copies):
        return "ABSENT"
    if not copies or any(copy.get("status") != "READABLE" for copy in copies):
        return "UNREADABLE"
    for copy in copies:
        total, selected, confidence = copy.get("total"), copy.get("selected"), copy.get("confidence")
        if (type(total) is not int or type(selected) is not int or not 0 <= selected <= total
                or type(confidence) not in {int, float} or not .85 <= confidence <= 1):
            return "UNREADABLE"
    counts = {(copy["total"], copy["selected"]) for copy in copies}
    if len(counts) != 1:
        return "CONFLICT"
    total, selected = next(iter(counts))
    return "PARTIAL" if selected < total else "COMPLETE"


def selection_status(fields):
    """Recheck saved count provenance; never trust a categorical status alone."""
    if "일용근로선택자료" not in fields:
        return "ABSENT"  # Existing supported forms may have no selection note.
    try:
        data = json.loads(fields["일용근로선택자료"])
        copies = data["copies"]
        if type(data.get("version")) is not int or data["version"] != 1 or not isinstance(copies, list) or any(not isinstance(c, dict) for c in copies):
            return "UNREADABLE"
        if data.get("copies_consistent") is not True:
            return "CONFLICT"
        return _selection_summary(copies)
    except (ValueError, TypeError, KeyError):
        return "UNREADABLE"


def _insurance(lines):
    upper = [word for row in lines for word in row if word.cy < 12]
    found = []
    for row in group_lines(upper):
        text = squash(line_text(row))
        found.extend(re.findall(CHECK + r"(산재|고용)보험", text))
        found.extend(re.findall(r"(산재|고용)보험" + CHECK, text))
    return found[0] if len(found) == 1 else None


def _headers(lines):
    numbers = forms.label_hits(lines, ("번호",))
    candidates = []
    for _, words in numbers:
        if not 18 <= min(word.cy for word in words) <= 40:
            continue
        height = max(word.y1 - word.y0 for word in words)
        cy = sum(word.cy for word in words) / len(words)
        region = [row for row in lines if abs(row[0].cy - cy) <= 3 * height]
        headers = [_unique(region, aliases) for aliases in HEADERS]
        if all(headers):
            candidates.append(headers)
    return candidates[0] if len(candidates) == 1 else None


def _money(words):
    text = _compact(words)
    if not MONEY.fullmatch(text):
        return None
    return int(text.removesuffix("원").replace(",", ""))


def _days(words, month):
    text = _compact(words)
    if not re.fullmatch(r"\d{1,2}(?:,\d{1,2})*", text):
        return None
    values = [int(part) for part in text.split(",")]
    year, month_number = (int(part) for part in month.split("-"))
    last = calendar.monthrange(year, month_number)[1]
    return sorted(values) if len(values) == len(set(values)) and all(1 <= value <= last for value in values) else None


def _table(page, result, lines, headers):
    if not headers:
        return [], [], False
    top = max(word.y1 for words in headers for word in words)
    endings = [min(word.cy for word in row) for row in lines if min(word.cy for word in row)>top and
               any(label in squash(line_text(row)) for label in ("이하여백","확인합니다","근로복지공단"))]
    bottom = min(endings, default=95)
    body = [row for row in lines if top < row[0].cy < bottom]
    # A printed amount/count and its separate currency/day unit occupy one
    # cell. Reserve their observed interval during corridor discovery only;
    # keep every original token for parsing, confidence and field bounds.
    corridor_rows = []
    for row in body:
        reserved = []
        for word in row:
            previous = reserved[-1] if reserved else None
            numeric = previous and re.fullmatch(r"[0-9,]+",_compact([previous]))
            glyph = ((previous.x1-previous.x0)/max(len(squash(previous.text)),1)) if previous else 0
            if (numeric and word.text in {"원","일"} and 0<=word.x0-previous.x1<=3*glyph
                    and abs(word.cy-previous.cy)<=max(word.y1-word.y0,previous.y1-previous.y0)):
                reserved[-1] = replace(previous,text=previous.text+word.text,x1=word.x1,
                                       y0=min(previous.y0,word.y0),y1=max(previous.y1,word.y1))
            else:
                reserved.append(word)
        corridor_rows.append(reserved)
    columns = forms.table_columns(headers, corridor_rows)
    if columns is None:
        return [], [word for row in body for word in row], False
    flat = [word for row in body for word in row]
    month_candidates = [word for word in flat if columns[1] <= word.x0 and word.x1 <= columns[2]]
    anchors = []
    for row in group_lines(month_candidates):
        text = _compact(row)
        match = MONTH.fullmatch(text)
        if not match:
            return [], flat, False
        anchors.append((sum(word.cy for word in row) / len(row), f"{match[1]}-{int(match[2]):02}", row))
    if not anchors:
        return [], flat, False
    anchors.sort()
    bounds = [top, *[(a[0]+b[0])/2 for a,b in zip(anchors,anchors[1:])], bottom]
    rows = []
    valid = True
    for index, ((_, month, _), a, b) in enumerate(zip(anchors,bounds,bounds[1:])):
        words = [word for word in flat if a < word.cy < b]
        cells = forms.column_cells(words, columns)
        if cells is None:
            valid = False
            continue
        ordinal, _, workplace, day_words, count_words, wage_words, pay_words, category = cells
        number = _compact(ordinal)
        workplace_text, category_text = _text(workplace), _compact(category)
        day_values = _days(day_words,month)
        count_text = _compact(count_words).removesuffix("일")
        count = int(count_text) if re.fullmatch(r"[1-9]\d?",count_text) else None
        wage, remuneration = _money(wage_words), _money(pay_words)
        row_ok = (number == str(index+1) and bool(workplace_text) and not common.is_header_only_value(workplace_text)
                  and bool(re.search(r"[가-힣A-Za-z]",workplace_text)) and day_values is not None and count == len(day_values)
                  and wage is not None and remuneration is not None
                  and category_text in {"근로자","일용근로자","노무제공자","특수형태근로종사자"}
                  and all(word.conf >= .85 for word in words))
        valid &= row_ok
        rows.append({"month":month,"workplace":workplace_text,"work_dates":day_values or [],
                     "days":count,"wage":wage,"remuneration":remuneration,"worker_category":category_text})
    return rows, flat, bool(valid and len(rows)==len(anchors))


def _issuer(lines):
    aliases = ("근로복지공단이사장", "근로복지공단")
    standalone = [row for row in lines if _compact(row) in aliases]
    return _unique(standalone, aliases, exact=True)


def _confirmation(copy):
    found = []
    for page,result in copy:
        lines = common.page_lines(page,result)
        issuer = _issuer(lines)
        if not issuer:
            continue
        issuer_y = min(word.y0 for word in issuer)
        confirmations = [row for row in lines if row[0].cy < issuer_y and
                         re.fullmatch(r"위와같이(?:내역을확인합니다|확인합니다|자격내역을알려드립니다)\.?", _compact(row))]
        if len(confirmations) != 1:
            return None, [], False
        top = max(word.y1 for word in confirmations[0])
        words = [word for row in lines for word in row if top < word.cy < issuer_y]
        # Notice prose is above the confirmation, not part of this date cell.
        value = _date(words)
        if value is None or any(word.conf < .85 for word in words + issuer + confirmations[0]):
            return None, words, False
        found.append((value,words))
    return (*found[0],True) if len(found)==1 else (None,[],False)


def extract(pages, today=None) -> DailyWorkResult:
    today = today or kst_today()
    page_map = {page.page:page for page,_ in pages}
    sources = common.sources_by_page(pages)
    checks = []
    warnings = []
    fields = {}
    lines_by_page = [common.page_lines(page,result) for page,result in pages]
    starts = [index for index,lines in enumerate(lines_by_page) if _title(lines)]
    detected = DocType.DAILY_WORK_RECORD if starts else DocType.UNKNOWN
    checks.append(common.Validation("daily_document_type",bool(starts)))
    checks.append(common.Validation("daily_copy_pages_assigned",bool(starts) and starts[0]==0))
    records = []
    all_row_words = []
    for number,start in enumerate(starts):
        end = starts[number+1] if number+1<len(starts) else len(pages)
        copy = pages[start:end]
        page,result = pages[start]
        lines = lines_by_page[start]
        headers = _headers(lines)
        checks.append(common.Validation(f"daily_{number}_table_headers",headers is not None))
        label_words = [word for words in headers or [] for word in words]+_title(lines)
        label_words += [word for alias in ("발급번호","발급일자","발급일","성명","생년월일","조회기간")
                        for word in _unique(lines,(alias,))]
        checks.append(common.Validation(f"daily_{number}_label_confidence",bool(label_words) and all(word.conf>=.85 for word in label_words)))
        metadata = _labeled_cells(lines,(("발급번호",),("발급일자", "발급일"),("접수번호",)))
        # Some issued copies omit a receipt cell; the issue/date labels still
        # delimit each other, and the last date cell must full-match a date.
        if metadata is None:
            metadata = _labeled_cells(lines,(("발급번호",),("발급일자", "발급일")))
        issue_number = _compact(metadata[0]) if metadata else ""
        issue = _date(metadata[1]) if metadata else None
        issue_ok = bool(ISSUE_NUMBER.fullmatch(issue_number) and issue is not None and issue<=today)
        checks.append(common.Validation(f"daily_{number}_issue_metadata",issue_ok))
        identity = _labeled_cells(lines,(("성명",),("생년월일",)))
        name = _compact(identity[0]) if identity else ""
        birth,printed,candidates = _birth(identity[1]) if identity else (None,None,[])
        identity_ok = bool(common.NAME_RE.fullmatch(name) and not common.is_header_only_value(name) and candidates)
        checks.append(common.Validation(f"daily_{number}_applicant_identity",identity_ok))
        period,period_words = _query_period(lines,headers)
        checks.append(common.Validation(f"daily_{number}_query_period",period is not None))
        rows,row_words,table_ok = _table(page,result,lines,headers)
        selection_record = _selection(lines, headers)
        if table_ok and selection_record.get("status") == "READABLE" and selection_record["selected"] != len(rows):
            selection_record = {"status": "UNREADABLE"}
        checks.append(common.Validation(f"daily_{number}_table_rows",table_ok))
        if period is not None:
            checks.append(common.Validation(f"daily_{number}_rows_in_period",all(period[0]<=row["month"]<=period[1] for row in rows)))
        confirmation,confirmation_words,confirmation_ok = _confirmation(copy)
        checks.append(common.Validation(f"daily_{number}_confirmation",confirmation_ok and confirmation==issue))
        # A continuation page cannot conceal an independent table or identity.
        continuation_ok = len(copy)<=2 and all(
            _headers(lines_by_page[i]) is None and not _title(lines_by_page[i])
            and bool(_issuer(lines_by_page[i]))
            and _confirmation([pages[i]])[2] and _confirmation([pages[i]])[0] == issue
            # Supported continuation pages contain notices and confirmation,
            # not an independently labeled applicant/issue grid. Even matching
            # extra metadata needs review until its page relationship is known.
            and _labeled_cells(lines_by_page[i],(("성명",),("생년월일",))) is None
            and _labeled_cells(lines_by_page[i],(("발급번호",),("발급일자","발급일"))) is None
            for i in range(start+1,end))
        checks.append(common.Validation(f"daily_{number}_continuation",continuation_ok))
        required_words = [word for cells in (metadata or [],identity or []) for cell in cells for word in cell]
        required_words += period_words+confirmation_words
        checks.append(common.Validation(f"daily_{number}_cell_confidence",bool(required_words) and all(word.conf>=.85 for word in required_words)))
        insurance = _insurance(lines)
        if insurance is None:
            warnings.append("산재·고용보험 체크 표시를 문자로 확인하지 못했습니다. 근로 내역 판정에는 사용하지 않는 참고 정보입니다.")
        records.append({"issue_number":issue_number,"issue":issue,"name":name,"birth":birth,
                        "birth_printed":printed,"birth_candidates":candidates,"period":period,"rows":rows,
                        "insurance":insurance,"metadata":metadata,"identity":identity,"period_words":period_words,
                        "selection":selection_record})
        all_row_words+=row_words
    comparable = [(r["issue"],r["name"],r["birth_printed"],r["period"],r["rows"]) for r in records]
    consistent = bool(records) and all(record==comparable[0] for record in comparable)
    checks.append(common.Validation("daily_insurance_copies_consistent",consistent))
    known_insurance = [record["insurance"] for record in records if record["insurance"]]
    if len(known_insurance) != len(set(known_insurance)):
        warnings.append("보험 체크 표시가 중복되어 보입니다. 근로 내역 판정에는 사용하지 않는 참고 정보입니다.")
    selections = [record["selection"] for record in records]
    selection = _selection_summary(selections)
    checks.append(common.Validation("daily_selection_copies_consistent", selection != "CONFLICT"))
    if selection in {"UNREADABLE", "CONFLICT"}:
        warnings.append("전체 이력 선택 여부를 확실히 읽지 못해 근로 내역의 완전성을 확인해야 합니다.")
    complete = bool(checks) and all(check.passed for check in checks)
    confidence = .97 if complete else .4

    def put(key,value,words=None):
        raw = json.dumps(value,ensure_ascii=False,separators=(",",":")) if isinstance(value,(dict,list,tuple)) else str(value)
        fields[key]=common.make_field(value if isinstance(value,date) else raw,raw,words or [],page_map,confidence,sources)

    if records:
        first=records[0]
        metadata,identity = first["metadata"],first["identity"]
        if first["issue_number"]:
            put("발급번호",first["issue_number"],metadata[0] if metadata else [])
        if first["issue"]:
            put("발급일",first["issue"],metadata[1] if metadata else [])
        if first["name"]:
            put("성명",first["name"],identity[0] if identity else [])
        if first["birth"]:
            put("생년월일",first["birth"],identity[1] if identity else [])
        if first["birth_printed"]:
            put("생년월일표기",first["birth_printed"],identity[1] if identity else [])
            put("생년월일후보",first["birth_candidates"],identity[1] if identity else [])
        if first["period"]:
            put("조회기간",first["period"],first["period_words"])
        put("보험구분",known_insurance or ["미확인"])
        put("발급번호목록",[record["issue_number"] for record in records])
        put("일용근로선택자료", {"version": 1, "status": selection, "copies": selections,
                               "copies_consistent": consistent})
        put("일용근로내역자료",{"period":first["period"],"rows":first["rows"],
                           "insurance_types":known_insurance,"copies_consistent":consistent},all_row_words)
    if not complete:
        warnings.append("일용근로·노무제공내역서의 표·조회기간·신청인 또는 중복본을 완전히 확인하지 못했습니다.")
    return DailyWorkResult(detected,.97 if starts else .1,fields,checks,list(dict.fromkeys(warnings)),structure_complete=complete)

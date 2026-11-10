"""주민등록표 초본 추출기 (레퍼런스 구현).

실측 레이아웃 (2026-11-10, 정부24 초본 브라우저 인쇄본, Apple Vision OCR) — 좌표는 페이지 대비 %
  y≈3      문서확인번호 ####-####-####-#####  /  우측 x≈79 쪽번호 "n/N"
  y≈7~10   제목 "주민등록표 ( 초 본 )"  ← 글자가 띄어져 읽힘 → 공백 제거 후 판별
  y≈12.8   발급일 "YYYY년 MM월 DD일" (x≈58)       ← 매 쪽 반복
  y≈14.5   발급기관 "○○○○ ○○시장"
  y≈17.7   성명(x≈23) / 주민등록번호(x≈68)        ← 매 쪽 반복
  표 머리  "번호 | 주소 | 발생일/신고일 | 세대주 및 관계"
  표 본문  한 건이 2줄:  주소(x≈13) 발생일(x≈54) 신고일(x≈68) 세대주·관계(x≈79)
                         순번(x≈9)  주소 상세(x≈13)  변동사유(x≈62~73)
           순번은 윗줄/아랫줄 어디에도 올 수 있음 → 줄이 아니라 '신고일 칸'으로 건을 나눈다
           "[...]" 메모 줄 = 도로명주소 전환, 행정구역 변경 안내 → 다음 건에 붙임
  끝       "== 이하 여백 ==" 또는 병역사항, 또는 y≈78 이후 안내문

개인정보 최소화
  - 주민등록번호 원문은 결과에 남기지 않는다. 생년월일과 성별 자리만 쓴다.
  - 병역사항, 담당자 연락처는 읽지 않는다. 첫 쪽의 신청인 성명·생년월일은 본인 대조용으로 읽는다.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from zoneinfo import ZoneInfo

from ..pipeline.layout import Word, group_lines, line_text, normalize, squash
from ..pipeline.ocr import OcrResult
from ..pipeline.preprocess import PageImage
from ..schemas.models import BBox, DocType, ExtractedField, FieldSource

# --- 패턴 ---------------------------------------------------------------
ISO_DATE = re.compile(r"(\d{4})\s*[-.]\s*(\d{1,2})\s*[-.]\s*(\d{1,2})")
KOR_DATE = re.compile(r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일")
APPLICANT_DATE = re.compile(
    r"(\d{4}\s*[-./]\s*\d{1,2}\s*[-./]\s*\d{1,2}|"
    r"\d{4}\s*년\s*\d{1,2}\s*월\s*\d{1,2}\s*일|\d{8})"
)
RRN = re.compile(r"(\d{6})\s*-\s*([0-9])")
DOC_NO = re.compile(r"\d{4}-\d{4}-\d{4}-\d{4,5}")
PAGE_NO = re.compile(r"^\s*(\d{1,2})\s*/\s*(\d{1,2})\s*$")
ISSUER = re.compile(r"(시장|군수|구청장)")

# --- 영역 (페이지 대비 %) — 실측값. 양식이 바뀌면 여기만 고친다 ------------
HEADER_MAX_Y = 16.0
COL_NO_MAX_X = 11.5
COL_ADDR_MAX_X = 50.0
COL_OCCUR_X = (50.0, 61.0)
COL_REPORT_X = (61.0, 73.0)
COL_REASON_X = (58.0, 77.5)
COL_HOLDER_MIN_X = 77.5
FOOTER_Y = 77.5

SIDO = {
    "전북특별자치도": "전북", "전라북도": "전북",
    "서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구", "인천광역시": "인천",
    "광주광역시": "광주", "대전광역시": "대전", "울산광역시": "울산", "세종특별자치시": "세종",
    "경기도": "경기", "강원특별자치도": "강원", "강원도": "강원",
    "충청북도": "충북", "충청남도": "충남", "전라남도": "전남",
    "경상북도": "경북", "경상남도": "경남", "제주특별자치도": "제주", "제주도": "제주",
}


KST = ZoneInfo("Asia/Seoul")


def kst_today() -> date:
    """판정 기준일은 항상 한국 시간. 서버가 UTC면 오전 9시 전 당일 발급 서류가 '미래'로 잘못 판정된다."""
    return datetime.now(KST).date()


# --- 결과 구조 ------------------------------------------------------------
@dataclass
class HistoryEntry:
    no: int | None = None
    address: list[str] = field(default_factory=list)
    occurred: date | None = None      # 발생일
    reported: date | None = None      # 신고일
    reason: list[str] = field(default_factory=list)
    holder: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    page: int = 0
    words: list[Word] = field(default_factory=list)

    @property
    def address_text(self) -> str:
        return " ".join(self.address)

    @property
    def effective(self) -> date | None:
        return self.occurred or self.reported

    @property
    def sido(self) -> str | None:
        s = squash(self.address_text)
        for name, short in SIDO.items():
            if s.startswith(name):
                return short
        return None


@dataclass
class Validation:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class ResidentAbstractResult:
    detected_type: DocType
    type_confidence: float
    fields: dict[str, ExtractedField]
    history: list[HistoryEntry]
    validations: list[Validation]
    warnings: list[str] = field(default_factory=list)


# --- 유틸 ---------------------------------------------------------------
def _to_date(m: re.Match | None) -> date | None:
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _bbox(words: list[Word], pages: dict[int, PageImage]) -> BBox | None:
    if not words:
        return None
    p = pages[words[0].page]
    x0 = min(w.px[0] for w in words); y0 = min(w.px[1] for w in words)
    x1 = max(w.px[2] for w in words); y1 = max(w.px[3] for w in words)
    a, b = p.px_to_pt(x0, y0)
    c, d = p.px_to_pt(x1, y1)
    return BBox(page=words[0].page, x0=round(a, 1), y0=round(b, 1), x1=round(c, 1), y1=round(d, 1))


INCONSISTENT_CAP = 0.6  # 쪽마다 값이 다르게 읽힘 = 오독 신호 → 자동 부적합 판정에 쓰지 않도록 상한


def _confidence(checks: list[bool], hard_fail: bool = False, consistent: bool = True) -> float:
    """OCR 점수가 아니라 검증 통과율로 신뢰도를 매긴다 (실측: OCR 점수는 정답 여부와 무관)."""
    if hard_fail:
        return 0.2
    if not consistent:
        return min(INCONSISTENT_CAP, round(0.4 + 0.6 * sum(checks) / max(len(checks), 1), 2))
    if not checks:
        return 0.5
    return round(0.4 + 0.6 * sum(checks) / len(checks), 2)


def _birth_from_rrn(front6: str, g: str) -> date | None:
    century = {"1": 1900, "2": 1900, "5": 1900, "6": 1900,
               "3": 2000, "4": 2000, "7": 2000, "8": 2000,
               "9": 1800, "0": 1800}.get(g)
    if century is None:
        return None
    try:
        return date(century + int(front6[:2]), int(front6[2:4]), int(front6[4:6]))
    except ValueError:
        return None


# --- 페이지 단위 파싱 -----------------------------------------------------
def _parse_header(lines: list[list[Word]]) -> dict:
    out: dict = {"title": "", "issue": None, "issue_words": [], "doc_no": None,
                 "page_no": None, "issuer": None, "name": None, "name_words": [],
                 "birth": None, "gender": None, "birth_words": []}
    title_parts = []
    for line in lines:
        y = line[0].cy
        t = line_text(line)
        if y < HEADER_MAX_Y:
            title_parts.append(t)
            if (m := DOC_NO.search(t)) and out["doc_no"] is None:
                out["doc_no"] = m.group(0)
            for w in line:
                if w.x0 > 70 and (m := PAGE_NO.match(w.text)):
                    out["page_no"] = (int(m.group(1)), int(m.group(2)))
            ws = [w for w in line if w.x0 > 50 and KOR_DATE.search(w.text)]
            if ws and out["issue"] is None:
                out["issue"] = _to_date(KOR_DATE.search(ws[0].text))
                out["issue_words"] = ws
            if out["issuer"] is None and any(w.x0 > 55 for w in line) and ISSUER.search(t) and "증명" not in t:
                out["issuer"] = t.strip()
        if y < 26 and "주민등록번호" in squash(t) and (m := RRN.search(t)):
            out["birth"] = _birth_from_rrn(m.group(1), m.group(2))
            out["gender"] = m.group(2)
            out["birth_words"] = [w for w in line if RRN.search(w.text)]
            nws = [w for w in line if 15 <= w.x0 < 36 and "성명" not in w.text and not w.text.strip().startswith("(")]
            name = re.sub(r"[\s()（）]", "", "".join(w.text for w in nws))
            if name:
                out["name"] = name
                out["name_words"] = nws
    out["title"] = squash(" ".join(title_parts))
    return out


def _parse_applicant(lines: list[list[Word]]) -> dict:
    """첫 쪽 머리 상자의 '신청인: 성명 (생년월일)'을 읽는다."""
    for line in lines:
        flat = squash(line_text(line))
        marker = re.search(r"신청인[:：]?", flat)
        if not marker:
            continue
        remainder = flat[marker.end():]
        date_match = APPLICANT_DATE.search(remainder)
        if not date_match:
            continue
        name = re.sub(r"[^가-힣]", "", remainder[:date_match.start()])
        if not re.fullmatch(r"[가-힣]{2,6}", name):
            continue
        date_digits = re.sub(r"\D", "", date_match.group(1))
        try:
            if len(date_digits) != 8:
                continue
            birth = date(int(date_digits[:4]), int(date_digits[4:6]), int(date_digits[6:8]))
        except ValueError:
            continue
        return {"name": name, "birth": birth, "words": line}
    return {"name": None, "birth": None, "words": []}


def _table_bounds(lines: list[list[Word]]) -> tuple[float, float] | None:
    start = None
    for line in lines:
        t = squash(line_text(line))
        if line[0].cy > HEADER_MAX_Y and "번호" in t and ("세대주" in t or "신고일" in t or "발생일" in t):
            start = line[0].cy + 1.5   # 바로 아래 세로쓰기 소제목 줄 건너뜀
            break
    if start is None:
        return None
    end = FOOTER_Y
    for line in lines:
        t = squash(line_text(line))
        if line[0].cy > start and ("이하여백" in t or ("병역" in t and line[0].x0 < 12)):
            end = min(end, line[0].cy)
    return start, end


def _parse_rows(lines: list[list[Word]], start: float, end: float, page: int,
                entries: list[HistoryEntry], pending_notes: list[str], note_numbers: list[int]) -> None:
    for line in lines:
        if not (start <= line[0].cy < end):
            continue
        no = None; addr: list[str] = []; occ = rep = None
        reason: list[str] = []; holder: list[str] = []
        for w in line:
            t = w.text.strip()
            if w.x0 < COL_NO_MAX_X:
                if m := re.fullmatch(r"(\d{1,3})\s*(.*)", t):
                    no = int(m.group(1))
                    if m.group(2):
                        addr.append(m.group(2))
                continue
            if w.x0 < COL_ADDR_MAX_X:
                addr.append(t)
            elif COL_OCCUR_X[0] <= w.x0 < COL_OCCUR_X[1] and ISO_DATE.fullmatch(t):
                occ = _to_date(ISO_DATE.fullmatch(t))
            elif COL_REPORT_X[0] <= w.x0 < COL_REPORT_X[1] and ISO_DATE.fullmatch(t):
                rep = _to_date(ISO_DATE.fullmatch(t))
            elif COL_REASON_X[0] <= w.x0 < COL_REASON_X[1]:
                reason.append(t)
            elif w.x0 >= COL_HOLDER_MIN_X:
                holder.append(t)

        notes = [a for a in addr if a.startswith("[")]
        addr = [a for a in addr if not a.startswith("[")]
        pending_notes.extend(notes)
        if notes and rep is None and no is not None:
            # 실측: "[도로명주소 ...]", "[행정구역 변경 ...]" 메모 줄도 자기 순번을 가진다
            note_numbers.append(no)
            no = None

        if rep is not None:  # 신고일이 있는 줄 = 새 건의 첫 줄
            e = HistoryEntry(no=no, address=addr, occurred=occ, reported=rep,
                             reason=reason, holder=holder, notes=list(pending_notes),
                             page=page, words=list(line))
            pending_notes.clear()
            entries.append(e)
        elif entries and (no is not None or addr or reason or holder):  # 이어지는 줄
            e = entries[-1]
            if e.no is None and no is not None:
                e.no = no
            e.address += addr; e.reason += reason; e.holder += holder
            e.words += list(line)


# --- 메인 ---------------------------------------------------------------
def extract(pages: list[tuple[PageImage, OcrResult]], today: date | None = None) -> ResidentAbstractResult:
    today = today or kst_today()
    page_map = {p.page: p for p, _ in pages}
    headers = []
    first_page_lines: list[list[Word]] = []
    entries: list[HistoryEntry] = []
    pending: list[str] = []
    note_numbers: list[int] = []
    warnings: list[str] = []

    for p, r in pages:
        lines = group_lines(normalize(r.words, p.page, p.pixel_size))
        if p.page == 0:
            first_page_lines = lines
        headers.append(_parse_header(lines))
        bounds = _table_bounds(lines)
        if bounds:
            _parse_rows(lines, *bounds, p.page, entries, pending, note_numbers)
        else:
            warnings.append(f"page {p.page}: 주소 이력 표를 찾지 못함")

    # --- 서류 종류 ---
    titles = "".join(h["title"] for h in headers)
    is_abs = "(초본)" in titles or "이초본은" in titles
    is_reg = "(등본)" in titles or "이등본은" in titles
    if is_abs and not is_reg:
        detected, tconf = DocType.RESIDENT_ABSTRACT, 0.95
    elif is_reg and not is_abs:
        detected, tconf = DocType.RESIDENT_REGISTER, 0.95
    elif "주민등록표" in titles:
        detected, tconf = DocType.UNKNOWN, 0.4
        warnings.append("주민등록표이나 등본/초본 구분 실패")
    else:
        detected, tconf = DocType.UNKNOWN, 0.1

    validations: list[Validation] = []
    fields: dict[str, ExtractedField] = {}
    n = len(headers)

    def consistent(key: str) -> tuple[object, bool, list[Word]]:
        vals = [h[key] for h in headers if h[key] is not None]
        if not vals:
            return None, False, []
        top, cnt = Counter(vals).most_common(1)[0]
        words = next((h.get(f"{key}_words", []) for h in headers if h[key] == top), [])
        return top, cnt == len(vals) and len(vals) == n, words

    # --- 쪽 완전성 ---
    pnos = [h["page_no"] for h in headers if h["page_no"]]
    if pnos:
        total = pnos[0][1]
        seen = sorted({a for a, _ in pnos})
        ok = seen == list(range(1, total + 1))
        validations.append(Validation("pages_complete", ok, f"{seen} / 전체 {total}쪽"))
    else:
        validations.append(Validation("pages_complete", False, "쪽 번호를 읽지 못함"))

    # --- 문서확인번호 ---
    doc_no, doc_same, _ = consistent("doc_no")
    validations.append(Validation("doc_no_consistent", doc_same, "모든 쪽 동일" if doc_same else "쪽마다 다르거나 누락"))

    # --- 발급일 ---
    issue, issue_same, iw = consistent("issue")
    if issue:
        not_future = issue <= today
        validations += [Validation("issue_date_consistent", issue_same),
                        Validation("issue_date_not_future", not_future)]
        fields["issue_date"] = ExtractedField(
            value=issue, raw_text=iw[0].text if iw else "", source=FieldSource.OCR,
            confidence=_confidence([issue_same, not_future, doc_same], hard_fail=not not_future, consistent=issue_same),
            bbox=_bbox(iw, page_map))

    # --- 발급기관 ---
    issuer = next((h["issuer"] for h in headers if h["issuer"]), None)
    if issuer:
        fields["issuer"] = ExtractedField(value=issuer, raw_text=issuer, confidence=0.7, source=FieldSource.OCR)

    # --- 성명 ---
    name, name_same, nw = consistent("name")
    if name:
        plausible = bool(re.fullmatch(r"[가-힣]{2,6}", name))
        validations.append(Validation("name_consistent", name_same))
        fields["name"] = ExtractedField(
            value=name, raw_text=name, source=FieldSource.OCR,
            confidence=_confidence([name_same, plausible], consistent=name_same), bbox=_bbox(nw, page_map))

    # --- 생년월일 (주민번호 원문은 남기지 않음) ---
    birth, birth_same, bw = consistent("birth")
    if birth:
        g = next(h["gender"] for h in headers if h["birth"] == birth)
        validations.append(Validation("birth_consistent", birth_same))
        fields["birth_date"] = ExtractedField(
            value=birth, raw_text=f"{birth:%y%m%d}-{g}******", source=FieldSource.OCR,
            confidence=_confidence([birth_same, birth <= today], consistent=birth_same), bbox=_bbox(bw, page_map))

    # --- 첫 쪽 신청인 대조 정보 ---
    applicant = _parse_applicant(first_page_lines)
    if applicant["name"]:
        fields["applicant_name"] = ExtractedField(
            value=applicant["name"], raw_text=applicant["name"], source=FieldSource.OCR,
            confidence=0.9, bbox=_bbox(applicant["words"], page_map))
    if applicant["birth"]:
        fields["applicant_birth_date"] = ExtractedField(
            value=applicant["birth"], raw_text=applicant["birth"].isoformat(), source=FieldSource.OCR,
            confidence=0.9, bbox=_bbox(applicant["words"], page_map))
    if not applicant["name"] or not applicant["birth"]:
        warnings.append("첫 쪽 신청인 성명·생년월일을 모두 읽지 못함")

    # --- 주소 이력 ---
    entry_nos = [e.no for e in entries if e.no is not None]
    nos = sorted(entry_nos + note_numbers)
    if nos:
        seq_ok = nos == list(range(nos[0], nos[0] + len(nos))) and len(set(nos)) == len(nos)
        missing = sorted(set(range(nos[0], nos[-1] + 1)) - set(nos))
        validations.append(Validation(
            "history_numbers_sequential", seq_ok,
            f"순번 {len(nos)}개 (이력 {len(entry_nos)} + 메모 {len(note_numbers)}) / 건 {len(entries)}개"
            + (f", 빠진 번호 {missing}" if missing else "")))
    eff = [e.effective for e in entries if e.effective]
    order_ok = all(a <= b for a, b in zip(eff, eff[1:]))
    validations.append(Validation("history_dates_ordered", order_ok))
    occ_ok = all(e.occurred <= e.reported for e in entries if e.occurred and e.reported)
    validations.append(Validation("occurred_before_reported", occ_ok))

    hist_checks = [v.passed for v in validations if v.name.startswith(("history", "occurred"))]
    if entries:
        fields["address_history_count"] = ExtractedField(
            value=len(entries), raw_text=f"{len(entries)}건", source=FieldSource.OCR,
            confidence=_confidence(hist_checks))
        fields["address_history"] = ExtractedField(
            value=[{"no": e.no, "sido": resolved_sido(entries, i), "address": e.address_text,
                    "occurred": e.occurred, "reported": e.reported,
                    "reason": " ".join(e.reason), "notes": e.notes}
                   for i, e in enumerate(entries)],
            raw_text=f"{len(entries)}건", source=FieldSource.OCR,
            confidence=_confidence(hist_checks))
        last = entries[-1]
        fields["current_address"] = ExtractedField(
            value=last.address_text, raw_text=last.address_text, source=FieldSource.OCR,
            confidence=_confidence(hist_checks + [resolved_sido(entries, len(entries) - 1) is not None]),
            bbox=_bbox(last.words, page_map))

    return ResidentAbstractResult(detected, tconf, fields, entries, validations, warnings)


def resolved_sido(entries: list[HistoryEntry], i: int) -> str | None:
    """시도가 안 적힌 건(도로명 상세만 있는 경우 등)은 바로 앞 건의 시도를 이어받는다."""
    for e in reversed(entries[: i + 1]):
        if e.sido:
            return e.sido
    return None


def trailing_residence_start(entries: list[HistoryEntry], sido: str = "전북") -> date | None:
    """맨 마지막 건부터 거슬러 올라가며 해당 시도에 연속 거주를 시작한 날짜.

    세대주변경·행정구역 명칭 변경(전라북도→전북특별자치도) 같은 건은 시도가 같으므로 끊기지 않는다.
    """
    start = None
    for i in range(len(entries) - 1, -1, -1):
        if resolved_sido(entries, i) != sido:
            break
        start = entries[i].effective or start
    return start


def months_between(a: date, b: date) -> int:
    m = (b.year - a.year) * 12 + (b.month - a.month)
    return m - 1 if b.day < a.day else m

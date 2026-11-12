"""취업지원패키지 추가서류(결제영수증·응시서류·면접확인서) 공통 처리.

건강보험 서류의 `nhis_common`과 같은 역할이다. 이 서류들은 정부24 서식처럼 모양이 하나로
정해져 있지 않다(영수증은 가게·결제수단마다, 응시서류는 시행기관마다 다르고, 면접확인서는
사업계획서 서식을 기업이 손으로 채운다). 그래서 좌표를 고정하지 않고 '라벨 → 값'으로 읽는다:
라벨(합계금액·승인일시·응시일자 …)의 오른쪽, 없으면 바로 아래 한두 줄에서 값을 찾는다.
위치 판단은 다른 판독기와 같이 페이지 대비 퍼센트 좌표를 쓴다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Callable, Iterable, Iterator, Sequence

from ..pipeline.layout import Word, group_lines, line_text, normalize, squash
from ..pipeline.ocr import OcrResult, OcrWord
from ..pipeline.preprocess import PageImage
from ..schemas.models import ExtractedField, FieldSource
from . import nhis_common as common

DASHES = "-‐‑‒–—―"
AMOUNT_RE = re.compile(r"(?<![\d.,])(\d{1,3}(?:[,.]\d{3})+|\d{3,8})(?!\d)")
#: 품목 줄의 금액: 세 자리 쉼표 또는 '원'이 붙은 숫자만 (주소 번지·전화번호를 금액으로 세지 않게)
ITEM_AMOUNT_RE = re.compile(r"(?<![\d.,])\d{1,3}(?:,\d{3})+(?!\d)|(?<!\d)\d{3,7}\s*원")
TIME_RE = re.compile(r"(?<!\d)\d{1,2}\s*:\s*\d{2}(?:\s*:\s*\d{2})?(?!\d)")
TIME_RANGE_RE = re.compile(r"(\d{1,2}\s*:\s*\d{2})\s*[~∼〜～\-–]\s*(\d{1,2}\s*:\s*\d{2})")
#: 카드 전표의 두 자리 연도 날짜(26/03/15). 결제일 라벨 뒤에서만 쓴다.
SHORT_DATE_RE = re.compile(r"(?<!\d)(\d{2})\s*[./\-]\s*(\d{1,2})\s*[./\-]\s*(\d{1,2})(?!\d)")
#: OCR이 날짜와 시각을 붙여 읽은 경우('2026.09.2112:02'). 붙어 있으면 두 자리 일만 인정하고 사이를 띄운다.
GLUED_TIME_RE = re.compile(r"(?<!\d)((?:\d{4}|\d{2})\s*[./\-년]\s*\d{1,2}\s*[./\-월]\s*\d{2})(?=\d{1,2}\s*:\s*\d{2})")
BRN_RE = re.compile(rf"(?<!\d)(\d{{3}})\s*[{DASHES}]?\s*(\d{{2}})\s*[{DASHES}]?\s*(\d{{5}})(?!\d)")
RRN_RE = re.compile(rf"(?<!\d)(\d{{6}})\s*[{DASHES}]?\s*([1-8])(?:\s*[\d*]){{6}}(?![\d*])")
NAME_RE = re.compile(r"[가-힣]{2,5}")
NAME_STOPWORDS = frozenset({
    "성명", "이름", "생년월일", "주소", "응시자", "수험자", "수험번호", "한자", "본인",
    "대표", "대표자", "담당자", "확인", "서명", "응시", "시험",
})


@dataclass
class Hit:
    """라벨 하나로 찾은 값. `words`는 근거 위치(값이 적힌 단어)."""
    value: object
    raw: str
    words: list[Word]
    label: str
    same_line: bool = True


# ---------------------------------------------------------------------------
# 값 해석
# ---------------------------------------------------------------------------

def unglue_time(text: str) -> str:
    return GLUED_TIME_RE.sub(r"\1 ", text)


def parse_amount(text: str, minimum: int = 100) -> int | None:
    """금액(원). 날짜·시각을 먼저 지워 '2026.03.15'나 '14:20'을 금액으로 읽지 않는다."""
    cleaned = common.DATE_RE.sub(" ", unglue_time(text))
    cleaned = SHORT_DATE_RE.sub(" ", cleaned)
    cleaned = TIME_RE.sub(" ", cleaned)
    for match in AMOUNT_RE.finditer(cleaned):
        value = int(re.sub(r"[,.]", "", match.group(1)))
        if minimum <= value <= 10_000_000:
            return value
    return None


def parse_date(text: str, *, short_year: bool = False) -> date | None:
    text = unglue_time(text)
    value = common.parse_date(text)
    if value is not None or not short_year:
        return value
    match = SHORT_DATE_RE.search(text)
    if match is None:
        return None
    try:
        return date(2000 + int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def parse_short_year_date(text: str) -> date | None:
    return parse_date(text, short_year=True)


def parse_brn(text: str) -> str | None:
    match = BRN_RE.search(text)
    return f"{match.group(1)}-{match.group(2)}-{match.group(3)}" if match else None


def brn_check_digit(first_nine: Sequence[int]) -> int:
    """사업자등록번호 10번째 자리(검증숫자). 가중치 1,3,7,1,3,7,1,3,5."""
    weights = (1, 3, 7, 1, 3, 7, 1, 3, 5)
    total = sum(digit * weight for digit, weight in zip(first_nine, weights))
    total += (first_nine[8] * 5) // 10
    return (10 - total % 10) % 10


def brn_is_valid(number: str) -> bool:
    digits = [int(char) for char in re.sub(r"\D", "", number)]
    return len(digits) == 10 and brn_check_digit(digits[:9]) == digits[9]


def parse_name(text: str) -> str | None:
    for token in NAME_RE.findall(squash(text)):
        if token not in NAME_STOPWORDS:
            return token
    return None


def parse_text(text: str) -> str | None:
    value = re.sub(r"\s+", " ", text).strip(" :：|·-")
    if not value or len(squash(value)) > 40 or not re.search(r"[가-힣A-Za-z0-9]", value):
        return None
    return value


def same_company(a: str, b: str) -> bool:
    """회사명 비교: (주)·주식회사·공백·문장부호 차이는 같은 회사로 본다."""
    def norm(value: str) -> str:
        value = re.sub(r"\(주\)|㈜|주식회사|\(유\)|유한회사", "", value)
        return re.sub(r"[\s()（）.,·]", "", value)
    return bool(a and b) and norm(a) == norm(b)


# ---------------------------------------------------------------------------
# 줄·라벨
# ---------------------------------------------------------------------------

def birth_from_rrn(front: str, gender: str) -> date | None:
    century = 2000 if gender in "3478" else 1900
    try:
        return date(century + int(front[:2]), int(front[2:4]), int(front[4:6]))
    except ValueError:
        return None


def scrub_rrn(words: list[Word], originals: list[OcrWord]) -> date | None:
    """주민등록번호 뒷자리를 읽는 즉시 지운다(성별 자리만 남김). 앞자리로 생년월일을 돌려준다.

    `words`는 `normalize(originals)` 결과라 순서가 같다. 원본 OCR 단어도 함께 지운다.
    """
    birth = None
    for index, word in enumerate(words):
        text = word.text
        match = RRN_RE.search(text)
        if match:
            birth = birth or birth_from_rrn(match.group(1), match.group(2))
            text = RRN_RE.sub(lambda m: f"{m.group(1)}-{m.group(2)}******", text)
        elif re.fullmatch(r"[1-8][\d*]{6}", text) and index > 0:
            before = " ".join(item.text for item in words[max(0, index - 2):index])
            front = re.search(rf"(\d{{6}})\s*[{DASHES}]\s*$", before)
            if front:
                birth = birth or birth_from_rrn(front.group(1), text[0])
                text = text[0] + "******"
        if text != word.text:
            word.text = text
            if index < len(originals):
                originals[index].text = text
    return birth


def page_lines(pages: list[tuple[PageImage, OcrResult]]) -> tuple[list[list[Word]], date | None]:
    """모든 쪽의 단어를 줄로 묶는다(쪽 순서대로). 주민등록번호 뒷자리는 여기서 지운다."""
    lines: list[list[Word]] = []
    birth = None
    for page, result in pages:
        words = normalize(result.words, page.page, page.pixel_size or (1, 1))
        birth = scrub_rrn(words, result.words) or birth
        lines.extend(group_lines([word for word in words if word.text]))
    return lines, birth


def text_of(lines: list[list[Word]]) -> str:
    return "\n".join(line_text(line) for line in lines)


def find_hint(flat: str, hints: Sequence[str]) -> str | None:
    """공백을 지운 본문에서 처음 걸리는 단서."""
    return next((hint for hint in hints if squash(hint) in flat), None)


def stop_pattern(labels: Iterable[str]) -> re.Pattern[str]:
    """값을 오른쪽으로 읽다가 다른 칸의 라벨이 나오면 멈추는 패턴.

    짧은 라벨(세 글자 이하)은 앞이 공백이거나 줄 처음일 때만 멈춘다 ('한빛상호'처럼 값 안에 든
    글자에서 끊지 않게). 네 글자 이상 라벨은 OCR이 띄어쓰기를 빼고 한 상자로 읽어도 멈춘다.
    """
    keys = sorted({squash(label) for label in labels if squash(label)}, key=len, reverse=True)

    def spaced(key: str) -> str:
        return r"\s*".join(re.escape(char) for char in key)

    long_keys = "|".join(spaced(key) for key in keys if len(key) >= 4)
    short_keys = "|".join(spaced(key) for key in keys if len(key) < 4)
    parts = [f"(?:{long_keys})"] if long_keys else []
    if short_keys:
        parts.append(rf"(?:^|(?<=\s))(?:{short_keys})")
    return re.compile("|".join(parts) or r"(?!)")


def _line_index(line: list[Word]) -> tuple[str, list[tuple[int, int, Word]]]:
    flat = ""
    spans: list[tuple[int, int, Word]] = []
    for word in line:
        text = squash(word.text)
        spans.append((len(flat), len(flat) + len(text), word))
        flat += text
    return flat, spans


def _tail(spans: list[tuple[int, int, Word]], end: int) -> tuple[str, list[Word]]:
    """라벨 끝 뒤의 글자와 단어.

    라벨과 값이 한 상자로 읽힌 경우(RapidOCR는 줄 단위 상자를 자주 낸다) 그 상자의 나머지를
    원문 띄어쓰기 그대로 쓴다 — 뒤에 이어지는 다른 칸 라벨에서 끊으려면 띄어쓰기가 필요하다.
    """
    parts: list[str] = []
    words: list[Word] = []
    for start, stop, word in spans:
        if stop <= end:
            continue
        if start < end:
            kept = [index for index, char in enumerate(word.text) if not char.isspace()]
            rest = word.text[kept[end - start]:] if end - start < len(kept) else ""
            if rest.strip():
                parts.append(rest)
                words.append(word)
        else:
            parts.append(word.text)
            words.append(word)
    return " ".join(parts), words


def _under(line: list[Word], label_words: list[Word]) -> tuple[str, list[Word]]:
    """라벨 아래 줄에서 라벨 열에서 시작하는 단어 (결제 화면처럼 라벨 아래에 값을 쓰는 배치)."""
    x0 = min(word.x0 for word in label_words)
    x1 = max(word.x1 for word in label_words)
    words = [word for word in line if word.x1 > x0 - 1 and word.x0 < x1 + 25]
    return " ".join(word.text for word in words), words


def _cut(text: str, stop: re.Pattern[str]) -> str:
    match = stop.search(text)
    return text[:match.start()] if match else text


def iter_hits(lines: list[list[Word]], labels: Sequence[str], parse: Callable[[str], object | None], *,
              stop: re.Pattern[str], below: bool = True, exclude: Sequence[str] = ()) -> Iterator[Hit]:
    """라벨 우선순위대로, 위에서 아래로 값을 찾는다.

    exclude: 라벨 바로 앞에 붙으면 다른 칸이 되는 말 ('할인'+'금액', '받은'+'금액' 등).
    """
    excluded = tuple(squash(item) for item in exclude)
    for label in labels:
        key = squash(label)
        for index, line in enumerate(lines):
            flat, spans = _line_index(line)
            start = flat.find(key)
            while start >= 0:
                end = start + len(key)
                context = flat[max(0, start - 3):end]
                if not any(item in context for item in excluded if item != key):
                    label_words = [word for s, e, word in spans if s < end and e > start]
                    tail, words = _tail(spans, end)
                    text = _cut(tail, stop)
                    value = parse(text)
                    if value is not None:
                        yield Hit(value, text.strip(" :："), words or label_words, label)
                    elif below and label_words:
                        for following in lines[index + 1:index + 3]:
                            under, candidates = _under(following, label_words)
                            under = _cut(under, stop)
                            value = parse(under) if candidates else None
                            if value is not None:
                                yield Hit(value, under.strip(" :："), candidates, label, same_line=False)
                                break
                start = flat.find(key, start + 1)


def find(lines: list[list[Word]], labels: Sequence[str], parse: Callable[[str], object | None], *,
         stop: re.Pattern[str], below: bool = True, exclude: Sequence[str] = ()) -> Hit | None:
    return next(iter_hits(lines, labels, parse, stop=stop, below=below, exclude=exclude), None)


def find_all(lines: list[list[Word]], labels: Sequence[str], parse: Callable[[str], object | None], *,
             stop: re.Pattern[str], below: bool = True, exclude: Sequence[str] = ()) -> list[Hit]:
    return list(iter_hits(lines, labels, parse, stop=stop, below=below, exclude=exclude))


def dates_in_line(line: list[Word]) -> list[tuple[date, list[Word]]]:
    """`nhis_common.dates_in_line`에 날짜·시각이 붙어 읽힌 경우를 더한다."""
    found = common.dates_in_line(line)
    if found:
        return found
    value = common.parse_date(unglue_time(" ".join(word.text for word in line)))
    return [(value, line)] if value else []


def line_index_of(lines: list[list[Word]], hints: Sequence[str]) -> int | None:
    for index, line in enumerate(lines):
        if find_hint(squash(line_text(line)), hints):
            return index
    return None


# ---------------------------------------------------------------------------
# 필드
# ---------------------------------------------------------------------------

def ocr_ok(hit: Hit | None, threshold: float = 0.8) -> bool:
    """값 단어의 OCR 점수가 모두 기준 이상인가 (글자층은 1.0)."""
    return bool(hit and hit.words) and min(word.conf for word in hit.words) >= threshold


def to_field(hit: Hit, checks: list[bool], page_map: dict[int, PageImage],
             sources: dict[int, FieldSource]) -> ExtractedField:
    """필드 신뢰도는 다른 판독기와 같이 검증 통과율(0.4+0.6×통과율)이다."""
    return common.make_field(hit.value, hit.raw, hit.words, page_map, common.confidence(checks), sources)


def raw_field(value, raw: str, words: list[Word], checks: list[bool], page_map: dict[int, PageImage],
              sources: dict[int, FieldSource]) -> ExtractedField:
    return common.make_field(value, raw, words, page_map, common.confidence(checks), sources)

"""Shared value masking for tools that may inspect real applicant documents."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable


ALLOWED_LABELS = (
    "주민등록표", "초본", "등본", "성명", "주민등록번호", "주소", "발생일", "신고일",
    "변동사유", "전입", "전출", "세대주", "관계", "본인", "번호", "발급", "발급일",
    "발급일자", "발급번호", "발급일시", "문서확인번호", "시장", "군수", "구청장", "읍장",
    "면장", "동장", "직인", "개인", "인적사항", "변경", "내용", "변동", "사항", "정정",
    "말소", "재등록", "병역", "이하", "여백", "페이지", "쪽", "년", "월", "일", "용도",
    "제출처", "확인", "증명", "전라북도", "전북특별자치도", "특별자치도", "광역시", "특별시",
    "주민등록법", "제29조", "에", "의하여", "위", "와", "같이", "합니다", "국민연금",
    "건강보험", "고용보험", "산재보험", "사회보험", "가입내역", "확인서", "가입자", "사업장",
    "명칭", "관리번호", "사업장관리번호", "사업장명칭", "구분", "자격", "취득일", "자격취득일",
    "신고접수일", "가입자종별", "미가입", "해당없음", "지역", "지역가입자",
    "직장", "직장가입자", "직장피부양자", "사업장가입자", "외국인", "등록번호",
    "주민(외국인)등록번호", "현재", "기준", "공단", "고지금액", "납부금액", "토큰",
    "4대사회보험정보연계", "가입자 가입내역 확인서", "발급일자", "내역",
)
ALLOWED_REGIONS = (
    "서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시", "대전광역시",
    "울산광역시", "세종특별자치시", "경기도", "강원특별자치도", "강원도", "충청북도",
    "충청남도", "전북특별자치도", "전라북도", "전라남도", "경상북도", "경상남도",
    "제주특별자치도", "제주도", "서울", "부산", "대구", "인천", "광주", "대전", "울산",
    "세종", "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
)
_RRN_PATTERNS = (
    re.compile(r"(?<!\d)\d{6}\s*[-‐‑‒–—―~]\s*\d(?:\s?\d){6}(?!\d)"),
    re.compile(r"(?<!\d)\d{6}\s*[-‐‑‒–—―~]\s*[\d*]\*{6}(?![\d*])"),
    re.compile(r"(?<!\d)\d{13}(?!\d)"),
)
_MODEL_TOKEN = re.compile(r"<\|[^|\r\n]*?\|>")


def _is_hangul(code: int) -> bool:
    return (0xAC00 <= code <= 0xD7A3 or 0x1100 <= code <= 0x11FF or
            0x3130 <= code <= 0x318F or 0xA960 <= code <= 0xA97F or 0xD7B0 <= code <= 0xD7FF)


def _is_han(code: int) -> bool:
    return (0x3400 <= code <= 0x4DBF or 0x4E00 <= code <= 0x9FFF or
            0xF900 <= code <= 0xFAFF or 0x20000 <= code <= 0x323AF or
            0x2F800 <= code <= 0x2FA1F)


def _is_kana(code: int) -> bool:
    return (0x3040 <= code <= 0x30FF or 0x31F0 <= code <= 0x31FF or
            0xFF66 <= code <= 0xFF9F or 0x1B000 <= code <= 0x1B16F or
            0x1AFF0 <= code <= 0x1AFFF)


def _mask_character(char: str) -> str:
    code = ord(char)
    if _is_hangul(code):
        return "가"
    if char.isdigit():
        return "9"
    if char.isascii() and char.isalpha() or unicodedata.name(char, "").startswith("LATIN "):
        return "a"
    if _is_han(code):
        return "漢"
    if _is_kana(code):
        return "カ"
    category = unicodedata.category(char)
    if char.isspace() or category.startswith(("P", "Z")):
        return char
    if code < 128 and not char.isalnum():
        return char
    return "?"


def mask_text(text: str, *, labels: Iterable[str] = ()) -> str:
    """Mask PII while keeping approved form labels and region names readable."""
    text = _MODEL_TOKEN.sub("[토큰]", text)
    for pattern in _RRN_PATTERNS:
        text = pattern.sub("[주민번호]", text)
    keep = sorted(set(ALLOWED_LABELS + ALLOWED_REGIONS + tuple(labels) + ("주민번호",)),
                  key=len, reverse=True)
    label_re = re.compile("|".join(re.escape(label) for label in keep if label))
    out: list[str] = []
    cursor = 0
    for match in label_re.finditer(text):
        out.extend(_mask_character(char) for char in text[cursor:match.start()])
        out.append(match.group())
        cursor = match.end()
    out.extend(_mask_character(char) for char in text[cursor:])
    return "".join(out)

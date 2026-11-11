"""Page-level quality metrics for noisy vision-language OCR responses."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass


# Thresholds and weights are intentionally centralized for calibration after synthetic runs.
HALLUCINATION_THRESHOLDS = {
    "non_local_script_ratio": 0.15,
    "repeated_line_ratio": 0.30,
    "repeated_phrase_ratio": 0.18,
    "characters_per_megapixel": 1200.0,
    "minimum_long_response_chars": 2000,
    "fail_score": 0.45,
    "weights": {"scripts": 0.50, "repetition": 0.25, "length": 0.25},
}


@dataclass(frozen=True)
class HallucinationAssessment:
    score: float
    hangul_ratio: float
    non_local_script_ratio: float
    repeated_line_ratio: float
    repeated_phrase_ratio: float
    characters_per_megapixel: float
    reasons: tuple[str, ...]

    @property
    def failed(self) -> bool:
        return self.score >= HALLUCINATION_THRESHOLDS["fail_score"]


def _is_korean_or_latin(char: str) -> bool:
    code = ord(char)
    if (0xAC00 <= code <= 0xD7A3 or 0x1100 <= code <= 0x11FF or
            0x3130 <= code <= 0x318F or 0xA960 <= code <= 0xA97F or 0xD7B0 <= code <= 0xD7FF):
        return True
    return char.isdigit() or char.isascii() and char.isalpha() or unicodedata.name(char, "").startswith("LATIN ")


def assess_page(text_lines: list[str], table_content: str, image_size: tuple[int, int]) -> HallucinationAssessment:
    text = "\n".join(text_lines) + "\n" + table_content
    relevant = [char for char in text if char.isalpha() or char.isdigit()]
    non_local = sum(not _is_korean_or_latin(char) for char in relevant)
    script_ratio = non_local / len(relevant) if relevant else 0.0
    hangul = sum(0xAC00 <= ord(char) <= 0xD7A3 or 0x1100 <= ord(char) <= 0x11FF or
                 0x3130 <= ord(char) <= 0x318F for char in relevant)
    hangul_ratio = hangul / len(relevant) if relevant else 0.0

    normalized = [re.sub(r"\s+", " ", line).strip() for line in text_lines if line.strip()]
    counts = Counter(normalized)
    repeated = sum(count - 1 for count in counts.values() if count > 1)
    repeated_ratio = repeated / len(normalized) if normalized else 0.0

    compact = re.sub(r"<[^>]*>|\s+|\|", "", text).lower()[:20_000]
    repeated_phrase_ratio = 0.0
    for size in range(4, min(17, len(compact) // 3 + 1)):
        ngrams = Counter(compact[index:index + size] for index in range(len(compact) - size + 1))
        repeated_span = max(((count - 1) * size for count in ngrams.values() if count >= 3), default=0)
        repeated_phrase_ratio = max(repeated_phrase_ratio, repeated_span / max(len(compact), 1))

    width, height = image_size
    megapixels = max(width * height / 1_000_000, 0.01)
    chars_per_mp = len(text) / megapixels
    thresholds = HALLUCINATION_THRESHOLDS
    weights = thresholds["weights"]
    script_score = min(1.0, script_ratio / thresholds["non_local_script_ratio"]) * weights["scripts"]
    repeat_score = max(
        min(1.0, repeated_ratio / thresholds["repeated_line_ratio"]),
        min(1.0, repeated_phrase_ratio / thresholds["repeated_phrase_ratio"]),
    ) * weights["repetition"]
    length_score = 0.0
    if len(text) >= thresholds["minimum_long_response_chars"]:
        length_score = min(1.0, chars_per_mp / thresholds["characters_per_megapixel"]) * weights["length"]
    score = min(1.0, script_score + repeat_score + length_score)

    reasons = []
    if script_ratio >= thresholds["non_local_script_ratio"]:
        reasons.append("비한국어 문자 비율 높음")
    if (repeated_ratio >= thresholds["repeated_line_ratio"] or
            repeated_phrase_ratio >= thresholds["repeated_phrase_ratio"]):
        reasons.append("같은 줄 반복")
    if len(text) >= thresholds["minimum_long_response_chars"] and chars_per_mp >= thresholds["characters_per_megapixel"]:
        reasons.append("이미지 대비 응답 과다")
    return HallucinationAssessment(round(score, 3), hangul_ratio, script_ratio,
                                   repeated_ratio, repeated_phrase_ratio, chars_per_mp, tuple(reasons))

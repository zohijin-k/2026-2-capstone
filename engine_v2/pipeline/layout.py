"""OCR 단어를 페이지 비율 좌표(%)로 정규화하고 줄 단위로 묶는다.

추출기는 픽셀이 아니라 % 좌표로 위치를 판단한다 → 해상도가 달라도 같은 규칙이 통한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from pipeline.ocr import OcrWord


@dataclass
class Word:
    text: str
    conf: float
    page: int
    x0: float  # 페이지 너비 대비 %
    y0: float  # 페이지 높이 대비 %
    x1: float
    y1: float
    px: tuple[float, float, float, float]  # 원본 픽셀 bbox (근거 하이라이트용)

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2


def normalize(words: list[OcrWord], page: int, size: tuple[int, int]) -> list[Word]:
    W, H = size
    return [
        Word(w.text, w.confidence, page,
             w.bbox_px[0] / W * 100, w.bbox_px[1] / H * 100,
             w.bbox_px[2] / W * 100, w.bbox_px[3] / H * 100, w.bbox_px)
        for w in words
    ]


def group_lines(words: list[Word], tol: float = 0.6) -> list[list[Word]]:
    """세로 중심 차이가 글자 높이의 tol배 이내면 같은 줄. 줄 안은 왼→오른 정렬."""
    lines: list[list[Word]] = []
    for w in sorted(words, key=lambda w: w.cy):
        h = max(w.y1 - w.y0, 0.3)
        if lines:
            last = lines[-1]
            ly = sum(x.cy for x in last) / len(last)
            if abs(w.cy - ly) <= h * tol:
                last.append(w)
                continue
        lines.append([w])
    return [sorted(l, key=lambda w: w.x0) for l in lines]


def squash(s: str) -> str:
    return re.sub(r"\s+", "", s)


def line_text(line: list[Word]) -> str:
    return " ".join(w.text for w in line)

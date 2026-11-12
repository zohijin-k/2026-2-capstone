"""Conservative coordinate fallback for split resident-document titles."""
from __future__ import annotations

import re
from statistics import median

from .layout import group_lines, normalize, squash


def classify_resident_title(pages) -> tuple[str | None, str]:
    """Return abstract/register only from large adjacent upper-page title words.

    Callers run their legacy keyword classifier first. Reading order outside the
    title, small side notices and lower-page combined notices are not evidence.
    """
    from ..extractors.nhis_forms import label_hits

    kinds = set()
    seen = False
    for page, result in pages:
        if not page.pixel_size:
            continue
        words = normalize(result.words, page.page, page.pixel_size)
        heights = [w.y1 - w.y0 for w in words if re.search('[가-힣]', w.text)]
        if not heights:
            continue
        ordinary = median(heights)
        upper = [w for w in words if w.cy <= 25]
        mains = label_hits(group_lines(upper), ('주민등록표',))
        for _, main in mains:
            left, right = min(w.x0 for w in main), max(w.x1 for w in main)
            top, bottom = min(w.y0 for w in main), max(w.y1 for w in main)
            height = bottom - top
            if height < 1.25 * ordinary:
                continue
            seen = True
            glyph_width = (right - left) / 5
            below = [w for w in upper if w not in main and
                     top < w.cy <= bottom + 1.8 * height and
                     left - .4 * glyph_width <= w.x0 and w.x1 <= right + .4 * glyph_width and
                     w.y1 - w.y0 >= .55 * height]
            beside = [w for w in upper if w not in main and
                      abs(w.cy - (top + bottom) / 2) <= .6 * height and
                      right <= w.x0 <= right + 2 * glyph_width and
                      w.y1 - w.y0 >= .55 * height]
            for row in group_lines(below) + group_lines(beside):
                text = re.sub('[^가-힣]', '', ''.join(squash(w.text) for w in row))
                if '등초본' in text or '초등본' in text:
                    kinds.update(('abstract', 'register'))
                if '초본' in text:
                    kinds.add('abstract')
                if '등본' in text:
                    kinds.add('register')
    if seen and len(kinds) == 1:
        return next(iter(kinds)), '좌표 제목 규칙: 쪽 상단 큰 주민등록표 제목과 인접한 구분 글자를 확인했습니다.'
    return None, '좌표 제목 규칙: 제목 구분 근거가 없거나 충돌합니다.'

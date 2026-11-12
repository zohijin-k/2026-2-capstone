"""Fictitious multi-page resident notes with source-shaped unequal OCR boxes."""
import random
import re

from engine_v2.tests.test_resident_abstract import build

NAME = "가상인"
BIRTH = "1999-01-01"
ISSUE = "2026-03-03"


def resident(*, name=NAME, scale=1, jitter=0, skew=0, boundary=False, offset=0):
    pages = build(name=name, issue="2026년 03월 03일", applicant=f"신청인: {name} ({BIRTH})")
    words = pages[2][1].words
    number = next(word for word in words if word.text == "10")
    note = next(word for word in words if word.text.startswith("[행정구역"))
    number.bbox_px = (170, 1101, 221, 1147)
    note.bbox_px = (278, 1129, 1054, 1160)
    if boundary:
        moved = [word for word in words if word.text == "8" or word.text.startswith("[도로명")]
        for word in moved:
            words.remove(word)
        moved[0].bbox_px = (170, 1800, 221, 1846)
        moved[1].bbox_px = (278, 1828, 1054, 1859)
        pages[1][1].words.extend(moved)
    rng = random.Random(17)
    for page, result in pages:
        for word in result.words:
            x0, y0, x1, y1 = word.bbox_px
            if x0 / page.pixel_size[0] * 100 < 11.5 and re.fullmatch(r"\d{1,3}", word.text):
                word.text = str(int(word.text) + offset)
            dx, dy = rng.uniform(-jitter, jitter), rng.uniform(-jitter, jitter)
            dy += skew * ((x0 + x1) / 2 / page.pixel_size[0] - .5)
            word.bbox_px = tuple(value * scale for value in (x0 + dx, y0 + dy, x1 + dx, y1 + dy))
        page.pixel_size = tuple(round(value * scale) for value in page.pixel_size)
        result.engine = "own"
    return pages


def damage(pages, defect):
    for page, result in pages:
        numbered = [word for word in result.words if word.bbox_px[0] / page.pixel_size[0] * 100 < 11.5
                    and re.fullmatch(r"\d{1,3}", word.text)]
        for word in numbered:
            missing = defect == "all" or (defect == "first" and word.text == "1") or (
                defect == "last" and word.text == "11") or (defect == "middle" and word.text == "5") or (
                defect == "note" and word.text == "10")
            if missing:
                result.words.remove(word)
            elif defect == "duplicate" and word.text == "5":
                word.text = "4"
            elif defect == "unreadable" and word.text == "5":
                word.text = "A"
    return pages

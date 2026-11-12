"""Fictitious own-OCR words following redacted second-applicant form shapes."""
import random

from engine_v2.pipeline.ocr import OcrResult, OcrWord
from engine_v2.pipeline.preprocess import PageImage, PageSource

NAME = "가상인"
BIRTH = "1990-01-01"
ISSUE = "2026-03-03"


def cell(x0, y0, x1, y1, text, confidence=.99):
    return (x0, y0, x1, y1, text, confidence)


def page(cells, *, size=(2480, 3505), scale=1, jitter=0, skew=0, seed=7):
    rng = random.Random(seed)
    words = []
    for x0, y0, x1, y1, text, confidence in cells:
        dx, dy = rng.uniform(-jitter, jitter), rng.uniform(-jitter, jitter)
        dy += skew * ((x0 + x1) / 2 / size[0] - .5)
        bbox = tuple(value * scale for value in (x0 + dx, y0 + dy, x1 + dx, y1 + dy))
        words.append(OcrWord(text, confidence, bbox))
    image = PageImage(0, PageSource.EMBEDDED, (595, 842),
                      pixel_size=tuple(round(value * scale) for value in size), dpi=250 * scale)
    return image, OcrResult("own", words)


def acquisition(*, name=NAME, count=3, gap=True, overlap=False, full_rrn=True,
                noise=True, marker="이하여백", separators=False):
    """Empty employer cells, regional rows, marker-only end and blank-row overprints."""
    cells = [cell(2165, 50, 2319, 81, "국민건강보험공단", 1),
             cell(222, 224, 343, 280, "1/ 1", .89),
             cell(216, 332, 990, 386, "발급번호:G" + "0" * 18),
             cell(789, 430, 1697, 516, "건강보험자격득실확인서", 1),
             cell(769, 583, 887, 659, "성명", 1),
             cell(1539, 590, 1970, 648, "주 민 등 록 번 호", .97),
             cell(193, 650, 454, 720, "확인청구자", 1),
             cell(828 - 28 * len(name), 713, 828 + 28 * len(name), 790, name, 1),
             cell(1579, 725, 1929, 778, "900101-1123456" if full_rrn else "900101-1******"),
             cell(909, 849, 1582, 913, "자 격 득 실 확 인 내 역", .93),
             cell(167, 980, 241, 1044, "No", .93),
             cell(320, 978, 577, 1044, "가입자구분", 1),
             cell(966, 978, 1226, 1044, "사업장명칭", 1),
             cell(1628, 978, 1888, 1044, "자격취득일", 1),
             cell(2025, 978, 2284, 1044, "자격상실일", .99)]
    current_year = 2024 if count >= 3 else 2020
    for index in range(count):
        y = 1115 + 128 * index
        acquired = current_year - 4 * index
        cells.extend([cell(185, y, 230, y + 48, str(index + 1), 1),
                      cell(258, y - 4, 474, y + 48, "지역세대주" if index == 0 else "지역세대원", 1),
                      cell(1652, y, 1867, y + 46, f"{acquired}.01.01", 1)])
        if index:
            upper_year = current_year - 4 * (index - 1)
            lost = upper_year - (1 if gap else 0)
            if overlap and index == 1:
                lost = upper_year + 1
            cells.append(cell(2048, y, 2263, y + 46, f"{lost}.01.01", 1))
    marker_y = 1115 + 128 * count - 10
    cells.append(cell(646, marker_y, 831, marker_y + 65, marker, 1))
    if separators:
        cells.extend([cell(258, marker_y, 474, marker_y + 55, "===", 1),
                      cell(1652, marker_y, 1867, marker_y + 55, "~~", 1),
                      cell(2048, marker_y, 2263, marker_y + 55, "···", 1)])
    footer_y = max(2475, marker_y + 900)
    cells.extend([cell(325, footer_y, 1444, footer_y + 54,
                       "건강보험 자격득실내역을 위와 같이 확인합니다.", .99),
                  cell(1103, footer_y + 110, 1361, footer_y + 162, "2026.03.03", 1),
                  cell(752, footer_y + 289, 1657, footer_y + 380, "국민건강보험공단 이사장", .99)])
    if noise:
        cells.extend([cell(845, 1201, 1105, 1420, ".II", .64),
                      cell(1574, marker_y + 544, 1742, marker_y + 711, "I", .48),
                      cell(1398, marker_y + 582, 1689, marker_y + 870, "I", .5),
                      cell(1141, marker_y + 764, 1248, marker_y + 841, "가", 1),
                      cell(1309, marker_y + 768, 1410, marker_y + 850, "상", .93)])
    return cells, (2480, max(3505, footer_y + 440))

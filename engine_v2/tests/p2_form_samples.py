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


def qualification(*, name=NAME, count=1, noise=True, marker="이하여백", separators=False,
                  same_dates=True, issuer_role=" 이사", empty_management=True):
    """One member, empty management/suspension cells and distant seal artifacts."""
    request = "2026.03.03" if same_dates else "2026.03.01"
    validity = "2026.03.03" if same_dates else "2026.04.03"
    cells = [cell(2112, 40, 2317, 82, "국민건강보험공단", 1),
             cell(220, 220, 346, 281, "1/1", .99),
             cell(721, 365, 1757, 456, "건강보험 자격확인(통보)서", .99),
             cell(185, 551, 1013, 605, "통보번호:0-0000-20260301-000000", .99),
             cell(210, 676, 444, 732, "수신기관명", 1),
             cell(671, 671, 908, 736, "가상기관용", 1),
             cell(1180, 677, 1503, 729, "자격확인요청일", 1),
             cell(1841, 677, 2079, 729, request, 1),
             cell(229, 820, 429, 880, "증번호", .98),
             cell(658, 826, 919, 878, "00000000000", 1),
             cell(1180, 824, 1506, 876, "사업장관리번호", 1),
             cell(732, 956, 845, 1031, "성명", 1),
             cell(1517, 964, 1911, 1017, "주 민 등 록 번 호", .95),
             cell(227, 998, 428, 1064, "가입자", 1),
             cell(233, 1065, 424, 1125, "(세대주)", 1),
             cell(789 - 27 * len(name), 1091, 789 + 27 * len(name), 1163, name, 1),
             cell(1551, 1103, 1878, 1151, "900101–1******", .97),
             cell(989, 1224, 1416, 1304, "자격확인내", 1),
             cell(1420, 1236, 1486, 1292, "역", 1),
             cell(185, 1361, 369, 1438, "성명", 1),
             cell(501, 1370, 787, 1427, "주민등록번호", 1),
             cell(949, 1368, 1188, 1434, "자격취득일", .99),
             cell(1301, 1368, 1540, 1434, "자격상실일", 1),
             cell(1730, 1370, 2194, 1430, "급여정지사유 및 기간", .98)]
    if not empty_management:
        cells.append(cell(1841, 826, 2079, 878, "00000000000", 1))
    for index in range(count):
        y = 1481 + 112 * index
        member_name = name if index == 0 else "가상원"
        cells.extend([cell(155, y, 155 + 47 * len(member_name), y + 66, member_name, 1),
                      cell(413, y + 12, 706, y + 54, "900101–1******", .98),
                      cell(959, y + 7, 1180, y + 58, "2020.01.01", 1)])
    marker_y = 1481 + 112 * count + 3
    cells.append(cell(977, marker_y, 1159, marker_y + 59, marker, 1))
    if separators:
        cells.extend([cell(155, marker_y, 295, marker_y + 55, "===", 1),
                      cell(413, marker_y, 706, marker_y + 55, "~~", 1),
                      cell(1301, marker_y, 1540, marker_y + 55, "···", 1),
                      cell(1730, marker_y, 2194, marker_y + 55, "--", 1)])
    footer_y = max(2635, marker_y + 1000)
    cells.extend([cell(292, footer_y, 1159, footer_y + 54,
                       "이와같이 건강보험자격을 확인합니다.", .98),
                  cell(1114, footer_y + 91, 1375, footer_y + 154, "2026.03.03", 1),
                  cell(764, footer_y + 220, 1643, footer_y + 315, "국민건강보험공단" + issuer_role, 1),
                  cell(278, footer_y + 376, 889, footer_y + 424, validity + " 까지 유효합니다.", .98)])
    if noise:
        cells.extend([cell(1521, 1279, 1566, 1322, "1", .2),
                      cell(954, 1303, 968, 1315, "1", .15),
                      cell(1614, 1362, 1675, 1423, "I", .54),
                      cell(797, 1480, 827, 1507, "1", .18),
                      cell(1725, marker_y + 380, 1753, marker_y + 410, ".", .39),
                      cell(772, marker_y + 382, 798, marker_y + 407, "1", .1),
                      cell(1579, marker_y + 433, 1743, marker_y + 590, "1I", .21),
                      cell(1645, footer_y + 169, 1838, footer_y + 250, "가상도장", .33),
                      cell(1648, footer_y + 284, 1842, footer_y + 361, "가상도장", .35)])
    return cells, (2480, max(3505, footer_y + 650))

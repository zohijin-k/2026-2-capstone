"""Fictitious payment cells with the observed own-OCR word geometry."""
from .p2_form_samples import BIRTH, ISSUE, NAME, cell, page


def payment(*, name=NAME, corrected=False, optional=False, workplace="", trailing_blank=True,
            paid_different=False):
    cells = [cell(346, 98, 1082, 138, "문서확인번호:0000-0000-0000-00000", 1),
             cell(613, 411, 1453, 470, "가입자 건강·장기요양보험료 납부확인서", 1),
             cell(169, 507, 344, 563, "가입자 성명", .95),
             cell(1176, 508, 1309, 561, "생년월일", 1),
             cell(750 - 18 * len(name), 509, 750 + 18 * len(name), 560, name, 1),
             cell(1538, 512, 1733, 555, "1990.01.01.", 1),
             cell(167, 586, 344, 640, "사업장명칭", 1),
             cell(1162, 587, 1321, 637, "납부자번호", 1),
             cell(1525, 590, 1748, 634, "00000000000", 1),
             cell(757, 660, 1310, 701, "2025년 10월 ~ 2025년 12월 납부내역", .92),
             cell(1776, 700, 1920, 750, "(단위:원)", 1),
             cell(640, 762, 778, 815, "고지금액", 1),
             cell(1447, 762, 1586, 815, "납부금액", 1),
             cell(187, 830, 265, 887, "월별", 1)]
    if workplace:
        cells.append(cell(650, 587, 930, 638, workplace, 1))
    for health, care, outside_health, outside_care in ((407, 606, 809, 1010), (1212, 1414, 1616, 1817)):
        cells.extend([cell(health - 40, 838, health + 41, 890, "건강", 1),
                      cell(health - 55, 883, health + 50, 937, "보험료", 1),
                      cell(care - 67, 840, care + 68, 889, "장기요양", 1),
                      cell(care - 52, 883, care + 53, 934, "보험료", 1)])
        for center, kind in ((outside_health, "건강"), (outside_care, "요양")):
            cells.extend([cell(center - 57, 820, center + 60, 868, "보수외", .97),
                          cell(center - 68, 857, center + 69, 910, "소득월액", 1),
                          cell(center - 49, 904, center + 50, 952, f"({kind})", 1)])
    totals = [0] * 8
    for month in range(1, 13):
        y = 962 + (month - 1) * 59
        cells.append(cell(196 if month < 10 else 185, y - 3,
                          258 if month < 10 else 270, y + 54, f"{month}월", 1))
        health = {10: 100_000, 11: 20_000, 12: 30_000}.get(month, 0)
        care = health // 10
        outside = 1000 if optional and month == 10 else None
        outside_care = 100 if optional and month == 10 else None
        billed = [health, care, outside, outside_care]
        paid = [value // 2 if value is not None else None for value in billed] if paid_different else billed
        amounts = billed + paid
        for index, (center, amount) in enumerate(zip((407, 606, 809, 1010, 1212, 1414, 1616, 1817), amounts)):
            if amount is None:
                continue
            totals[index] += amount
            text = f"{amount:,}"
            confidence = 1 if amount else (.33 + ((month + index) % 7) * .05)
            if corrected and amount == 0:
                text = "O" if (month + index) % 2 else "o"
            elif corrected and month == 10 and index == 0:
                text = "I00.000"
            width = 30 if amount == 0 else (145 if amount >= 100_000 else 122 if amount >= 10_000 else 105)
            cells.append(cell(center - width / 2, y, center + width / 2, y + 49, text, confidence))
    sum_y = 1726 if trailing_blank else 1680
    cells.append(cell(186, sum_y, 264, sum_y + 54, "합계", 1))
    for index, (center, amount) in enumerate(zip((407, 606, 809, 1010, 1212, 1414, 1616, 1817), totals)):
        if index in (2, 3, 6, 7) and not optional:
            continue
        cells.append(cell(center - 72, sum_y, center + 72, sum_y + 54, f"{amount:,}", 1))
    grand = sum(totals[4:])
    cells.extend([cell(261, 1795, 395, 1851, "납부총액", 1),
                  cell(738, 1799, 879, 1848, f"{grand:,}", 1),
                  cell(1245, 1798, 1379, 1851, "용도구분", 1),
                  cell(1638, 1798, 1799, 1848, "납부확인용", 1),
                  cell(724, 1881, 1343, 1921, "위와 같이 보험료를 납부하였음을 확인합니다", 1),
                  cell(883, 1957, 1182, 2000, "2026 년 03 월 03 일", 1),
                  cell(1252, 2010, 1392, 2070, "I상", .54),
                  cell(1219, 2022, 1423, 2185, "가상", .22),
                  cell(773, 2063, 1249, 2117, "국민건강보험공단 이사장", 1)])
    return cells, (2065, 2923)

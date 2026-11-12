"""Fictitious business-proof words with the observed own-OCR form geometry."""
from .p2_form_samples import BIRTH, ISSUE, cell, page

NAME = "김가상"
NUMBER = "123-45-67891"
CORPORATE_NUMBER = "123-81-12341"


def business(*, name=NAME, number=NUMBER, joint_count=0, noise=True, multiline=False,
             blank_rows=True, representative_role=""):
    representative = name + (f"({representative_role})" if representative_role else "")
    cells = [cell(683, 372, 1373, 443, "사 업자등록증명", .97),
             cell(226, 379, 430, 426, "발급번호", .99),
             cell(1635, 379, 1837, 426, "처리기간", 1),
             cell(850, 452, 1215, 513, "(일반과세자)", 1),
             cell(1645, 472, 1692, 522, "즉", 1), cell(1779, 471, 1831, 522, "시", 1),
             cell(166, 474, 486, 509, "1234-567-8901-234", 1),
             cell(240, 568, 535, 612, "상 호 (법 인 명)", .92),
             cell(657, 562, 882, 609, "가상합성상점", 1),
             cell(245, 657, 530, 697, "사업자등록번호", 1),
             cell(661, 655, 909, 695, number, 1),
             cell(219, 748, 559, 795, "대표자성명(대표유형)", 1),
             cell(650, 742, 650 + 40 * len(representative), 801, representative, 1),
             cell(237, 843, 535, 883, "주민(법인)등록번호", .98),
             cell(661, 843, 953, 878, "900101-1654321", 1),
             cell(230, 928, 540, 972, "사업장소재 지", .95),
             cell(664, 925, 1735, 961, "전북특별자치도 전주시 가상구 합성9길 12,345동 678호(가상동9가)", .99),
             cell(229, 1012, 280, 1061, "개", 1), cell(364, 1013, 408, 1062, "업", 1),
             cell(495, 1011, 539, 1062, "일", 1),
             cell(659, 1003, 958, 1057, "2018년 01월 02일", .94),
             cell(237, 1103, 534, 1142, "사업자등록일", 1),
             cell(658, 1096, 953, 1140, "2018년 01월 03일", .91),
             cell(233, 1232, 270, 1274, "업", 1), cell(497, 1228, 545, 1276, "태", .96),
             cell(637, 1194, 1323, 1234, "가상업종가|합성 품목가 제공업|가짜서비스", .99),
             cell(230, 1444, 276, 1492, "종", .99), cell(500, 1443, 542, 1487, "목", 1),
             cell(633, 1353, 1380, 1410, "가상품목가|가상 상품가 판매업|합성서비스업", .93),
             cell(862, 1612, 1066, 1660, "성명(법인명)", 1),
             cell(1441, 1616, 1778, 1656, "주민(사업자)등록번호", .97),
             cell(227, 1738, 547, 1787, "공 동 사 업 자", .97),
             cell(855, 1939, 1208, 1979, "위와 같이 증명합니다.", .96),
             cell(170, 2050, 1205, 2091, "※ 위 내용은 발급일 현재 상황으로서 발급 당시의 내용입니다.", .98),
             cell(1311, 2112, 1567, 2156, "2026년 3월 3일", .97),
             cell(167, 2169, 408, 2217, "접 수 번 호", .95),
             cell(451, 2170, 707, 2209, "123456789012", 1),
             cell(167, 2235, 407, 2283, "담 당 부 서", .84),
             cell(449, 2234, 631, 2280, "가상민원실", 1),
             cell(1033, 2250, 1561, 2316, "가상합성세무서장", .92),
             cell(162, 2296, 412, 2356, "담 당 자", .94),
             cell(166, 2367, 225, 2415, "연", 1), cell(254, 2369, 329, 2414, "락", .79),
             cell(319, 2366, 410, 2415, "처", .63),
             cell(449, 2369, 707, 2408, "000-000-0000", 1)]
    if multiline:
        cells.extend([cell(637, 1260, 1323, 1300, "|추가합성업", .98),
                      cell(633, 1460, 1380, 1500, "|추가가상품목", .95)])
    if joint_count:
        height = min(45, 200 / joint_count * .6)
        for index in range(joint_count):
            y = 1690 + index * (210 / joint_count)
            cells.extend([cell(867, y, 1047, y + height, "이합성", .99),
                          cell(1445, y, 1740, y + height, "910202-2******", .98)])
    else:
        cells.append(cell(799, 1785, 1137, 1834, "해당사항이 없습니다.", .97))
        if noise:
            # Source-shaped oversized fragments have an unknown purpose.
            cells.extend([cell(867, 1703, 1091, 1796, "합성", .97),
                          cell(1116, 1710, 1198, 1795, "가", .85),
                          cell(1382, 2278, 1569, 2368, "가", .08)])
    if blank_rows:
        cells.append(cell(867, 1898, 1740, 1905, "────", .45))
    return cells, (2065, 2923)


def text_pdf(path, cells, size):
    import pymupdf

    font = pymupdf.Font("cjk")
    with pymupdf.open() as document:
        sheet = document.new_page(width=595, height=842)
        for x0, y0, x1, y1, text, _ in cells:
            width = (x1 - x0) / size[0] * 595
            height = (y1 - y0) / size[1] * 842
            fontsize = min(width / font.text_length(text, fontsize=1), height / (font.ascender - font.descender))
            writer = pymupdf.TextWriter(sheet.rect)
            writer.append((x0 / size[0] * 595, y0 / size[1] * 842 + font.ascender * fontsize),
                          text, font=font, fontsize=fontsize)
            writer.write_text(sheet)
        document.save(path)
    return path

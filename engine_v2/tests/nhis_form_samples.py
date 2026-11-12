"""Authored NHIS acquisition-loss cells; all values are conspicuously fictitious."""
from engine_v2.pipeline.ocr import OcrResult, OcrWord
from engine_v2.pipeline.preprocess import PageImage, PageSource

NAME = "가짜이름"
BIRTH = "1990-01-01"
ISSUE = "2026-03-03"


def acquisition_cells(*, name=NAME):
    cells = [(5, 4, "1 / 1"), (10, 8, "발급번호 : G000000000000000000"),
             (25, 12, "건강보험자격득실확인서"), (10, 19, "확인청구자"),
             (28, 18, "성명"), (55, 18, "주 민 등 록 번 호"),
             (55, 22, "900101-1******"), (25, 27, "자 격 득 실 확 인 내 역"),
             (7, 32, "No"), (15, 32, "가입자구분"), (33, 32, "사업장명칭"),
             (65, 32, "자격취득일"), (81, 32, "자격상실일"),
             (15, 68, "건강보험 자격득실내역을 위와 같이 확인합니다."),
             (43, 72, "2026.03.03"), (30, 76, "국민건강보험공단 이사장")]
    if name:
        cells.append((28, 22, name))
    # Deliberately append history after the footer in text insertion order.
    cells += [(7, 37, "1"), (15, 37, "직장가입자"), (33, 37, "가짜상사 (FAKE,Corp)"),
              (65, 37, "2024.01.01"), (7, 42, "2"), (15, 42, "지역세대주"),
              (65, 42, "2020.01.01"), (81, 42, "2024.01.01"),
              (7, 47, "3"), (15, 47, "직장피부양자"), (33, 47, "가짜센터(가짜사업부)"),
              (65, 47, "2010.01.01"), (81, 47, "2020.01.01"),
              (15, 52, "----------"), (33, 52, "이하여백"),
              (65, 52, "----------"), (81, 52, "----------")]
    return cells


def coordinate_page(cells=None, *, name=NAME):
    cells = acquisition_cells(name=name) if cells is None else cells
    words = [OcrWord(t, .99, (x * 10, y * 14, (x + len(t) * .8) * 10, (y + .8) * 14))
             for x, y, t in cells]
    page = PageImage(0, PageSource.TEXT_LAYER, (595, 842), pixel_size=(1000, 1400), dpi=250)
    return page, OcrResult("synthetic", words)


def text_pdf(path, cells=None, *, name=NAME):
    import pymupdf
    cells = acquisition_cells(name=name) if cells is None else cells
    with pymupdf.open() as document:
        page = document.new_page(width=595, height=842)
        font = pymupdf.Font("cjk")
        for x, y, text in cells:
            writer = pymupdf.TextWriter(page.rect)
            writer.append((x * 5.95, y * 8.42), text, font=font, fontsize=8)
            writer.write_text(page)
        document.save(path)
    return path


def qualification_cells():
    """Authored notification form; request and expiry dates differ from issuance."""
    return [(5, 4, "1 / 1"), (24, 10, "건강보험 자격확인(통보)서"),
            (10, 14, "통보번호 : 0-0000-20260301-000000"),
            (10, 19, "수신기관명"), (30, 19, "요양기관용"),
            (57, 19, "자격확인요청일"), (78, 19, "2026.03.01"),
            (10, 23, "증 번 호"), (30, 23, "00000000000"),
            (57, 23, "사업장관리번호"), (78, 23, "00000000000"),
            (10, 29, "가 입 자"), (10, 31, "(세대주)"),
            (29, 28, "성명"), (55, 28, "주 민 등 록 번 호"),
            (29, 32, NAME), (55, 32, "900101-1******"),
            (30, 38, "자 격 확 인 내 역"), (10, 43, "성 명"),
            (27, 43, "주민등록번호"), (49, 43, "자격취득일"),
            (65, 43, "자격상실일"), (80, 43, "급여정지사유 및 기간"),
            (20, 68, "이와같이 건강보험자격을 확인합니다."),
            (42, 72, "2026.03.03"), (30, 76, "국민건강보험공단 이사장"),
            (28, 81, "2026.04.03 까지 유효합니다."),
            (10, 86, "※ 합성 문서 안내 1"), (10, 89, "※ 합성 문서 안내 2"),
            (10, 47, NAME), (27, 47, "900101-1******"), (49, 47, "2020.01.01"),
            (10, 51, "가짜가족"), (27, 51, "010101-3******"), (49, 51, "2021.01.01"),
            (10, 55, "----------"), (27, 55, "----------"), (49, 55, "이하여백"),
            (65, 55, "----------"), (80, 55, "----------")]


def insurance_portal_cells():
    """Authored portal form; every identifier/workplace/person is fictitious."""
    cells = [(65, 5, "출력일시 : 2026.03.04 09:30"), (15, 13, "4대 사회보험"),
             (14, 16, "가입자 가입내역 확인서"), (10, 16, "확인용"),
             (10, 21, "발 급 번 호"), (30, 21, "00000000000000"),
             (58, 21, "발 급 일 시"), (74, 21, "2026-03-03 10:20"),
             (10, 25, "주민(외국인)등록번호"), (34, 25, "900101-1******"),
             (60, 25, "성명"), (80, 25, NAME),
             (10, 29, "■ 가입 내역(발급일자 현재기준)"), (87, 29, "1 / 1"),
             (10, 31, "내역/구분"), (23, 31, "성명"), (34, 31, "가입자종별"),
             (48, 31, "사업장"), (48, 32, "관리번호"), (65, 31, "사업장명칭"),
             (82, 31, "자격취득일"), (82, 32, "(신고접수일)"), (10, 57, "▷ 합성 안내")]
    for y, insurance, category in [(36, "국민연금", "사업장가입자"), (40, "건강보험", "직장가입자"),
                                    (44, "산재보험", "직장가입자"), (48, "고용보험", "직장가입자")]:
        cells += [(9, y, insurance), (23, y, NAME), (34, y, category),
                  (48, y, "00000000000"),
                  (65, y, "가짜상사 가짜" if y % 8 == 4 else "가짜상사가짜"),
                  (82, y, "2020.01.01"), (82, y + 1, "(2020.01.02)")]
    for y, insurance in [(64, "국민연금"), (69, "건강보험"), (74, "산재보험"), (79, "고용보험")]:
        cells.append((12, y, f"위와 같이 {insurance} 가입내역을 확인합니다."))
    return cells

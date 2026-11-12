"""Fictitious word boxes modeled on redacted layout shapes, without PDF rules."""
import random

from engine_v2.pipeline.ocr import OcrResult, OcrWord
from engine_v2.pipeline.preprocess import PageImage, PageSource

NAME = "가상인"
BIRTH = "1990-01-01"
ISSUE = "2026-03-03"


def word(x, y, width, text, height=12):
    return (x, y, x + width, y + height, text)


def spaced(x, y, text, *, size=12, step=18):
    return [word(x + i * step, y, size, char, size) for i, char in enumerate(text)]


def page(cells, *, jitter=0, seed=7, image=False, size=(595, 842), scale=1):
    rng = random.Random(seed)
    words = []
    for x0, y0, x1, y1, text in cells:
        dx, dy = rng.uniform(-jitter, jitter), rng.uniform(-jitter, jitter)
        words.append(OcrWord(text, .99, tuple(v * scale for v in (x0 + dx, y0 + dy, x1 + dx, y1 + dy))))
    return (PageImage(0, PageSource.UPLOAD if image else PageSource.TEXT_LAYER,
                      size, pixel_size=tuple(v * scale for v in size), dpi=72 * scale), OcrResult("synthetic", words))


def acquisition(*, name=NAME, count=9, long=False):
    cells = [word(55, 55, 5, "1", 10), word(65, 55, 5, "/", 10), word(75, 55, 5, "1", 10),
             word(51, 80, 48, "발급번호"), word(105, 80, 6, ":"),
             word(123, 80, 114, "G" + "0" * 18),
             word(189, 104, 220, "건강보험자격득실확인서", 20),
             word(187, 143, 24, "성명"), word(48, 159, 60, "확인청구자"),
             word(378, 174, 84, "900101-1******"),
             *spaced(369, 143, "주민등록번호"), *spaced(218, 205, "자격득실확인내역", size=14, step=21)]
    if name:
        cells.append(word(199 - 6 * len(name), 174, 12 * len(name), name))
    for x, width, text in [(43, 12, "No"), (78, 60, "가입자구분"), (233, 60, "사업장명칭"),
                           (392, 60, "자격취득일"), (487, 60, "자격상실일")]:
        cells.append(word(x, 237, width, text))
    for i in range(count):
        y = 268 + 31 * i
        cells += [word(47, y, 5 * len(str(i + 1)), str(i + 1), 10),
                  word(63, y, 60 if i == 5 else 50, "직장피부양자" if i == 5 else
                       ("직장가입자" if i % 2 == 0 else "지역세대주"), 10),
                  word(397, y, 50, f"{2024 - i * 3}.01.01", 10)]
        if i:
            cells.append(word(492, y, 50, f"{2027 - i * 3}.01.01", 10))
        if i % 2 == 0:
            cells += [word(157, y, 40, "가상회사", 10), word(202, y, 20, "센터", 10)]
        if long and i == 5:
            cells.append(word(157, y, 210, "가상기업연구소(가상긴사업부)", 10))
    y = 268 + 31 * count
    cells += [word(63, y, 50, "----------", 10), word(157, y, 40, "이하여백", 10),
              word(397, y, 50, "----------", 10), word(492, y, 50, "----------", 10),
              word(78, y + 49, 48, "건강보험"), word(132, y + 49, 84, "자격득실내역을"),
              word(222, y + 49, 24, "위와"), word(252, y + 49, 24, "같이"),
              word(282, y + 49, 66, "확인합니다."), word(266, y + 75, 60, "2026.03.03"),
              word(181, y + 118, 160, "국민건강보험공단", 20), word(351, y + 118, 60, "이사장", 20)]
    return cells


def qualification(*, name=NAME, count=2):
    cells = [word(55, 55, 5, "1", 10), word(65, 55, 5, "/", 10), word(75, 55, 5, "1", 10),
             word(173, 89, 80, "건강보험", 20), word(263, 89, 160, "자격확인(통보)서", 20),
             word(45, 133, 48, "통보번호"), word(99, 133, 6, ":"),
             word(111, 133, 132, "0-0000-20260301-000000"),
             word(51, 163, 55, "수신기관명", 11), word(162, 163, 55, "가상기관용", 11),
             word(283, 163, 77, "자격확인요청일", 11), word(443, 163, 55, "2026.03.01", 11),
             *spaced(57, 199, "증번호", size=11, step=16.5), word(159, 199, 61, "00000000000", 11),
             word(283, 199, 77, "사업장관리번호", 11), word(440, 199, 60, "00000000000", 11),
             word(178, 233, 22, "성명", 11), *spaced(364, 233, "주민등록번호", size=11, step=16.5),
             *spaced(57, 242, "가입자", size=11, step=16.5), word(57, 257, 44, "(세대주)", 11),
             word(372, 265, 77, "900101-1******", 11), *spaced(238, 298, "자격확인내역", size=14, step=21),
             word(47, 330, 11, "성", 11), word(75, 330, 11, "명", 11),
             word(121, 330, 66, "주민등록번호", 11), word(229, 330, 55, "자격취득일", 11),
             word(313, 330, 55, "자격상실일", 11), word(415, 330, 66, "급여정지사유", 11),
             word(487, 330, 11, "및", 11), word(503, 330, 22, "기간", 11)]
    if name:
        cells.append(word(189.5 - 5.5 * len(name), 265, 11 * len(name), name, 11))
    for i in range(count):
        y = 358 + 28 * i
        value = (name or NAME) if i == 0 else "가상원"
        cells += [word(39, y, 10 * len(value), value, 10),
                  word(98, y, 70, "900101-1******" if i == 0 else "010101-3******", 10),
                  word(231, y, 50, "2020.01.01", 10)]
    y = 358 + 28 * count
    cells += [word(39, y, 40, "--------", 10), word(98, y, 70, "--------------", 10),
              word(236, y, 40, "이하여백", 10), word(308, y, 65, "-------------", 10),
              word(383, y, 150, "------------------------------", 10),
              word(69, 633, 48, "이와같이"), word(123, 633, 84, "건강보험자격을"),
              word(213, 633, 66, "확인합니다."), word(268, 656, 60, "2026.03.03"),
              word(183, 687, 160, "국민건강보험공단", 20), word(353, 687, 60, "이사장", 20),
              word(67, 723, 55, "2026.04.03", 11), word(126, 723, 22, "까지", 11),
              word(154, 723, 60, "유효합니다.", 11)]
    return cells


def portal(*, name=NAME, long=False):
    cells = [word(425, 82, 45, "출력일시:"), word(474, 82, 52, "2026.03.04"), word(529, 82, 26, "09:30"),
             word(244, 113, 103, "4대사회보험", 21), word(192, 141, 207, "가입자가입내역확인서", 23),
             word(48, 163, 28, "확인용", 11), word(77, 184, 46, "발 급 번 호", 11),
             word(189, 184, 85, "00000000000000", 11), word(340, 184, 46, "발급일시", 11),
             word(452, 184, 56, "2026-03-03", 11), word(511, 184, 27, "10:20", 11),
             word(54, 212, 92, "주민(외국인)등록번호"), word(195, 212, 82, "900101-1******"),
             word(358, 212, 19, "성명"), word(485, 212, 10 * len(name), name),
             word(42, 242, 141, "■가입내역(발급일자현재기준)"),
             word(513, 242, 6, "1"), word(530, 242, 3, "/"), word(541, 242, 6, "1"),
             word(77, 270, 19, "내역"), word(58, 281, 19, "구분"), word(137, 276, 20, "성명", 11),
             word(201, 276, 48, "가입자종별", 11), word(291, 270, 29, "사업장"),
             word(286, 281, 39, "관리번호"), word(388, 276, 48, "사업장명칭", 11),
             word(493, 267, 48, "자격취득일"), word(489, 284, 56, "(신고접수일)", 11)]
    for i, insurance in enumerate(("국민연금", "건강보험", "산재보험", "고용보험")):
        y = 310 + 34 * i
        cells += [word(491, y - 9, 53, "2020.01.01"), word(57, y, 39, insurance, 11),
                  word(132, y, 10 * len(name), name, 11),
                  word(196 if i != 1 else 201, y, 58 if i != 1 else 48,
                       "사업장가입자" if i == 0 else "직장가입자", 11),
                  word(273, y, 65, "00000000000", 11),
                  word(370 if long else 381, y, 90 if long else 61, "가상기업연구센터" if long else "가상회사센터", 11),
                  word(488, y + 8, 59, "(2020.01.02)", 11)]
    cells += [word(41, 449, 346, "▷가상안내문", 11), word(58, 604, 83, "위와같이가입내역을", 11),
              word(48, 614, 104, "확인합니다.", 11), word(188, 637, 86, "국민건강보험공단"),
              word(209, 649, 44, "이사장", 13)]
    return cells


def resident(*, kind='초본', opening='', prior=False, combined=False, main=True, subtitle=True):
    """Title boxes preserve the two OCR layouts and interleaved side notice."""
    cells = [word(376, 97, 645, '문서확인번호:0000-0000-0000-0000', 36),
             word(996, 150, 619, '가상 안내 문구입니다', 58),
             word(956, 182, 179, '가상 안내문', 54),
             word(958, 231, 123, '가상라벨:', 49),
             word(961, 278, 209, '가상인:가상인', 43),
             word(960, 321, 212, '가상 신청인 안내', 47),
             word(1347, 423, 561, '가상 발급기관', 53),
             word(190, 510, 192, '성 명(한자)', 51), word(471, 509, 111, NAME, 51),
             word(1124, 511, 208, '주민등록번호', 47), word(1422, 516, 240, '900101-1******', 35)]
    # Insert side-notice words between title tokens, like OCR reading order.
    if main:
        cells.insert(2, word(309 if prior else 292, 204 if prior else 207, 559 if prior else 556,
                             '주 민 등 록 표', 85 if prior else 82))
    if subtitle:
        x, y = (420, 290) if prior else (403, 300)
        if opening:
            cells.append(word(320, y, 50, opening, 58))
        cells += [word(x, y, 65, kind[0], 52), word(689 if prior else 671, 284 if prior else 294,
                                                                   75 if prior else 70, kind[1], 69),
                  word(829 if prior else 804, 291 if prior else 305, 42 if prior else 29, ')', 50)]
        if combined:
            cells.append(word(500, 380, 200, '등 본', 65))
    cells += [word(200, 900 + i * 60, 600, '가상 본문 자료 안내', 40) for i in range(20)]
    cells.append(word(207, 2502, 1684, '주민등록표 등·초본상 가상 안내문', 32))
    return cells

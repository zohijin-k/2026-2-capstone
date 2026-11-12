"""Authored fictitious values with query-note and notice wording from form labels."""
from engine_v2.pipeline.ocr import OcrWord
from engine_v2.tests.followup_daily_samples import daily_short_birth


def daily_notices(*, total=9, selected=9):
    pages = daily_short_birth()
    for page, result in pages:
        if page.page % 2 == 0:
            result.words[:] = [w for w in result.words if not w.text.startswith("[√]")
                              and "이하 여백" not in w.text]
            result.words += [OcrWord("산재보험", 1, (224,50,290,71)),
                             OcrWord("고용보험", 1, (314,50,380,71))]
            for word in result.words:
                if "합성시험용 가짜 안내문" in word.text:
                    word.text = f"(조회기간 총 {total}개 이력 중 {selected}개 이력 선택 발급 요청)"
        else:
            result.words[:] = [w for w in result.words if "확인합니다" not in w.text]
            result.words += [
                OcrWord("※", 1, (46,58,55,70)),
                OcrWord("가짜 시험용 안내문입니다. 실제 서류가 아닙니다.", 1, (57,58,447,70)),
                OcrWord("-", 1, (46,102,52,114)),
                OcrWord("이 증명원은 근로복지공단 방문 없이 가짜 시험 안내를 확인합니다.", 1, (54,102,535,114)),
                OcrWord("가짜 안내를 확인할 수 있습니다.(합성시험용)", 1, (53,113,416,125)),
                OcrWord("-", 1, (46,124,52,136)),
                OcrWord("발급증명원은 근로복지공단 홈페이지 가짜 시험 안내를 이용합니다.", 1, (54,124,546,136)),
                OcrWord("위와같이자격내역을알려드립니다.", 1, (220,162,375,174)),
            ]
    return pages

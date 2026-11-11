"""OCR 결과의 '줄 구조'를 개인정보 없이 보여준다 — 추출 규칙 설계용.

  python -m engine_v2.tools.layout_dump engine_v2/data/private/초본.pdf --engine applevision

양식 라벨(성명, 주소, 발생일, 신고일, 변동사유 ...)은 그대로 두고 나머지는 가린다.

출력은 팀 공유 가능. 단, 공유 전에 한 번 훑어서 가려지지 않은 개인정보가 없는지 확인할 것.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ..pipeline.ocr import OcrWord, run_ocr
from ..pipeline.preprocess import PageSource, preprocess
from .privacy import mask_text

# 양식에 고정으로 찍히는 문구만. 개인을 특정할 수 있는 단어(시군·동 이름 등)는 넣지 않는다.
LABELS = sorted({
    "주민등록표", "초본", "등본", "성명", "주민등록번호", "주소", "발생일", "신고일",
    "변동사유", "전입", "전출", "세대주", "관계", "본인", "번호", "발급", "발급일",
    "발급번호", "문서확인번호", "시장", "군수", "구청장", "읍장", "면장", "동장", "직인",
    "개인", "인적사항", "변경", "내용", "변동", "사항", "정정", "말소", "재등록", "병역",
    "이하", "여백", "페이지", "쪽", "년", "월", "일", "용도", "제출처", "확인", "증명",
    "전라북도", "전북특별자치도", "특별자치도", "광역시", "특별시",
    "주민등록법", "제29조", "에", "의하여", "위", "와", "같이", "합니다",
    "4대", "4대사회보험", "사회보험", "가입자", "가입내역", "국민연금", "건강보험",
    "고용보험", "산재보험", "사업장", "명칭", "관리번호", "구분", "자격", "취득일",
    "상실일", "미가입", "해당없음", "지역", "직장", "외국인", "등록번호", "발급번호",
    "발급일시", "현재", "기준", "국민연금공단", "국민건강보험공단", "건강보험공단",
    "근로복지공단", "고용노동부",
}, key=len, reverse=True)


def mask(text: str) -> str:
    return mask_text(text, labels=LABELS)


def group_lines(words: list[OcrWord], tol: float = 0.6) -> list[list[OcrWord]]:
    """세로 중심이 글자 높이의 tol배 이내면 같은 줄."""
    ws = sorted(words, key=lambda w: (w.bbox_px[1] + w.bbox_px[3]) / 2)
    lines: list[list[OcrWord]] = []
    for w in ws:
        cy = (w.bbox_px[1] + w.bbox_px[3]) / 2
        h = w.bbox_px[3] - w.bbox_px[1]
        if lines:
            last = lines[-1]
            ly = sum((x.bbox_px[1] + x.bbox_px[3]) / 2 for x in last) / len(last)
            if abs(cy - ly) <= h * tol:
                last.append(w)
                continue
        lines.append([w])
    return [sorted(l, key=lambda w: w.bbox_px[0]) for l in lines]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("file", type=Path)
    ap.add_argument("--engine", default="applevision")
    args = ap.parse_args()

    for p in preprocess(args.file):
        if p.source == PageSource.TEXT_LAYER:
            continue
        r = run_ocr(args.engine, p.png, p.pixel_size)
        if r.error:
            raise SystemExit(mask_text(r.error))
        W, H = p.pixel_size
        print(f"\n===== page {p.page}  ({W}x{H}px) =====")
        print(" y%  | x%  단어들 (마스킹)                                   | conf")
        for line in group_lines(r.words):
            y = (line[0].bbox_px[1] / H) * 100
            cells = "  ".join(f"[{w.bbox_px[0] / W * 100:4.1f}]{mask(w.text)}" for w in line)
            confs = ",".join(f"{w.confidence:.1f}" for w in line)
            print(f"{y:4.1f} | {cells} | {confs}")


if __name__ == "__main__":
    main()

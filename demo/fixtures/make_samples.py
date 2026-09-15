"""시연용 더미 서류 생성기.

저장소 루트에서:
    python -m demo.fixtures.make_samples

`demo/backend/ocr/fixture.py`의 FIXTURES 키와 같은 이름으로 더미 PDF를 만들어
`demo/fixtures/samples/`에 떨군다. 이 파일들을 업로드 화면에 끌어다 놓으면
시나리오 S2~S12가 그대로 재현된다.

**실제 개인정보나 실물 서류는 쓰지 않는다.** 내용은 서류 문구를 흉내낸 더미이고,
생성물은 저장소에 커밋하지 않는다(루트 .gitignore).
"""

from pathlib import Path

from ..backend.ocr.fixture import FIXTURES

OUT_DIR = Path(__file__).resolve().parent / "samples"

#: 파일명 키워드 → 본문에 넣을 더미 문구.
#: Tier1이 파일명으로 먼저 잡으므로 본문은 사람이 열어봤을 때의 설명용이다.
BODY_HINTS: list[tuple[str, list[str]]] = [
    ("주민등록등본", ["주민등록표 등본", "성명 : 홍길동", "세대주 및 관계 : 본인"]),
    ("주민등록초본", ["주민등록표 초본", "성명 : 홍길동", "주소변동 사항", "발급일자 : 2026년 3월 5일"]),
    ("건강보험료납부확인서", ["건강보험료 납부확인서", "성명 : 홍길동", "고지금액 : 200,000"]),
    ("건강보험자격득실확인서", ["건강보험 자격득실확인서", "성명 : 홍길동"]),
    ("건강보험자격확인서", ["건강보험 자격확인서", "성명 : 홍길동", "세대원수 : 4"]),
    ("4대보험가입내역확인서", ["4대보험 가입내역 확인서", "성명 : 홍길동"]),
    # --- 취업지원패키지 추가서류 ---
    ("면접확인서", ["면접확인서", "성명 : 홍길동", "면접일 : 2026년 4월 2일", "발급일자 : 2026년 4월 2일"]),
    (
        "응시확인서_응시일없음",
        ["응시확인서", "성명 : 홍길동", "자격종목 : 정보처리기사", "※ 응시일 표기 없음"],
    ),
    ("응시확인서", ["응시확인서", "성명 : 홍길동", "자격종목 : 정보처리기사", "응시일 : 2026년 3월 22일"]),
    ("성적표", ["성적표", "성명 : 홍길동", "자격종목 : 정보처리기사", "응시일 : 2026년 3월 22일"]),
    ("결제영수증", ["결제영수증", "품목 : 면접정장 대여", "결제금액 : 70,000", "결제일 : 2026년 4월 1일"]),
    ("면접용사진사본", ["면접용 증명사진 사본", "성명 : 홍길동"]),
]


def _body(stem: str) -> list[str]:
    for keyword, lines in BODY_HINTS:
        if keyword in stem:
            return _fill_amount(stem, lines) + [
                "",
                "※ 시연용 더미 문서입니다. 실제 서류가 아닙니다.",
            ]
    return [stem, "", "※ 시연용 더미 문서입니다. 실제 서류가 아닙니다."]


def _fill_amount(stem: str, lines: list[str]) -> list[str]:
    """파일명 끝의 금액(S10_결제영수증_정장70000)을 본문 금액과 맞춘다.

    Tier1 fixture가 파일명으로 먼저 잡으므로 판정에는 영향이 없지만, 사람이 파일을
    열어봤을 때 본문과 판독 결과가 다르면 시연 중에 설명이 꼬인다.
    """
    digits = "".join(c for c in stem.rsplit("_", 1)[-1] if c.isdigit())
    if not digits or "결제금액" not in " ".join(lines):
        return lines
    amount = f"{int(digits):,}"
    return [
        f"결제금액 : {amount}" if line.startswith("결제금액") else line for line in lines
    ]


def make(stem: str, out_dir: Path) -> Path:
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    writer = fitz.TextWriter(page.rect)
    font = fitz.Font("cjk")
    y = 90.0
    for line in _body(stem):
        if line:
            writer.append((60, y), line, font=font, fontsize=12)
        y += 26
    writer.write_text(page)

    target = out_dir / f"{stem}.pdf"
    if "암호" in stem:
        # S6 재현: 사용자 암호가 걸린 PDF.
        doc.save(target, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="1234")
    else:
        doc.save(target)
    doc.close()
    return target


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stem in sorted(FIXTURES):
        path = make(stem, OUT_DIR)
        print(f"  {path.name}")
    print(f"\n{len(FIXTURES)}개 생성 → {OUT_DIR}")


if __name__ == "__main__":
    main()

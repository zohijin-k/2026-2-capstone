"""정답 파일 만들기 — 질문에 답하면 data/private/초본.gt.json 을 만든다.

  python -m tools.make_gt

초본 이미지(data/private/초본_p0.png)를 옆에 열어두고, 보이는 그대로 입력하면 된다.
모르는 항목은 그냥 엔터로 건너뛰면 된다. 파일은 본인 PC에만 저장된다.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

OUT = Path("data/private/초본.gt.json")


def ask_date(prompt: str) -> str | None:
    while True:
        raw = input(prompt).strip()
        if not raw:
            return None
        nums = re.findall(r"\d+", raw)  # 2026.11.10 / 2026-11-10 / 2026년 11월 10일 모두 허용
        if len(nums) == 3:
            try:
                return date(int(nums[0]), int(nums[1]), int(nums[2])).isoformat()
            except ValueError:
                pass
        print("  날짜를 못 알아들었어요. 예: 2026.11.10")


def main() -> None:
    print("초본 이미지를 옆에 열어두고 보이는 그대로 입력하세요. 모르면 엔터로 건너뛰기.\n")
    gt: dict = {}

    name = input("1) 성명 (초본 위쪽 '성명' 칸, 예: 홍길동): ").strip()
    if name:
        gt["name"] = name

    if d := ask_date("2) 생년월일 (주민번호 앞 6자리를 날짜로, 예: 990101 → 1999.01.01): "):
        gt["birth_date"] = d

    if d := ask_date("3) 발급일 (보통 마지막 쪽 아래, 시장/구청장 직인 근처 날짜): "):
        gt["issue_date"] = d

    print("4) 현재 주소에 들어 있는 지역 이름을 하나씩 (예: 전주시 → 엔터 → 완산구 → 엔터, 끝나면 빈 엔터)")
    parts = []
    while part := input("   지역 이름: ").strip():
        parts.append(part)
    if parts:
        gt["address_contains"] = parts

    print("5) 주소 이력 표에 있는 날짜들 (전입일·신고일 등, 2~3개면 충분. 끝나면 빈 엔터)")
    moves = []
    while d := ask_date("   날짜: "):
        moves.append(d)
    if moves:
        gt["move_in_dates"] = moves

    if not gt:
        print("\n입력한 게 없어서 파일을 만들지 않았어요.")
        return

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(gt, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장: {OUT}  (항목 {len(gt)}개, 커밋 금지)")
    print("다음: python -m tools.ocr_bench data/private/초본.pdf --engines applevision --gt", OUT)


if __name__ == "__main__":
    main()

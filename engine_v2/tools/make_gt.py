"""정답 파일 만들기 — 입력한 실제 값은 engine_v2/data/private/ 아래에만 저장한다.

  python -m engine_v2.tools.make_gt --doc resident_abstract
  python -m engine_v2.tools.make_gt --doc nhis_payment
  python -m engine_v2.tools.make_gt --doc nhis_acquisition_loss

초본 이미지(data/private/초본_p0.png)를 옆에 열어두고, 보이는 그대로 입력하면 된다.
모르는 항목은 그냥 엔터로 건너뛰면 된다. 파일은 본인 PC에만 저장된다.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path

from ..paths import PRIVATE_DIR

OUT = PRIVATE_DIR / "초본.gt.json"
DOCS = {"resident_abstract", "nhis_payment", "nhis_acquisition_loss"}


def ask_amount(prompt: str) -> str | None:
    while True:
        raw = input(prompt).strip()
        if not raw:
            return None
        digits = re.sub(r"[,\s원]", "", raw)
        if re.fullmatch(r"-?\d+", digits):
            return str(int(digits))
        print("  금액을 숫자로 입력해 주세요.")


def ask_date(prompt: str) -> str | None:
    while True:
        raw = input(prompt).strip()
        if not raw:
            return None
        compact = re.fullmatch(r"(20\d{2})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])", raw)
        if compact:
            try:
                return date(*(int(part) for part in compact.groups())).isoformat()
            except ValueError:
                pass
        nums = re.findall(r"\d+", raw)  # 2026.11.10 / 2026-11-10 / 2026년 11월 10일 모두 허용
        if len(nums) == 3:
            try:
                return date(int(nums[0]), int(nums[1]), int(nums[2])).isoformat()
            except ValueError:
                pass
        print("  날짜를 못 알아들었어요. 예: 2026.11.10")


def _resident_gt() -> dict:
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
    return gt


def _payment_gt() -> dict:
    print("납부확인서를 보고 정답을 입력하세요. 모르면 엔터로 건너뛰기.\n")
    gt: dict = {}
    for field, prompt in (("name", "1) 성명: "), ("birth_date", "2) 생년월일: "),
                          ("issue_date", "3) 발급일: ")):
        value = input(prompt).strip() if field == "name" else ask_date(prompt)
        if value:
            gt[field] = value
    insurance = input("4) 가입구분 (직장/지역): ").strip()
    if insurance in ("직장", "지역"):
        gt["insurance_type"] = insurance
    billed = {}
    care = {}
    for month in ("2025-10", "2025-11", "2025-12"):
        if value := ask_amount(f"5) {month}월 고지금액 (원): "):
            billed[month] = value
        if value := ask_amount(f"   {month}월 장기요양보험료 (원, 없으면 엔터): "):
            care[month] = value
    if billed:
        gt["billed_by_month"] = billed
    if care:
        gt["long_term_care_by_month"] = care
    return gt


def _acquisition_gt() -> dict:
    print("자격득실확인서를 보고 정답을 입력하세요. 사업장명은 입력하지 않습니다.\n")
    gt: dict = {}
    for field, prompt in (("name", "1) 성명: "), ("birth_date", "2) 생년월일: "),
                          ("issue_date", "3) 발급일: ")):
        value = input(prompt).strip() if field == "name" else ask_date(prompt)
        if value:
            gt[field] = value
    start = ask_date("4) 조회기간 시작일 (없으면 엔터): ")
    end = ask_date("   조회기간 종료일 (없으면 엔터): ")
    if start and end:
        gt["query_period"] = [start, end]
    print("5) 이력 행을 추가하세요. 가입자구분은 직장/지역, 날짜는 모르면 엔터. 빈 구분 입력 시 종료.")
    rows = []
    while category := input("   가입자구분: ").strip():
        if category not in ("직장", "지역"):
            print("  직장 또는 지역으로 입력해 주세요.")
            continue
        acquired = ask_date("   자격취득일: ")
        lost = ask_date("   자격상실일 (없으면 엔터): ")
        rows.append({"category": category, "acquired": acquired, "lost": lost})
    if rows:
        gt["history"] = rows
    included = input("6) 최근 5년 포함 여부 (예/아니오): ").strip()
    if included in ("예", "아니오"):
        gt["recent_five_years"] = included == "예"
    return gt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--doc", choices=sorted(DOCS), default="resident_abstract")
    args = parser.parse_args()
    gt = {"resident_abstract": _resident_gt, "nhis_payment": _payment_gt,
          "nhis_acquisition_loss": _acquisition_gt}[args.doc]()
    out = OUT if args.doc == "resident_abstract" else PRIVATE_DIR / f"{args.doc}.gt.json"

    if not gt:
        print("\n입력한 게 없어서 파일을 만들지 않았어요.")
        return

    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(gt, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n정답 파일 저장 완료 ({len(gt)}개 항목, 커밋 금지)")
    print(f"다음: python -m engine_v2.tools.extract_check <실제파일.pdf> --doc {args.doc} --gt {out}")


if __name__ == "__main__":
    main()

"""정답 파일 만들기 — 입력한 실제 값은 engine_v2/data/private/ 아래에만 저장한다.

  python -m engine_v2.tools.make_gt --doc resident_abstract
  python -m engine_v2.tools.make_gt --doc nhis_payment
  python -m engine_v2.tools.make_gt --doc nhis_acquisition_loss
  python -m engine_v2.tools.make_gt --doc insurance_4
  python -m engine_v2.tools.make_gt --doc receipt            # 취업지원패키지: receipt · exam_admission ·
                                                             #   exam_score · interview_confirm

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
DOCS = {"resident_abstract", "nhis_payment", "nhis_acquisition_loss", "insurance_4",
        "receipt", "exam_admission", "exam_score", "interview_confirm"}


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


def _ask_optional_date(prompt: str) -> str | None:
    while True:
        raw = input(prompt).strip()
        if raw in {"", "-", "–", "—"}:
            return None
        compact = re.fullmatch(r"(20\d{2})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])", raw)
        nums = compact.groups() if compact else re.findall(r"\d+", raw)
        if len(nums) == 3:
            try:
                return date(int(nums[0]), int(nums[1]), int(nums[2])).isoformat()
            except ValueError:
                pass
        print("  날짜를 못 알아들었어요. 예: 2026.11.10 또는 '-'")


def _insurance4_gt() -> dict:
    print("4대 사회보험 가입내역 확인서를 보고 입력하세요. 주민등록번호는 입력하지 않습니다.\n")
    gt: dict = {}
    name = input("1) 성명: ").strip()
    if name:
        gt["name"] = name
    if birth := ask_date("2) 생년월일: "):
        gt["birth_date"] = birth
    if issue := ask_date("3) 발급일: "):
        gt["issue_date"] = issue
    confirmation = input("4) 문서확인번호 (하이픈 포함, 모르면 엔터): ").strip()
    if confirmation:
        gt["document_number"] = confirmation
    print("5) 국민연금·건강보험·산재보험·고용보험 네 행을 모두 입력하세요. 미가입 행도 기록합니다.")
    rows = []
    while insurance := input("   보험 종류 (국민연금/건강보험/산재보험/고용보험, 끝나면 엔터): ").strip():
        if insurance not in ("국민연금", "건강보험", "산재보험", "고용보험"):
            print("  알려진 보험 종류를 입력해 주세요.")
            continue
        status = input("   상태 (가입/미가입): ").strip()
        while status not in {"가입", "미가입"}:
            status = input("   '가입' 또는 '미가입'을 입력해 주세요: ").strip()
        row = {"insurance": insurance, "status": status}
        if row["status"] == "가입":
            row["name"] = input("   성명: ").strip()
            row["subscriber_category"] = input("   가입자종별: ").strip()
            row["management_number"] = input("   사업장관리번호 (없으면 엔터): ").strip()
            row["workplace_name"] = input("   사업장명칭 (없으면 엔터): ").strip()
            row["acquired"] = ask_date("   자격취득일: ")
            row["received"] = _ask_optional_date("   신고접수일 (괄호 안 날짜, 없으면 '-'): ")
        rows.append(row)
    if rows:
        gt["rows"] = rows
    return gt


def _ask_fields(prompts: tuple[tuple[str, str, str], ...]) -> dict:
    """(정답 키, 질문, 종류 text·date·amount)를 차례로 묻는다. 엔터는 건너뛰기."""
    gt: dict = {}
    for key, prompt, kind in prompts:
        if kind == "date":
            value = ask_date(prompt)
        elif kind == "amount":
            value = ask_amount(prompt)
        else:
            value = input(prompt).strip()
        if value:
            gt[key] = value
    return gt


def _receipt_gt() -> dict:
    print("결제영수증을 보고 입력하세요. 카드번호·계좌번호는 입력하지 않습니다.\n")
    return _ask_fields((
        ("amount", "1) 결제금액 (합계, 원): ", "amount"),
        ("payment_date", "2) 결제일 (거래일시의 날짜): ", "date"),
        ("store", "3) 상호·가맹점명 (없으면 엔터): ", "text"),
        ("payee", "4) 받는분 (계좌이체 확인증일 때, 없으면 엔터): ", "text"),
        ("brn", "5) 사업자등록번호 (하이픈 포함, 없으면 엔터): ", "text"),
        ("payment_method", "6) 결제수단 (카드/현금/계좌이체/간편결제): ", "text"),
    ))


def _exam_gt() -> dict:
    print("응시확인서 또는 성적표를 보고 입력하세요.\n")
    return _ask_fields((
        ("name", "1) 성명: ", "text"),
        ("birth_date", "2) 생년월일 (없으면 엔터): ", "date"),
        ("exam_name", "3) 시험명·종목: ", "text"),
        ("exam_date", "4) 응시일 (시험일): ", "date"),
        ("issue_date", "5) 발급일·출력일 (없으면 엔터): ", "date"),
    ))


def _interview_gt() -> dict:
    print("면접확인서를 보고 입력하세요. 주소·연락처·이메일·담당자는 입력하지 않습니다.\n")
    return _ask_fields((
        ("name", "1) 성명: ", "text"),
        ("birth_date", "2) 생년월일: ", "date"),
        ("company", "3) 회사명 (면접기업 칸): ", "text"),
        ("industry", "4) 업태/업종 (없으면 엔터): ", "text"),
        ("interview_date", "5) 면접일: ", "date"),
        ("interview_time", "6) 면접시간 (예: 14:00~14:40, 없으면 엔터): ", "text"),
        ("place", "7) 면접장소 (없으면 엔터): ", "text"),
        ("job", "8) 응시직군 (없으면 엔터): ", "text"),
        ("confirm_date", "9) 확인일 ('확인합니다' 아래 날짜, 없으면 엔터): ", "date"),
    ))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--doc", choices=sorted(DOCS), default="resident_abstract")
    args = parser.parse_args()
    gt = {"resident_abstract": _resident_gt, "nhis_payment": _payment_gt,
          "nhis_acquisition_loss": _acquisition_gt, "insurance_4": _insurance4_gt,
          "receipt": _receipt_gt, "exam_admission": _exam_gt, "exam_score": _exam_gt,
          "interview_confirm": _interview_gt}[args.doc]()
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

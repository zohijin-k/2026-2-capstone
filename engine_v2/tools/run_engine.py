"""실제 서류로 엔진 전체 실행 — 본인 PC에서.

  python -m tools.run_engine data/private/초본.pdf --input data/private/초본.gt.json
  python -m tools.run_engine data/private/초본.pdf --input data/private/초본.gt.json --issue-date 2026-11-09   # 일부러 틀리게

--input: 신청자 입력값으로 쓸 JSON (make_gt로 만든 정답 파일을 그대로 써도 됨: name, birth_date, issue_date)
출력: 신청자용 결과 + 규칙별 통과/실패 (값 없음, 공유 가능)
저장: data/private/result_reviewer.json — 담당자용 전체 결과 (값 포함, 공유 금지)
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from engine import run
from extractors.resident_abstract import kst_today
from schemas.models import ApplicantInput, ApplicationInput, DocType, DocumentInput


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("file", type=Path)
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--announce", type=date.fromisoformat, default=None, help="공고일 (기본: 오늘)")
    ap.add_argument("--issue-date", help="신청자가 입력한 발급일을 덮어쓰기 (오류 시나리오 확인용)")
    ap.add_argument("--name", help="신청자 성명 덮어쓰기 (오류 시나리오 확인용)")
    ap.add_argument("--engine", default="applevision")
    args = ap.parse_args()

    for p in (args.file, args.input):
        if not p.exists():
            raise SystemExit(f"파일이 없어요: {p}")
    gt = json.loads(args.input.read_text(encoding="utf-8"))

    app = ApplicationInput(
        application_id="LOCAL-TEST",
        program_id="doubling_savings",
        announcement_date=args.announce or kst_today(),
        applicant=ApplicantInput(name=args.name or gt["name"], birth_date=gt["birth_date"]),
        documents=[DocumentInput(
            doc_id="abstract-1", declared_type=DocType.RESIDENT_ABSTRACT, file_path=str(args.file),
            declared_values={"issue_date": args.issue_date or gt["issue_date"]})],
    )
    result = run(app, ocr_engine=args.engine)

    print("=== 신청자에게 보이는 결과 ===")
    print(result.to_applicant_view().model_dump_json(indent=2))

    print("\n=== 담당자용 규칙 결과 (값 생략) ===")
    for d in result.documents:
        print(f"[{d.doc_id}] 판정: {d.verdict.value}  (감지: {d.detected_type.value})")
        for c in d.checks:
            print(f"  {c.status.value:7s} {c.rule_id}")
        for r in d.review_reasons:
            print(f"  검토사유: {r}")
    print(f"\n신청 최종: {result.status.value}")

    out = Path("data/private/result_reviewer.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    print(f"담당자용 전체 결과: {out} (공유 금지)")


if __name__ == "__main__":
    main()

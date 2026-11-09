"""실제 초본에 추출기를 돌려 정답과 비교 — 본인 PC에서 실행.

  python -m engine_v2.tools.extract_check engine_v2/data/private/초본.pdf --gt engine_v2/data/private/초본.gt.json

출력은 값 대신 맞음/틀림, 검증 통과 여부, 이력 구조(시도·사유)만 보여준다 → 팀 공유 가능.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from ..extractors.resident_abstract import extract, kst_today, months_between, resolved_sido, trailing_residence_start
from ..pipeline.ocr import run_ocr
from ..pipeline.preprocess import PageSource, preprocess


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("file", type=Path)
    ap.add_argument("--gt", type=Path)
    ap.add_argument("--engine", default="applevision")
    args = ap.parse_args()

    if not args.file.exists():
        raise SystemExit(f"서류 파일이 없어요: {args.file}  → engine_v2/data/private/ 에 PDF를 넣어주세요")
    if args.gt and not args.gt.exists():
        raise SystemExit(f"정답 파일이 없어요: {args.gt}  → python -m engine_v2.tools.make_gt 로 만들거나 --gt 없이 실행하세요")

    pages = []
    for p in preprocess(args.file):
        if p.source == PageSource.TEXT_LAYER:
            continue
        r = run_ocr(args.engine, p.png, p.pixel_size)
        if r.error:
            raise SystemExit(r.error)
        pages.append((p, r))

    res = extract(pages)
    gt = json.loads(args.gt.read_text(encoding="utf-8")) if args.gt else {}

    print(f"서류 판별: {res.detected_type.value} ({res.type_confidence})")
    for w in res.warnings:
        print(f"  경고: {w}")

    print("\n[필드]  추출됨 / 신뢰도 / 정답 일치")
    def cmp(key, f):
        if key == "name" and "name" in gt:
            return f.value == gt["name"].replace(" ", "")
        if key in ("birth_date", "issue_date") and key in gt:
            return f.value == date.fromisoformat(gt[key])
        if key == "current_address" and "address_contains" in gt:
            return all(a.replace(" ", "") in f.value.replace(" ", "") for a in gt["address_contains"])
        return None
    for key, f in res.fields.items():
        if key == "address_history":
            continue
        ok = cmp(key, f)
        mark = "-" if ok is None else ("O" if ok else "X")
        print(f"  {key:16s} 있음  {f.confidence:.2f}  {mark}")

    print("\n[검증]")
    for v in res.validations:
        print(f"  {'통과' if v.passed else '실패'}  {v.name}  {v.detail}")

    print(f"\n[주소 이력] {len(res.history)}건 (시도 / 사유 / 발생일 유무 / 메모 수)")
    for i, e in enumerate(res.history):
        print(f"  {e.no!s:>3}  {resolved_sido(res.history, i) or '?':4s}  "
              f"{' '.join(e.reason) or '-':10s}  발생일{'O' if e.occurred else 'X'}  메모{len(e.notes)}")

    if gt.get("move_in_dates"):
        found = {d for e in res.history for d in (e.occurred, e.reported) if d}
        hits = [date.fromisoformat(d) in found for d in gt["move_in_dates"]]
        print(f"\n정답 이력 날짜 일치: {sum(hits)}/{len(hits)}")

    start = trailing_residence_start(res.history, "전북")
    if start:
        print(f"전북 연속 거주: {months_between(start, kst_today())}개월")
    else:
        print("전북 연속 거주: 현재 주소가 전북이 아니거나 계산 불가")


if __name__ == "__main__":
    main()

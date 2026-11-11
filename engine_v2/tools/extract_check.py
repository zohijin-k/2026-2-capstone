"""실제 서류에 추출기를 돌려 정답과 비교 — 본인 PC에서 실행.

  python -m engine_v2.tools.extract_check <file.pdf> --doc nhis_payment --gt <gt.json>
  python -m engine_v2.tools.extract_check <file.pdf> --doc nhis_acquisition_loss --gt <gt.json>

건강보험 서류의 출력은 필드별 상태와 값 없는 원인만 보여준다. 실제 값은 절대 출력하지 않는다.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from ..extractors import nhis_acquisition_loss, nhis_payment
from ..extractors.resident_abstract import extract, kst_today, months_between, resolved_sido, trailing_residence_start
from ..schemas.models import DocType as V2DocType, DocumentInput
from ..pipeline.ocr import run_ocr
from ..pipeline.preprocess import PageSource, preprocess
from .privacy import mask_text


DOC_LABELS = {
    "nhis_payment": ["성명", "생년월일", "발급일", "가입구분", "고지월", "건강보험료", "장기요양보험료"],
    "nhis_acquisition_loss": ["성명", "생년월일", "발급일", "가입구분", "변동내역", "취득일"],
    "insurance_4": ["문서확인번호", "발급번호", "발급일", "성명", "생년월일",
                    "가입내역", "최근취득일", "가입중"],
}
LAYOUT_LABELS = {
    "nhis_payment": ("성명", "생년월일", "주민등록번호", "발급일", "발급일자", "발행일", "출력일",
                     "직장가입자", "지역가입자", "년월", "고지금액", "고지보험료", "납부금액",
                     "납부보험료", "실납부", "건강보험료", "장기요양보험료", "장기요양", "합계"),
    "nhis_acquisition_loss": ("성명", "생년월일", "주민등록번호", "발급일", "발급일자", "발행일",
                              "출력일", "조회기간", "대상기간", "가입자구분", "자격구분", "자격취득일",
                              "취득일", "자격상실일", "상실일", "사업장명칭", "사업장명", "사업장"),
    "insurance_4": ("4대사회보험", "사회보험", "가입자", "가입내역", "확인서", "문서확인번호",
                    "발급번호", "발급일시", "발급일자", "발급일", "주민등록번호",
                    "외국인등록번호", "성명", "국민연금", "건강보험", "고용보험", "산재보험",
                    "사업장", "명칭", "관리번호", "구분", "자격", "취득일", "상실일",
                    "미가입", "해당없음", "직장", "지역"),
}


def _expected(doc: str, gt: dict) -> dict[str, str]:
    expected = {}
    for source, target in (("name", "성명"), ("birth_date", "생년월일"), ("issue_date", "발급일"),
                           ("insurance_type", "가입구분")):
        if gt.get(source) is not None:
            expected[target] = ("".join(str(gt[source]).split()) if source == "name" else str(gt[source]))
    if doc == "insurance_4":
        for key, target in (("name", "성명"), ("birth_date", "생년월일"),
                            ("issue_date", "발급일"), ("document_number", "문서확인번호")):
            if gt.get(key) is not None:
                expected[target] = str(gt[key]).replace(" ", "")
        if gt.get("rows"):
            rows = gt["rows"]
            expected["가입내역"] = json.dumps([
                {"보험종류": row["insurance_type"],
                 "취득일": row.get("acquired") or "",
                 "상실일": row.get("lost") or "",
                 "가입상태": "" if row.get("status") == "가입 중" else row.get("status", "")}
                for row in rows
            ], ensure_ascii=False, separators=(",", ":"))
            expected["최근취득일"] = json.dumps({
                row["insurance_type"]: max(
                    (candidate.get("acquired") or "" for candidate in rows
                     if candidate["insurance_type"] == row["insurance_type"]),
                    default="",
                )
                for row in rows
            }, ensure_ascii=False, separators=(",", ":"))
            expected["가입중"] = json.dumps({
                row["insurance_type"]: any(
                    candidate["insurance_type"] == row["insurance_type"]
                    and candidate.get("status") not in {"미가입", "해당없음"}
                    and not candidate.get("lost")
                    for candidate in rows
                )
                for row in rows
            }, ensure_ascii=False, separators=(",", ":"))
    elif doc == "nhis_payment":
        months = gt.get("billed_by_month", {})
        if months:
            expected["고지월"] = ",".join(sorted(months))
        if all(month in months for month in ("2025-10", "2025-11", "2025-12")):
            average = (sum(int(months[month]) for month in ("2025-10", "2025-11", "2025-12")) * 2 + 3) // 6
            expected["건강보험료"] = str(average)
        care = gt.get("long_term_care_by_month", {})
        if all(month in care for month in ("2025-10", "2025-11", "2025-12")):
            average = (sum(int(care[month]) for month in ("2025-10", "2025-11", "2025-12")) * 2 + 3) // 6
            expected["장기요양보험료"] = str(average)
    else:
        if "recent_five_years" in gt:
            expected["변동내역"] = "최근 5년 포함" if gt["recent_five_years"] else "최근 5년 미포함"
        active = [row.get("acquired") for row in gt.get("history", [])
                  if row.get("category") == "직장" and row.get("acquired") and not row.get("lost")]
        if active:
            expected["취득일"] = max(active)
        history = [row for row in gt.get("history", []) if row.get("category") and row.get("acquired")]
        if history:
            expected["가입구분"] = max(history, key=lambda row: row["acquired"])["category"]
    return expected


def _layout(doc: str, pages) -> None:
    from ..extractors.nhis_common import label_hits, page_lines

    print("[가린 배치] 값은 ### 로 숨겼습니다.")
    for page, result in pages:
        if not page.pixel_size:
            continue
        hits = []
        lines = page_lines(page, result)
        for label, words in label_hits(lines, LAYOUT_LABELS[doc]):
            if words and "".join(word.text for word in words).replace(" ", "") == label.replace(" ", ""):
                x0 = min(word.x0 for word in words)
                hits.append((round(x0, 1), label))
        if hits:
            parts = [f"[{x:.1f}%] {label} [###]" for x, label in sorted(set(hits))]
            print(f"쪽 {page.page + 1}: " + "  ".join(parts))
        else:
            print(f"쪽 {page.page + 1}: 라벨 후보를 못 찾음")


def _run_nhis(args, gt: dict) -> None:
    from ..engine import _load_pages

    doc_type = {
        "nhis_payment": V2DocType.NHIS_PAYMENT,
        "nhis_acquisition_loss": V2DocType.NHIS_ACQUISITION_LOSS,
        "insurance_4": V2DocType.INSURANCE_4,
    }[args.doc]
    input_doc = DocumentInput(doc_id="private-check", declared_type=doc_type, file_path=str(args.file))
    try:
        if args.engine == "jbai":
            from ..pipeline.jbai_ocr import run_jbai_pdf_pair
            from ..extractors.jbai_text import extract as extract_jbai

            document = run_jbai_pdf_pair(args.file)
            result = extract_jbai(document, doc_type)
            pages = None
        else:
            pages = _load_pages(input_doc, args.engine)
    except Exception:
        print("입력 처리: 못찾음 — PDF 또는 OCR 처리 실패")
        return
    if isinstance(pages, str):
        print("입력 처리: 못찾음 — 페이지 또는 OCR 처리가 중단됨")
        return
    if args.layout and pages is not None:
        _layout(args.doc, pages)
    try:
        if pages is not None:
            if args.doc == "insurance_4":
                from ..extractors import insurance_4
                extractor = insurance_4.extract
            else:
                extractor = nhis_payment.extract if args.doc == "nhis_payment" else nhis_acquisition_loss.extract
            result = extractor(pages)
    except Exception:
        print("추출 처리: 못찾음 — 서류 구조 또는 입력 처리 실패")
        return
    expected = _expected(args.doc, gt)
    validation_names = {v.name: v.passed for v in result.validations}
    validation_failures = {
        "건강보험료": ("monthly_total_matches", "월별 고지금액 합계가 합계 줄과 다름"),
        "취득일": ("acquisition_before_loss", "자격취득일이 자격상실일보다 늦음"),
        "변동내역": ("history_dates_read", "이력 표의 날짜를 모두 읽지 못함"),
    }
    print("[필드] 상태 — 값 없는 원인")
    for label in DOC_LABELS[args.doc]:
        field = result.fields.get(label)
        if field is None:
            status = "못찾음"
            reason = result.diagnostics.get(label, "해당 칸 또는 구분 가능한 값을 못 찾음")
        elif label in expected and args.doc == "insurance_4" and label in {"가입내역", "최근취득일", "가입중"}:
            try:
                actual_value = json.loads(field.value)
                expected_value = json.loads(expected[label])
                if label == "가입내역":
                    indexed = {row["보험종류"]: row for row in actual_value}
                    matches = all(
                        row["보험종류"] in indexed and all(
                            indexed[row["보험종류"]].get(key, "") == value
                            for key, value in row.items() if key != "보험종류"
                        )
                        for row in expected_value
                    )
                else:
                    matches = all(actual_value.get(key) == value for key, value in expected_value.items())
            except (TypeError, ValueError, KeyError):
                matches = False
            if not matches:
                status = "FAIL"
                reason = "정답과 불일치 (실제·정답 값 숨김)"
            else:
                status = "OK"
                reason = "정답과 일치"
        elif label in expected and str(field.value) != expected[label]:
            status = "FAIL"
            reason = "정답과 불일치 (실제·정답 값 숨김)"
        else:
            status = "OK"
            reason = "정답과 일치" if label in expected else "추출됨 (정답 비교 안 함)"
        if field is not None and label in validation_failures:
            validation, failure_reason = validation_failures[label]
            if not validation_names.get(validation, True):
                status, reason = "FAIL", failure_reason
        if label == "성명" and not validation_names.get("page_names_match", True):
            status, reason = "FAIL", "쪽마다 성명이 같지 않거나 일부 쪽에서 찾지 못함"
        print(f"  {label}: {status} — {mask_text(reason)}")
    if args.doc == "insurance_4":
        print("[검증]")
        for validation in result.validations:
            print(f"  {'OK' if validation.passed else 'FAIL'} {validation.name}")
    if args.engine == "jbai":
        _print_jbai_timing(document)


def _print_jbai_timing(document) -> None:
    print(f"[전북AI] 요청 {document.request_count}회, 전체 {document.elapsed_sec:.2f}초")
    for page in document.pages:
        print(f"  쪽 {page.page + 1}: OCR {page.ocr_elapsed_sec:.2f}초 / 표 {page.table_elapsed_sec:.2f}초")
    dropped = sorted({name for page in document.pages for name in page.unsupported_options})
    if dropped:
        print(f"  HTTP 400 뒤 제거한 요청 옵션: {', '.join(dropped)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("file", type=Path)
    ap.add_argument("--gt", type=Path)
    ap.add_argument("--engine", default="applevision")
    ap.add_argument("--doc", choices=("resident_abstract", "nhis_payment", "nhis_acquisition_loss", "insurance_4"),
                    default="resident_abstract")
    ap.add_argument("--layout", action="store_true", help="칸·열 제목 위치만 값 가림 형태로 표시")
    args = ap.parse_args()

    if args.doc == "insurance_4" and args.engine == "jbai":
        raise SystemExit("4대 사회보험 확인서는 좌표 기반 OCR 엔진만 지원합니다.")

    if args.engine == "jbai":
        import os
        if os.environ.get("JBAI_ALLOW_REAL_DOCS", "").strip().lower() not in {"1", "true", "yes", "on"}:
            raise SystemExit("전북AI 실제 파일 판독은 JBAI_ALLOW_REAL_DOCS=true일 때만 실행할 수 있습니다.")

    if not args.file.exists():
        if args.doc == "resident_abstract":
            raise SystemExit(f"서류 파일이 없어요: {args.file}  → engine_v2/data/private/ 에 PDF를 넣어주세요")
        raise SystemExit("서류 파일을 찾을 수 없습니다.")
    gt_path = args.gt
    if gt_path is None and args.doc != "resident_abstract":
        from ..paths import PRIVATE_DIR
        candidate = PRIVATE_DIR / f"{args.doc}.gt.json"
        gt_path = candidate if candidate.exists() else None
    if gt_path and not gt_path.exists():
        raise SystemExit(f"정답 파일이 없어요: {args.gt}  → python -m engine_v2.tools.make_gt 로 만들거나 --gt 없이 실행하세요")

    if args.doc != "resident_abstract":
        gt = json.loads(gt_path.read_text(encoding="utf-8")) if gt_path else {}
        _run_nhis(args, gt)
        return

    if args.engine == "jbai":
        from ..extractors.jbai_text import extract as extract_jbai
        from ..pipeline.jbai_ocr import run_jbai_pdf_pair
        document = run_jbai_pdf_pair(args.file)
        res = extract_jbai(document, V2DocType.RESIDENT_ABSTRACT)
        pages = []
    else:
        pages = []
        for p in preprocess(args.file):
            if p.source == PageSource.TEXT_LAYER:
                continue
            r = run_ocr(args.engine, p.png, p.pixel_size)
            if r.error:
                raise SystemExit(r.error)
            pages.append((p, r))
        res = extract(pages)
    gt = json.loads(gt_path.read_text(encoding="utf-8")) if gt_path else {}

    if args.layout:
        from ..pipeline.layout import group_lines, line_text, normalize, squash

        print("[가린 배치] 값은 ### 로 숨겼습니다.")
        found = False
        for page, result in pages:
            if not page.pixel_size:
                continue
            for line in group_lines(normalize(result.words, page.page, page.pixel_size)):
                text = squash(line_text(line))
                if "신청인" not in text:
                    continue
                x0 = min(word.x0 for word in line)
                print(f"쪽 {page.page + 1}: [{x0:.1f}%] 신청인  [###]")
                found = True
        if not found:
            print("쪽 1: 신청인 라벨을 못 찾음")
        if args.engine == "jbai":
            _print_jbai_timing(document)
        return

    if args.engine == "jbai":
        gt = json.loads(gt_path.read_text(encoding="utf-8")) if gt_path else {}
        print(f"서류 판별: {res.detected_type.value}")
        for key in ("issue_date", "name", "birth_date", "applicant_name", "applicant_birth_date",
                    "current_address", "address_history"):
            if key not in res.fields:
                continue
            field = res.fields[key]
            expected_match = None
            if key == "name" and "name" in gt:
                expected_match = field.value == gt["name"].replace(" ", "")
            elif key in ("birth_date", "issue_date") and key in gt:
                expected_match = field.value == date.fromisoformat(gt[key])
            label = "못찾음" if field is None else ("OK" if expected_match is True else
                  "FAIL" if expected_match is False else "추출됨")
            print(f"  {key}: {label}")
        print("[검증]")
        for validation in res.validations:
            print(f"  {'OK' if validation.passed else 'FAIL'} {validation.name}")
        print(f"[주소 이력] {len(res.history)}건")
        if gt.get("move_in_dates"):
            found = {d for entry in res.history for d in (entry.occurred, entry.reported) if d}
            hits = [date.fromisoformat(value) in found for value in gt["move_in_dates"]]
            print(f"정답 이력 날짜: {'OK' if all(hits) else 'FAIL'} ({sum(hits)}/{len(hits)})")
        _print_jbai_timing(document)
        return

    print(f"서류 판별: {res.detected_type.value} ({res.type_confidence})")
    for w in res.warnings:
        print(f"  경고: {mask_text(w)}")

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
        print(f"  {'통과' if v.passed else '실패'}  {mask_text(v.name)}  {mask_text(v.detail)}")

    print(f"\n[주소 이력] {len(res.history)}건 (시도 / 사유 / 발생일 유무 / 메모 수)")
    for i, e in enumerate(res.history):
        print(f"  {e.no!s:>3}  {mask_text(resolved_sido(res.history, i) or '?'):4s}  "
              f"{mask_text(' '.join(e.reason) or '-'):10s}  발생일{'O' if e.occurred else 'X'}  메모{len(e.notes)}")

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

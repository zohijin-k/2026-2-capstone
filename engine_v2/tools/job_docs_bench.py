"""패키지 서류 판독기 평가 — make_job_docs 합성셋을 정답과 비교한다 (가상 값만).

  python -m engine_v2.tools.make_job_docs
  python -m engine_v2.tools.job_docs_bench                        # 글자층(text) 조건만, OCR 엔진 없이
  python -m engine_v2.tools.job_docs_bench --engine rapidocr      # 이미지 조건까지 (pip install rapidocr onnxruntime)
  python -m engine_v2.tools.job_docs_bench --engine applevision   # 맥

출력: 서류 모양 × 화질 조건마다 서류 종류 판별, 필드 정답 수, 일부러 넣은 결함(취소 전표·일괄결제·
접수확인서·수험표)을 검증이 잡았는지, 건당 시간. --verbose는 틀린 필드를 정답과 함께 보여준다
(합성 가상 값이라 보여 줘도 된다. 실제 서류는 extract_check 로 값 없이 점검한다).
정답 비교 방식은 extract_check와 같다 (`_expected`·`_differs`).
"""
from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from pathlib import Path

from ..engine import _load_pages
from ..schemas.models import DocumentInput
from .extract_check import JOB_DOCS, _differs, _expected
from .make_job_docs import DEFAULT_OUT


def _register_rapidocr() -> None:
    """임시: RapidOCR 어댑터가 pipeline/ocr.py ENGINES에 들어오기 전까지 이 평가 도구에서만 붙인다.

    설정은 엔진 구축 계획의 실측값(PP-OCRv5 한국어 인식 모델, use_cls 끔, max_side_len 4000)이다.
    ENGINES에 이미 'rapidocr'가 있으면 그것을 쓴다.
    """
    from ..pipeline import ocr

    if "rapidocr" in ocr.ENGINES:
        return
    import cv2
    import numpy as np
    from rapidocr import LangRec, ModelType, OCRVersion, RapidOCR

    reader = RapidOCR(params={
        "Det.ocr_version": OCRVersion.PPOCRV5, "Det.model_type": ModelType.MOBILE,
        "Rec.lang_type": LangRec.KOREAN, "Rec.ocr_version": OCRVersion.PPOCRV5,
        "Rec.model_type": ModelType.MOBILE, "Global.use_cls": False, "Global.text_score": 0.0,
        "Global.max_side_len": 4000, "Global.log_level": "error"})

    def run(png: bytes, size) -> list:
        image = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
        result = reader(image)
        if result.boxes is None:
            return []
        return [ocr.OcrWord(text, float(score), (float(box[:, 0].min()), float(box[:, 1].min()),
                                                 float(box[:, 0].max()), float(box[:, 1].max())))
                for box, text, score in zip(np.asarray(result.boxes), result.txts, result.scores)]

    ocr.ENGINES["rapidocr"] = run


def evaluate(entry: dict, folder: Path, engine: str) -> dict:
    doc_type, extractor = JOB_DOCS[entry["doc"]]
    document = DocumentInput(doc_id=entry["file"], declared_type=doc_type, file_path=str(folder / entry["file"]))
    started = time.perf_counter()
    pages = _load_pages(document, engine)
    if isinstance(pages, str):
        return {"error": pages}
    result = extractor(pages)
    seconds = time.perf_counter() - started
    expected = _expected(entry["doc"], entry["gt"])
    wrong = {label: (str(result.fields[label].value) if label in result.fields else None, wanted)
             for label, wanted in expected.items()
             if label not in result.fields or _differs(entry["doc"], result.fields[label].value, wanted)}
    failed = {item.name for item in result.validations if not item.passed}
    return {
        "type_ok": result.detected_type.value == entry["expect_type"],
        "detected": result.detected_type.value,
        "fields": len(expected),
        "fields_ok": len(expected) - len(wrong),
        "wrong": wrong,
        "defects_caught": set(entry["expect_failed"]) <= failed,
        "unexpected_failed": sorted(failed - set(entry["expect_failed"])),
        "seconds": round(seconds, 2),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dir", type=Path, default=DEFAULT_OUT, help="make_job_docs 출력 폴더")
    ap.add_argument("--engine", default="text", help="text(글자층만) | rapidocr | applevision | easyocr | paddle")
    ap.add_argument("--conditions", help="쉼표로 구분 (기본: text 엔진이면 text, 아니면 합성셋의 전부)")
    ap.add_argument("--verbose", action="store_true", help="틀린 필드와 예상 밖 검증 실패를 보여줌")
    ap.add_argument("--json", type=Path, help="파일별 결과를 JSON으로 저장")
    args = ap.parse_args()

    manifest_path = args.dir / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit(f"합성셋이 없습니다: {manifest_path} → python -m engine_v2.tools.make_job_docs")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if args.conditions:
        conditions = set(args.conditions.split(","))
    else:
        conditions = {"text"} if args.engine == "text" else set(manifest["conditions"])
    if args.engine == "text" and conditions - {"text"}:
        raise SystemExit("이미지 조건은 OCR 엔진이 필요합니다: --engine rapidocr 등")
    if args.engine == "rapidocr":
        _register_rapidocr()
    engine = "off" if args.engine == "text" else args.engine  # 글자층은 OCR을 부르지 않는다

    rows = []
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for entry in manifest["files"]:
        if entry["condition"] not in conditions:
            continue
        outcome = evaluate(entry, args.dir, engine)
        rows.append({key: entry[key] for key in ("file", "doc", "layout", "condition")} | outcome)
        groups[(entry["layout"], entry["condition"])].append(outcome)

    print(f"엔진 {args.engine} · 조건 {','.join(sorted(conditions))} · 파일 {len(rows)}개")
    print(f"{'서류 모양':<28}{'조건':<8}{'건':>3}  {'종류':>5}  {'필드':>7}  {'결함':>5}  {'초/건':>6}")
    total = defaultdict(int)
    for (layout, condition), outcomes in sorted(groups.items()):
        ok = [o for o in outcomes if "error" not in o]
        errors = len(outcomes) - len(ok)
        fields = sum(o["fields"] for o in ok)
        fields_ok = sum(o["fields_ok"] for o in ok)
        types = sum(o["type_ok"] for o in ok)
        defects = sum(o["defects_caught"] for o in ok)
        seconds = sum(o["seconds"] for o in ok) / max(len(ok), 1)
        note = f"  오류 {errors}" if errors else ""
        print(f"{layout:<28}{condition:<8}{len(outcomes):>3}  {types:>2}/{len(ok):<2}  {fields_ok:>3}/{fields:<3}  "
              f"{defects:>2}/{len(ok):<2}  {seconds:>6.2f}{note}")
        for key, value in (("files", len(outcomes)), ("errors", errors), ("types", types), ("fields", fields),
                           ("fields_ok", fields_ok), ("defects", defects)):
            total[key] += value
    done = total["files"] - total["errors"]
    print(f"합계: 종류 {total['types']}/{done} · 필드 {total['fields_ok']}/{total['fields']} · "
          f"결함 잡음 {total['defects']}/{done}" + (f" · 처리 오류 {total['errors']}" if total["errors"] else ""))

    if args.verbose:
        for row in rows:
            if "error" in row:
                print(f"- {row['file']}: 처리 오류 {row['error']}")
            elif row["wrong"] or not row["type_ok"] or (row["unexpected_failed"] and row["fields"]):
                print(f"- {row['file']}: 판별={row['detected']} 틀림={row['wrong']} 예상밖실패={row['unexpected_failed']}")
    if args.json:
        args.json.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()

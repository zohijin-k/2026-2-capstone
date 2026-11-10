"""OCR 엔진 비교 — 반드시 본인 PC에서 실행.

  python -m engine_v2.tools.ocr_bench engine_v2/data/private/초본.pdf
  python -m engine_v2.tools.ocr_bench engine_v2/data/private/초본.pdf --engines applevision easyocr
  python -m engine_v2.tools.ocr_bench engine_v2/data/private/초본.pdf --gt engine_v2/data/private/초본.gt.json

출력 (터미널) — 팀 공유 가능: 엔진별 시간, 인식 단어 수, 평균 신뢰도, 키워드 적중, 정답 필드 맞음/틀림
저장 (data/private/ocr_<엔진>.txt) — 엔진별 전체 인식 텍스트. 개인정보 포함, 공유·커밋 금지

정답 파일 형식 (data/private/초본.gt.json, 본인 PC에만):
{
  "name": "홍길동",
  "birth_date": "1999-01-01",
  "issue_date": "2026-11-10",
  "address_contains": ["전주시", "완산구"],
  "move_in_dates": ["2018-03-02", "2021-07-15"]
}
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path

from ..paths import PRIVATE_DIR

from ..pipeline.ocr import ENGINES, run_ocr
from ..pipeline.preprocess import PageSource, preprocess
from ..pipeline.jbai_ocr import (
    JBAIOCRError, TASK_OCR, TASK_TABLE, run_jbai_pdf,
)

# 초본에 거의 항상 등장하는 고정 문구 — 읽혔는지로 기본 인식력 확인 (개인정보 아님)
KEYWORDS = ["주민등록표", "초본", "성명", "주민등록번호", "주소", "발생일", "신고일",
            "변동사유", "전입", "세대주", "발급", "시장", "군수", "구청장", "읍", "면", "동"]

DATE_RE = re.compile(r"(19|20)\d{2}\s*[.\-/년]\s*\d{1,2}\s*[.\-/월]\s*\d{1,2}")


def squash(s: str) -> str:
    return re.sub(r"\s+", "", s)


def date_variants(iso: str) -> list[str]:
    d = date.fromisoformat(iso)
    y, m, dd = d.year, d.month, d.day
    return [
        f"{y}.{m:02}.{dd:02}", f"{y}.{m}.{dd}", f"{y}-{m:02}-{dd:02}",
        f"{y}/{m:02}/{dd:02}", f"{y}년{m}월{dd}일", f"{y}년{m:02}월{dd:02}일",
    ]


def score_gt(text: str, gt: dict) -> dict[str, bool]:
    t = squash(text)
    res = {}
    if "name" in gt:
        res["name"] = squash(gt["name"]) in t
    for key in ("birth_date", "issue_date"):
        if key in gt:
            res[key] = any(v in t for v in date_variants(gt[key]))
    for i, part in enumerate(gt.get("address_contains", [])):
        res[f"address[{i}]"] = squash(part) in t
    for i, iso in enumerate(gt.get("move_in_dates", [])):
        res[f"move_in[{i}]"] = any(v in t for v in date_variants(iso))
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("file", type=Path)
    ap.add_argument("--engines", nargs="+", default=list(ENGINES))
    ap.add_argument("--gt", type=Path, help="정답 JSON (본인 PC에만)")
    args = ap.parse_args()

    pages = [p for p in preprocess(args.file) if p.source != PageSource.TEXT_LAYER]
    gt = json.loads(args.gt.read_text(encoding="utf-8")) if args.gt else None
    out_dir = PRIVATE_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"페이지 {len(pages)}쪽, 엔진 {args.engines}\n")
    summary = []
    for eng in args.engines:
        if eng in {"jbai-ocr", "jbai-table"}:
            task = TASK_OCR if eng == "jbai-ocr" else TASK_TABLE
            try:
                result = run_jbai_pdf(args.file, task=task)
            except JBAIOCRError as error:
                print(f"[{eng}] 실패 — {error}\n")
                summary.append({"engine": eng, "error": str(error)})
                continue
            content = "\n".join(
                "\n".join(page.text_lines) + "\n" + "\n".join(
                    cell.text for table in page.tables for row in table.rows for cell in row
                )
                for page in result.pages
            )
            row = {
                "engine": eng,
                "sec_total": round(result.elapsed_sec, 1),
                "sec_per_page": round(result.elapsed_sec / max(len(result.pages), 1), 1),
                "pages": len(result.pages),
                "text_lines": sum(len(page.text_lines) for page in result.pages),
                "tables": sum(len(page.tables) for page in result.pages),
                "table_cells": sum(
                    len(row) for page in result.pages for table in page.tables for row in table.rows
                ),
            }
            if gt:
                matches = score_gt(content, gt)
                row["gt_correct"] = f"{sum(matches.values())}/{len(matches)}"
                row["gt_detail"] = matches
            summary.append(row)
            print(f"[{eng}]")
            for key, value in row.items():
                if key != "engine":
                    print(f"  {key}: {value}")
            print("  인식 내용은 화면에 출력하거나 파일로 저장하지 않았습니다.\n")
            continue

        all_words, elapsed, err, texts = [], 0.0, None, []
        for p in pages:
            r = run_ocr(eng, p.png, p.pixel_size)
            if r.error:
                err = r.error
                break
            all_words += r.words
            elapsed += r.elapsed_sec
            texts.append(f"--- page {p.page} ---\n{r.text}")

        if err:
            print(f"[{eng}] 실패 — {err}\n")
            summary.append({"engine": eng, "error": err})
            continue

        full = "\n".join(texts)
        (out_dir / f"ocr_{eng}.txt").write_text(full, encoding="utf-8")

        confs = [w.confidence for w in all_words]
        row = {
            "engine": eng,
            "sec_total": round(elapsed, 1),
            "sec_per_page": round(elapsed / max(len(pages), 1), 1),
            "words": len(all_words),
            "mean_conf": round(sum(confs) / len(confs), 3) if confs else 0,
            "low_conf_ratio(<0.8)": round(sum(c < 0.8 for c in confs) / len(confs), 3) if confs else 0,
            "keywords_hit": f"{sum(k in squash(full) for k in KEYWORDS)}/{len(KEYWORDS)}",
            "dates_found": len(DATE_RE.findall(full)),
        }
        if gt:
            g = score_gt(full, gt)
            row["gt_correct"] = f"{sum(g.values())}/{len(g)}"
            row["gt_detail"] = g
        summary.append(row)
        print(f"[{eng}]")
        for k, v in row.items():
            if k != "engine":
                print(f"  {k}: {v}")
        print(f"  전체 텍스트: {out_dir / f'ocr_{eng}.txt'} (공유 금지)\n")

    print("=== 요약 JSON (팀 공유 가능) ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

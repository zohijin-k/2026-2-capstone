"""Synthetic evaluation or explicit-input, value-free document benchmark."""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import re

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


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse normally echoes invalid arguments (which may contain values).
        self.exit(2, "argument_error: O\n")


def main() -> None:
    ap = SafeParser()
    ap.add_argument("file", type=Path, nargs="?")
    ap.add_argument("--env-file", type=Path)
    ap.add_argument("--synth", type=Path)
    ap.add_argument("--output", type=Path, help="합성 결과 JSON 경로")
    ap.add_argument("--out", type=Path, help="값 미출력 결과 JSON; 생략 시 화면만")
    ap.add_argument("--unmasked-synthetic", action="store_true")
    ap.add_argument("--rectify-phone", action="store_true")
    ap.add_argument("--engines", nargs="+", default=["own", "applevision", "jbai"])
    ap.add_argument("--gt", type=Path)
    ap.add_argument("--doc", choices=["resident_abstract", "nhis_payment", "nhis_acquisition_loss", "insurance_4",
                                      "receipt", "exam_admission", "exam_score", "interview_confirm"],
                    default="resident_abstract")
    ap.add_argument("--today", type=date.fromisoformat)
    args = ap.parse_args()
    from .private_bench import quiet_dependencies
    if args.env_file:
        try:
            with quiet_dependencies():
                from dotenv import load_dotenv
                if not args.env_file.is_file():
                    raise ValueError("missing configuration")
                load_dotenv(args.env_file, override=False)
        except Exception:
            ap.error("configuration")
    if args.synth:
        if args.file or args.gt or args.out:
            ap.error("mixed modes")
        from .synth_bench import run_suite
        run_suite(args.synth, args.engines, args.output or args.synth.parent / "bench.json",
                  unmasked=args.unmasked_synthetic, rectify_phone=args.rectify_phone)
        return
    if args.file is None or args.gt is None or args.output or args.unmasked_synthetic or args.rectify_phone:
        ap.error("explicit file and ground truth required")
    from .private_bench import run_private
    run_private(args.file, args.gt, args.engines, doc=args.doc, out=args.out, today=args.today)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit("interrupted: O") from None

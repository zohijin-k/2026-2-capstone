"""원본 시행지침 PDF에서 서식 페이지를 **논리 쪽 단위로** 잘라 템플릿으로 저장한다 (P7).

저장소 루트에서:

    PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python -m demo.fixtures.cut_templates

⚠️ **원본이 2-up이다.** 시행지침·공고문 모두 A4 가로(841×595pt) 물리 1쪽에 논리
2쪽이 들어 있다. 물리 12쪽 왼쪽 반이 "- 23 -"(서식1 앞면), 오른쪽 반이
"- 24 -"(서식1 뒷면)이고, 물리 14쪽 오른쪽 반이 "- 28 -"(서식5)다. 반으로 자르지
않으면 서식 하나를 채우려고 쓸데없이 옆 쪽까지 끌고 다니게 되고, 좌표계도 옆 쪽
기준으로 밀린다.

자른 결과는 `templates/서식1.pdf`(2쪽) · `templates/서식5.pdf`(1쪽)이다. 원본
텍스트 레이어와 표 선(벡터)이 그대로 남으므로 `build_form_coords.py`가 여기서
좌표를 다시 뽑아낼 수 있다 — **눈대중 좌표를 쓰지 않기 위한 전제**다.

잘린 쪽이 맞는지는 쪽번호 문자열(`- 23 -`)로 검증한다. 원본 PDF가 개정되어 서식
위치가 밀리면 여기서 바로 실패한다.
"""

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent
TEMPLATES = FIXTURES / "templates"

#: 원본 파일명. 저장소 루트에 있다(커밋 대상이 아니다 — `.gitignore`의 `*.pdf`).
GUIDELINE = "2026년 전북청년 함께 두배적금 사업 시행지침.pdf"

#: 2-up 물리 쪽의 가로 절반 경계. 원본 물리 쪽 폭 841pt의 정확히 절반이다.
HALF = 0.5


@dataclass(frozen=True)
class Cut:
    """잘라낼 논리 쪽 하나."""

    #: 원본 물리 쪽 번호(0-based)
    physical_page: int
    #: 0=왼쪽 반(앞 논리 쪽) / 1=오른쪽 반(뒤 논리 쪽)
    half: int
    #: 잘린 쪽에 반드시 있어야 하는 쪽번호 문자열. 자른 자리가 맞는지 검증한다.
    marker: str


@dataclass(frozen=True)
class Template:
    form_no: str
    title: str
    source: str
    cuts: tuple[Cut, ...]


TEMPLATES_SPEC: tuple[Template, ...] = (
    Template(
        form_no="서식1",
        title="「전북청년 함께 두배적금」참여 신청서",
        source=GUIDELINE,
        cuts=(
            Cut(physical_page=12, half=0, marker="- 23 -"),
            Cut(physical_page=12, half=1, marker="- 24 -"),
        ),
    ),
    Template(
        form_no="서식5",
        title="행정정보 공동이용 사전동의서",
        source=GUIDELINE,
        cuts=(Cut(physical_page=14, half=1, marker="- 28 -"),),
    ),
)

#: 좌표 맵만 남기고 템플릿은 자르지 않는 서식들(설계 6-B.3). 원본 위치만 기록해
#: 두면 나중에 여기에 한 줄 추가하는 것으로 끝난다.
DEFERRED = {
    "서식2": Cut(physical_page=13, half=0, marker="- 25 -"),
    "서식3": Cut(physical_page=13, half=1, marker="- 26 -"),
    "서식4": Cut(physical_page=14, half=0, marker="- 27 -"),
}


def cut_all(source_dir: Path = REPO_ROOT, out_dir: Path = TEMPLATES) -> list[Path]:
    import fitz  # PyMuPDF

    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for spec in TEMPLATES_SPEC:
        src_path = source_dir / spec.source
        if not src_path.exists():
            raise FileNotFoundError(
                f"원본 PDF가 없습니다: {src_path}\n"
                "시행지침 PDF를 저장소 루트에 두고 다시 실행하세요."
            )
        with fitz.open(src_path) as src:
            out = fitz.open()
            for cut in spec.cuts:
                page = src[cut.physical_page]
                full = page.rect
                x0 = full.x0 + full.width * HALF * cut.half
                clip = fitz.Rect(x0, full.y0, x0 + full.width * HALF, full.y1)
                new = out.new_page(width=clip.width, height=clip.height)
                # clip 을 준 show_pdf_page 는 잘라낸 영역을 새 쪽 전체에 1:1로
                # 얹는다. 배율이 1이므로 원본 좌표 → 템플릿 좌표는 단순 평행이동
                # (x -= clip.x0)이고, 텍스트·벡터가 그대로 남아 재추출된다.
                new.show_pdf_page(new.rect, src, cut.physical_page, clip=clip)

            _verify(out, spec)
            # 원본 한글 폰트를 통째로 안고 가면 서식 하나가 300KB를 넘는다.
            # 실제로 쓰인 글자만 남겨 절반 이하로 줄인다.
            out.subset_fonts(verbose=False)
            target = out_dir / f"{spec.form_no}.pdf"
            out.save(target, garbage=4, deflate=True, clean=True)
            out.close()
        written.append(target)
        size = target.stat().st_size
        print(f"  {spec.form_no}: {len(spec.cuts)}쪽 · {size:,} bytes → {target}")

    return written


def _verify(doc: object, spec: Template) -> None:
    """자른 쪽이 정말 그 논리 쪽인지 쪽번호로 확인한다."""
    for index, cut in enumerate(spec.cuts):
        text = doc[index].get_text()  # type: ignore[index]
        flat = " ".join(text.split())
        if cut.marker.replace(" ", "") not in flat.replace(" ", ""):
            raise AssertionError(
                f"{spec.form_no} {index + 1}쪽에 쪽번호 {cut.marker!r}가 없습니다. "
                "원본 PDF의 서식 위치가 바뀐 것 같습니다."
            )
        if spec.form_no not in flat and index == 0:
            raise AssertionError(
                f"{spec.form_no} 1쪽에 서식 번호가 없습니다. 자른 위치를 확인하세요."
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="시행지침 PDF → 서식 템플릿 잘라내기")
    parser.add_argument(
        "--source-dir",
        default=str(REPO_ROOT),
        help="원본 PDF가 있는 폴더 (기본: 저장소 루트)",
    )
    args = parser.parse_args()

    print("서식 템플릿 잘라내기 (2-up 논리 쪽 단위)")
    cut_all(Path(args.source_dir))
    print("\n좌표 맵만 남기는 서식(템플릿 미생성):")
    for form_no, cut in DEFERRED.items():
        print(f"  {form_no}: 물리 {cut.physical_page}쪽 {'오른쪽' if cut.half else '왼쪽'} 반 ({cut.marker})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

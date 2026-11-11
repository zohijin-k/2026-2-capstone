"""두 사업 원본 PDF에서 A4 신청 서식 쪽을 검증하고 템플릿으로 만든다."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from ..form_numbers import order_form_numbers, public_form_no

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent
TEMPLATES = FIXTURES / "templates"

DOUBLE_SOURCE = "2026_두배적금_공고문.pdf"
JOB_SOURCE = "2026_취업패키지_신청서.pdf"

@dataclass(frozen=True)
class PageSpec:
    source_page: int  # 1-based page number
    title_marker: str


@dataclass(frozen=True)
class TemplateSpec:
    key: str
    source: str
    title: str
    pages: tuple[PageSpec, ...]
    mask_markers: tuple[str, ...] = ()

    @property
    def public_form(self) -> str | None:
        return public_form_no(self.key)


_TEMPLATE_SPECS = (
    TemplateSpec("서식2", DOUBLE_SOURCE, "신청자격 자가진단 및 필수사항 확인·동의서",
                 (PageSpec(10, "서식1 신청자격 자가진단"),)),
    TemplateSpec("서식1", DOUBLE_SOURCE, "「전북청년 함께 두배적금」참여 신청서",
                 (PageSpec(11, "서식2 「전북청년 함께 두배적금」참여 신청서"),
                  PageSpec(12, "Ⅱ. 납입금액"))),
    TemplateSpec("서식3", DOUBLE_SOURCE, "개인정보 수집 및 이용 동의서",
                 (PageSpec(13, "서식3 개인정보 수집 및 이용 동의서"),)),
    TemplateSpec("서식4", DOUBLE_SOURCE, "개인(신용)정보 제3자 제공 동의서",
                 (PageSpec(14, "서식4 개인(신용)정보 제3자 제공 동의서"),)),
    TemplateSpec("서식5", DOUBLE_SOURCE, "행정정보 공동이용 사전동의서",
                 (PageSpec(15, "서식5 행정정보 공동이용 사전동의서"),)),
    TemplateSpec("job_application", JOB_SOURCE, "2026 전북 청년 취업지원패키지 신청서",
                 (PageSpec(1, "『2026 전북 청년 취업지원패키지』신청서"),),
                 mask_markers=("전북특별자치도 OO시/군", "한국교통안전공단", "한국산업인력공단")),
    TemplateSpec("job_consent", JOB_SOURCE, "개인정보 수집·이용·제공 동의서",
                 (PageSpec(2, "개인정보 수집·이용·제공 동의서"),)),
    TemplateSpec("job_interview_confirmation", JOB_SOURCE, "면접확인서",
                 (PageSpec(3, "면접확인서"),)),
)

_spec_by_key = {spec.key: spec for spec in _TEMPLATE_SPECS}
TEMPLATES_SPEC = tuple(_spec_by_key[key] for key in order_form_numbers(_spec_by_key))


def _flat(text: str) -> str:
    return "".join(text.split())


def _verify_page(page, spec: TemplateSpec, page_spec: PageSpec) -> None:
    import pymupdf

    rect = page.rect
    if abs(rect.width - 595.276) > 1.0 or abs(rect.height - 841.89) > 1.0:
        raise AssertionError(f"{spec.key} 원본 {page_spec.source_page}쪽이 A4 세로가 아닙니다.")
    text = _flat(page.get_text())
    if _flat(page_spec.title_marker) not in text:
        raise AssertionError(
            f"{spec.key} 원본 {page_spec.source_page}쪽에서 지정 제목을 찾지 못했습니다."
        )
    if pymupdf.Rect(0, 0, rect.width, rect.height).is_empty:
        raise AssertionError(f"{spec.key} 원본 쪽 크기가 비었습니다.")


def cut_all(source_dir: Path = REPO_ROOT, out_dir: Path = TEMPLATES) -> list[Path]:
    import pymupdf

    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    by_key = {spec.key: spec for spec in TEMPLATES_SPEC}
    for form_no in order_form_numbers(by_key):
        spec = by_key[form_no]
        src_path = source_dir / spec.source
        if not src_path.exists():
            raise FileNotFoundError(f"원본 PDF가 없습니다: {src_path}")
        with pymupdf.open(src_path) as source:
            result = pymupdf.open()
            for page_spec in spec.pages:
                index = page_spec.source_page - 1
                if index >= len(source):
                    raise AssertionError(f"{spec.key} 원본 쪽 번호가 범위를 벗어났습니다.")
                _verify_page(source[index], spec, page_spec)
                result.insert_pdf(source, from_page=index, to_page=index)
            result.subset_fonts(verbose=False)
            target = out_dir / f"{spec.key}.pdf"
            result.save(target, garbage=4, deflate=True, clean=True)
            result.close()
        written.append(target)
        print(f"  {spec.key}: {len(spec.pages)}쪽, 제목·A4 검증 완료")
    return written


def main() -> int:
    print("공식 원본에서 A4 신청 서식 템플릿 만들기")
    cut_all()
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""좌표 맵 읽기.

좌표는 `demo/fixtures/build_form_coords.py`가 원본 PDF에서 뽑아 JSON으로 적어 둔
것이다. 여기서는 읽기만 한다 — 값을 여기에 적어 넣으면 원본과 어긋나도 아무도
모르게 된다.
"""

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
COORDS_DIR = FIXTURES / "form_coords"

# 신청자가 작성하는 서식. 공고문 번호와 시행지침 내부 번호의 대응은
# 템플릿 정의(cut_templates.py) 한 곳에만 둔다.
EXPORTABLE = ("서식1", "서식2", "서식3", "서식4", "서식5", "job_application", "job_consent")


@dataclass(frozen=True)
class FormCoords:
    form_no: str
    title: str
    template: Path
    fields: dict[str, dict[str, Any]]
    source: dict[str, Any]
    public_form: str | None = None
    internal_form: str | None = None
    masks: list[dict[str, Any]] | None = None

    def field(self, key: str) -> dict[str, Any] | None:
        return self.fields.get(key)

    def resolve_check(self, key: str) -> dict[str, Any] | None:
        """체크박스 좌표 찾기. 보기 문구가 원문보다 긴 경우를 접어 준다.

        화면 상수는 원문 괄호까지 붙여 쓰는데(`SNS(인스타그램)`) 원본 PDF는 줄이
        바뀌며 `SNS` 에서 끊긴다. 같은 묶음 안에서 앞부분이 일치하는 가장 긴
        좌표를 쓴다.
        """
        exact = self.fields.get(key)
        if exact is not None:
            return exact
        group = key.split(".", 1)[0] + "."
        candidates = [
            (len(name), value)
            for name, value in self.fields.items()
            if value["type"] == "check" and name.startswith(group) and key.startswith(name)
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda c: -c[0])
        return candidates[0][1]

    @property
    def available(self) -> bool:
        return bool(self.fields) and self.template.exists()


@lru_cache(maxsize=None)
def load(form_no: str) -> FormCoords | None:
    """좌표 맵 한 벌. 없으면 None — 선택 기능이라 예외로 세우지 않는다."""
    path = COORDS_DIR / f"{form_no}.json"
    if not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    template = raw.get("template")
    return FormCoords(
        form_no=raw.get("form_no", form_no),
        title=raw.get("title", form_no),
        template=(FIXTURES / template) if template else Path("<없음>"),
        fields=raw.get("fields", {}),
        source=raw.get("source", {}),
        public_form=raw.get("public_form"),
        internal_form=raw.get("internal_form"),
        masks=raw.get("masks", []),
    )

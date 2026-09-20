"""시연 초기화 — 데모 DB와 업로드 원본만 지운다. **파괴적 스크립트다.**

저장소 루트에서:

    PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python -m demo.backend.reset --dry-run
    PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python -m demo.backend.reset
    PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python -m demo.backend.reset --yes

`--dry-run`은 무엇을 지울지 출력만 한다. 인자 없이 실행하면 목록을 보여준 뒤
`y`를 입력해야 지운다. `--yes`는 확인을 건너뛴다 — 시연 직전에만 쓴다.

지우는 것은 **딱 둘**이다.

    demo/demo.db   (+ SQLite 부속 파일 -wal / -shm)
    demo/storage/  (업로드 원본 · 전자서명 PNG)

둘 다 루트 `.gitignore`에 올라가 있어 저장소에 커밋되지 않는다. 즉 이 스크립트가
지우는 것 중 git이 추적하는 파일은 하나도 없다. 소스(`backend/`, `frontend/`),
시연 샘플(`fixtures/`), 문서는 건드리지 않는다.

**방어 코드**를 세 겹으로 둔다. 시연장에서 급히 돌리는 스크립트라 실수 한 번의
대가가 크다.

  1. 대상 폴더 안에 `.git`·`engine`·`dashboard`가 있으면 저장소 루트로 보고 거부한다
  2. 지울 대상의 이름이 `DELETABLE` 목록에 없으면 거부한다
  3. 지울 대상이 대상 폴더의 직속 자식이 아니거나 심볼릭 링크면 거부한다
"""

import argparse
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

#: demo/ 폴더. 이 스크립트는 `demo/backend/reset.py`에 있다.
DEMO_ROOT = Path(__file__).resolve().parents[1]

#: 지워도 되는 것. 이름이 여기 없으면 어떤 경우에도 지우지 않는다.
DELETABLE: tuple[str, ...] = ("demo.db", "demo.db-wal", "demo.db-shm", "storage")

#: 하나라도 있으면 "데모 폴더가 아니다"로 보고 거부한다. 저장소 루트를 잘못
#: 가리켰을 때 engine/·dashboard/가 통째로 날아가는 것을 막는 1차 방어선이다.
REPO_MARKERS: tuple[str, ...] = (".git", "engine", "dashboard")

#: 데모 폴더 안에서도 절대 건드리지 않는 것. 참고용 목록이자 출력용이다.
PROTECTED: tuple[str, ...] = ("backend", "frontend", "fixtures", "docs", "README.md")

#: 지운 뒤 다시 만들어 두는 빈 폴더. 서버가 첫 업로드 때 어차피 만들지만,
#: 폴더가 보이는 편이 시연 중 "리셋됐다"를 눈으로 확인하기 쉽다.
RECREATE: tuple[str, ...] = ("storage/documents", "storage/signatures")


class ResetRefused(RuntimeError):
    """방어 코드에 걸려 아무것도 지우지 않았다."""


@dataclass
class Target:
    """지울 대상 하나."""

    path: Path
    exists: bool = False
    files: int = 0
    size: int = 0

    @property
    def kind(self) -> str:
        if not self.exists:
            return "없음"
        return "폴더" if self.path.is_dir() else "파일"


@dataclass
class ResetReport:
    root: Path
    targets: list[Target] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    dry_run: bool = False

    @property
    def deleted_files(self) -> int:
        return sum(t.files for t in self.targets if t.exists)

    @property
    def deleted_bytes(self) -> int:
        return sum(t.size for t in self.targets if t.exists)

    @property
    def had_anything(self) -> bool:
        return any(t.exists for t in self.targets)


# ---------------------------------------------------------------- 방어 코드


def check_root(root: Path) -> Path:
    """대상 폴더가 지워도 되는 곳인지 본다. 아니면 `ResetRefused`."""
    resolved = root.resolve()

    if not resolved.exists() or not resolved.is_dir():
        raise ResetRefused(f"폴더가 없습니다: {resolved}")

    # 드라이브 루트(D:\) · 파일시스템 루트(/)를 가리키면 즉시 거부한다.
    if len(resolved.parts) < 2:
        raise ResetRefused(f"최상위 경로는 대상이 될 수 없습니다: {resolved}")

    present = [m for m in REPO_MARKERS if (resolved / m).exists()]
    if present:
        raise ResetRefused(
            f"저장소 루트로 보입니다({', '.join(present)} 발견): {resolved}\n"
            "이 스크립트는 demo/ 폴더만 초기화합니다."
        )

    return resolved


def _check_target(root: Path, target: Path) -> None:
    """개별 대상에 대한 2·3차 방어선."""
    if target.name not in DELETABLE:
        raise ResetRefused(f"지울 수 있는 대상이 아닙니다: {target}")
    if target.parent != root:
        raise ResetRefused(f"대상 폴더의 직속 자식이 아닙니다: {target}")
    if target.is_symlink():
        raise ResetRefused(f"심볼릭 링크는 지우지 않습니다: {target}")


# ---------------------------------------------------------------- 계획


def _measure(path: Path) -> Target:
    target = Target(path=path, exists=path.exists())
    if not target.exists:
        return target
    if path.is_dir():
        for child in path.rglob("*"):
            if child.is_file():
                target.files += 1
                target.size += child.stat().st_size
    else:
        target.files = 1
        target.size = path.stat().st_size
    return target


def plan(root: Path = DEMO_ROOT) -> list[Target]:
    """무엇을 지울지 계산한다. 아무것도 지우지 않는다."""
    resolved = check_root(root)
    targets: list[Target] = []
    for name in DELETABLE:
        target_path = resolved / name
        _check_target(resolved, target_path)
        targets.append(_measure(target_path))
    return targets


# ---------------------------------------------------------------- 실행


def reset(root: Path = DEMO_ROOT, *, dry_run: bool = False) -> ResetReport:
    """`demo/demo.db`와 `demo/storage/`를 지운다.

    호출 전에 DB 연결을 닫아야 한다. Windows에서는 uvicorn이 떠 있으면 SQLite
    파일이 잠겨 삭제가 실패한다 — 그 경우 `PermissionError`를 그대로 올린다.
    """
    resolved = check_root(root)
    report = ResetReport(root=resolved, targets=plan(resolved), dry_run=dry_run)
    if dry_run:
        return report

    for target in report.targets:
        if not target.exists:
            continue
        _check_target(resolved, target.path)
        if target.path.is_dir():
            shutil.rmtree(target.path)
        else:
            target.path.unlink()
        report.removed.append(target.path.name)

    for relative in RECREATE:
        (resolved / relative).mkdir(parents=True, exist_ok=True)

    return report


# ---------------------------------------------------------------- CLI


def _human(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / 1024 / 1024:.1f} MB"


def _print_plan(root: Path, targets: list[Target]) -> None:
    print(f"초기화 대상 폴더: {root}")
    print("\n지울 것:")
    for target in targets:
        if target.exists:
            print(f"  - {target.path.name:<14} ({target.kind}, 파일 {target.files}개, {_human(target.size)})")
        else:
            print(f"  - {target.path.name:<14} (없음 — 건너뜀)")
    print("\n건드리지 않는 것:")
    print(f"  {', '.join(PROTECTED)}")
    print("  ※ 위 대상은 전부 .gitignore 대상이라 git이 추적하는 파일은 지워지지 않습니다.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m demo.backend.reset",
        description="데모 DB(demo/demo.db)와 업로드 저장소(demo/storage/)를 지운다.",
    )
    parser.add_argument("--yes", "-y", action="store_true", help="확인 없이 바로 지운다")
    parser.add_argument("--dry-run", action="store_true", help="지우지 않고 목록만 출력")
    parser.add_argument(
        "--root",
        default=str(DEMO_ROOT),
        help="초기화할 demo 폴더 (기본: 이 스크립트가 속한 demo/). 검증 스크립트가 임시 경로를 넘길 때 쓴다",
    )
    args = parser.parse_args(argv)

    try:
        root = check_root(Path(args.root))
        targets = plan(root)
    except ResetRefused as e:
        print(f"[거부] {e}", file=sys.stderr)
        return 2

    _print_plan(root, targets)

    if args.dry_run:
        print("\n--dry-run 이므로 아무것도 지우지 않았습니다.")
        return 0

    if not any(t.exists for t in targets):
        print("\n이미 비어 있습니다. 할 일이 없습니다.")
        return 0

    if not args.yes:
        if not sys.stdin.isatty():
            print(
                "\n[중단] 확인 입력을 받을 수 없는 환경입니다. 정말 지우려면 --yes 를 붙이세요.",
                file=sys.stderr,
            )
            return 2
        answer = input("\n정말 지울까요? 지운 데이터는 복구할 수 없습니다. [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("취소했습니다. 아무것도 지우지 않았습니다.")
            return 1

    try:
        report = reset(root)
    except PermissionError as e:
        print(
            f"\n[실패] 파일이 잠겨 있습니다: {e}\n"
            "uvicorn 서버를 멈춘 뒤 다시 실행하세요 (Windows는 실행 중인 SQLite 파일을 지우지 못합니다).",
            file=sys.stderr,
        )
        return 3

    print(f"\n지웠습니다: {', '.join(report.removed)}")
    print(f"파일 {report.deleted_files}개 · {_human(report.deleted_bytes)}")
    print("빈 DB는 서버를 다음에 띄울 때 자동으로 만들어집니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
